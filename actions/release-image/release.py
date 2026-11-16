#!/usr/bin/env python3
"""Check, tag and verify the release image of a version, by its digest.

Run by the `release-image` action (see its README) in the job that releases
an image after it was pushed by digest and scanned. The action attests and
signs the digest between the two commands of this script:

`check`: before anything is attested or signed, fail unless the settings
    are well-formed (a fully qualified image name, a `sha256:` digest, a
    release tag) and the version's image tag doesn't exist yet or points to
    the digest already (a re-run of the same release). A published version
    never moves to another digest.
`tag`: tag the digest with the version and, if it is the highest stable
    release, with `latest`, then check that each tag points to the digest.

`latest` follows the rule of `publish-release`, whose code it uses (see
`is_latest`), so that the image's `latest` and the GitHub release marked
"Latest" are the same release. Only the prefix of the tag differs: tags of
other prefixes (other packages or charts of the repository) don't count.

The settings are read from the environment (see `Settings`). Errors are
printed as error annotations to standard error; on success, the outputs are
written to `GITHUB_OUTPUT`. Needs Python 3.10 or later, the GitHub CLI
(`gh`; for `latest: auto` only) and Docker with Buildx (`docker buildx
imagetools`), as on GitHub-hosted Linux runners, and the scripts of the
`check-release` and `publish-release` actions next to this one (as in every
checkout of the repository that holds them).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import types
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

TITLE = "Release image"

Runner = Callable[[Sequence[str]], str]


def _load(name: str, path: Path) -> types.ModuleType:
    """Load the script of another action as a module.

    The actions' directories aren't packages, and `python3 -I` leaves this
    script's directory out of the module search path.

    Args:
        name: Name of the module.
        path: Path of the script.

    Returns:
        The module.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    # Registered first, as dataclasses look their module up
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_ACTIONS = Path(__file__).resolve().parent.parent
# The release versions of check-release, and the version order and "latest"
# rule of publish-release: used, not copied, so that they can't drift apart
check_release = _load(
    "release_image_check_release", _ACTIONS / "check-release" / "check.py"
)
publish_release = _load(
    "release_image_publish_release", _ACTIONS / "publish-release" / "publish.py"
)

# Fully qualified image names without tag or digest, as the attestation
# needs them: a registry host (with a `.` or a port, or `localhost`), then
# path components in lower case (OCI distribution spec), e.g.,
# `docker.io/elixircloud/tesk-api` or `ghcr.io/elixir-cloud-aai/krini`
_COMPONENT = r"[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*"
IMAGE = re.compile(
    r"(?:[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?::[0-9]+)?|localhost(?::[0-9]+)?"
    r"|[A-Za-z0-9-]+:[0-9]+)"
    rf"(?:/{_COMPONENT})+",
    re.ASCII,
)
DIGEST = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)
LATEST = ("auto", "false")
# Errors of `docker buildx imagetools inspect` for a tag that doesn't exist
# (Docker Hub, GHCR, the distribution registry); any other error fails
NOT_FOUND = re.compile(r"not found|manifest unknown", re.IGNORECASE)


class ReleaseError(Exception):
    """A reason not to release the image, with what to do about it."""


@dataclass(frozen=True)
class Settings:
    """Settings of the release, from the environment of the action's steps.

    Attributes:
        image: Fully qualified image name, without tag or digest (`IMAGE`).
        digest: Digest of the image to release (`DIGEST`).
        tag: Name of the release's Git tag (`TAG`).
        prefix: Part of the tag before the version (`TAG_PREFIX`).
        latest: `auto` to tag the highest stable release `latest`, `false`
            never to (`LATEST`).
        repository: `<owner>/<repo>` whose releases decide `latest`
            (`GH_REPO`).
    """

    image: str
    digest: str
    tag: str
    prefix: str = "v"
    latest: str = "auto"
    repository: str = ""

    @property
    def version(self) -> str:
        """The release version: the tag without the prefix."""
        return str(check_release.release_version(self.tag, self.prefix))

    @classmethod
    def from_env(cls, env: dict[str, str]) -> Settings:
        """Read and validate the settings from environment variables.

        Args:
            env: Environment variables.

        Returns:
            The settings.

        Raises:
            ReleaseError: If a required setting is missing or a setting is
                malformed.
        """
        required = ["IMAGE", "DIGEST", "TAG", "LATEST"]
        if env.get("LATEST", "").strip() != "false":
            required.append("GH_REPO")
        missing = [name for name in required if not env.get(name, "").strip()]
        if missing:
            raise ReleaseError(f"Not set: {', '.join(missing)}")
        settings = cls(
            image=env["IMAGE"].strip(),
            digest=env["DIGEST"].strip(),
            tag=env["TAG"].strip(),
            prefix=env.get("TAG_PREFIX", "").strip(),
            latest=env["LATEST"].strip(),
            repository=env.get("GH_REPO", "").strip(),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        """Check that the settings are well-formed.

        Raises:
            ReleaseError: For the first malformed setting.
        """
        checks = (
            (
                IMAGE,
                self.image,
                "image",
                (
                    "a fully qualified image name without tag or digest, e.g.,"
                    " docker.io/elixircloud/tesk-api"
                ),
            ),
            (DIGEST, self.digest, "digest", "sha256: and 64 hex digits"),
            (check_release.PREFIX, self.prefix, "tag-prefix", "e.g., v or chart-v"),
        )
        for pattern, value, name, expected in checks:
            if not pattern.fullmatch(value):
                raise ReleaseError(f"Invalid {name} '{value}': expected {expected}")
        if self.latest not in LATEST:
            raise ReleaseError(
                f"Invalid latest '{self.latest}': expected auto or false"
            )
        if self.latest == "auto" and not check_release.REPOSITORY.fullmatch(
            self.repository
        ):
            raise ReleaseError(
                f"Invalid repository '{self.repository}': expected <owner>/<repo>"
            )
        try:
            check_release.release_version(self.tag, self.prefix)
        except check_release.CheckError as error:
            raise ReleaseError(str(error)) from error


def _run(program: str, args: Sequence[str]) -> str:
    """Run a program and return its standard output.

    Args:
        program: Name of the program, e.g., `docker`.
        args: Its arguments.

    Returns:
        The standard output.

    Raises:
        ReleaseError: If the program fails; with its standard error.
    """
    command = [program, *args]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ReleaseError(f"{shlex.join(command)} failed: {result.stderr.strip()}")
    return result.stdout


def _docker(args: Sequence[str]) -> str:
    """Run Docker (see `_run`).

    Args:
        args: Arguments of `docker`.

    Returns:
        The standard output.
    """
    return _run("docker", args)


def _gh(args: Sequence[str]) -> str:
    """Run the GitHub CLI (see `_run`).

    Args:
        args: Arguments of `gh`.

    Returns:
        The standard output.
    """
    return _run("gh", args)


def tag_digest(reference: str, docker: Runner) -> str | None:
    """Return the digest that an image tag (or digest) points to.

    Args:
        reference: Image name and tag or digest, e.g.,
            `docker.io/o/i:1.2.0`.
        docker: Runs Docker.

    Returns:
        The digest of the manifest (or index); `None` if it doesn't exist.

    Raises:
        ReleaseError: If the registry can't be read (any error but a
            missing tag, so that an error never passes as "not released"),
            or the response has no digest.
    """
    args = [
        "buildx",
        "imagetools",
        "inspect",
        reference,
        "--format",
        "{{json .Manifest}}",
    ]
    try:
        output = docker(args)
    except ReleaseError as error:
        if NOT_FOUND.search(str(error)):
            return None
        raise ReleaseError(f"Could not read {reference}: {error}") from error
    try:
        digest = json.loads(output).get("digest")
    except (json.JSONDecodeError, AttributeError) as error:
        raise ReleaseError(f"Unexpected manifest of {reference}: {output!r}") from error
    if not isinstance(digest, str) or not DIGEST.fullmatch(digest):
        raise ReleaseError(f"Unexpected digest of {reference}: {digest!r}")
    return digest


def check(settings: Settings, docker: Runner = _docker) -> dict[str, str]:
    """Check that the version's image tag is free or points to the digest.

    Args:
        settings: The settings.
        docker: Runs Docker.

    Returns:
        The outputs: `version`.

    Raises:
        ReleaseError: If the digest isn't in the image's repository, the
            version's tag points to another digest, or the registry can't be
            read.
    """
    source = f"{settings.image}@{settings.digest}"
    if tag_digest(source, docker) != settings.digest:
        raise ReleaseError(
            f"{source} doesn't exist: push the image by digest first, to this"
            " image name"
        )
    reference = f"{settings.image}:{settings.version}"
    current = tag_digest(reference, docker)
    if current is not None and current != settings.digest:
        raise ReleaseError(
            f"{reference} already points to {current}, not to {settings.digest}:"
            " published versions never move (e.g., after re-running all jobs,"
            " which builds a new digest); re-run only the failed jobs, or"
            " release a new version"
        )
    if current is not None:
        print(
            f"::notice title={TITLE}::{reference} already points to the digest"
            " (an earlier attempt of this release)",
            file=sys.stderr,
        )
    return {"version": settings.version}


def _published(settings: Settings, gh: Runner) -> list[dict[str, object]]:
    """Return the published releases of the tag's prefix, by version.

    Args:
        settings: The settings.
        gh: Runs the GitHub CLI.

    Returns:
        The published releases (no drafts) whose tag has the prefix, each as
        `publish-release` reads them, with the version as `tag_name` and
        `prerelease` set if the version has a pre-release (see `is_latest`).

    Raises:
        ReleaseError: If the releases can't be read.
    """
    output = gh(
        [
            "api",
            "--paginate",
            "--slurp",
            f"repos/{settings.repository}/releases?per_page=100",
        ]
    )
    try:
        pages = json.loads(output)
        releases = [release for page in pages for release in page]
        names = [str(r["tag_name"]) for r in releases if not r.get("draft")]
    except (json.JSONDecodeError, TypeError, KeyError) as error:
        raise ReleaseError(f"Unexpected list of releases: {error}") from error
    return [
        {"tag_name": version, "prerelease": not _is_stable(version), "draft": False}
        for name in names
        if name.startswith(settings.prefix)
        and publish_release.parse_version(version := name[len(settings.prefix) :])
    ]


def _is_stable(version: str) -> bool:
    """Return whether a version has no pre-release (`a`, `b`, `rc`).

    Args:
        version: A version, e.g., `1.2.0` or `1.2.0rc1`.

    Returns:
        Whether it is a release version without a pre-release, in the order
        of `publish-release` (major version 0 included).
    """
    key = publish_release.parse_version(version)
    # Rank of "no pre-release" in publish-release's version order
    return key is not None and key[3] == publish_release._PRE_RANK[None]


def is_latest(
    settings: Settings, gh: Runner = _gh, docker: Runner = _docker
) -> tuple[bool, str]:
    """Return whether the release's image becomes `latest`, and why.

    The rule of `publish-release` (`is_latest`, the same code): `latest` if
    no published release has a higher version, among the stable versions
    (no pre-release). Unlike GitHub releases, whose pre-release flag
    `publish-release` sets for all versions below 1.0.0, stable versions
    below 1.0.0 count, so that repositories before 1.0.0 have a `latest`
    image. Higher stable versions whose release is not published yet (e.g.,
    a release still running) count if their image tag exists already, so
    that a release of a lower version that runs in between doesn't move
    `latest` back.

    Args:
        settings: The settings.
        gh: Runs the GitHub CLI.
        docker: Runs Docker.

    Returns:
        Whether to tag `latest`, and the reason.

    Raises:
        ReleaseError: If the releases, tags or image tags can't be read.
    """
    version = settings.version
    if settings.latest == "false":
        return False, "latest: false"
    if not _is_stable(version):
        return False, f"{version} is a pre-release"
    releases = _published(settings, gh)
    if not publish_release.is_latest(version, False, releases):
        return False, "a published release has a higher version"
    released = {str(r["tag_name"]) for r in releases}
    key = publish_release.parse_version(version)
    names = gh(
        [
            "api",
            "--paginate",
            f"repos/{settings.repository}/git/matching-refs/tags",
            "--jq",
            '.[].ref | ltrimstr("refs/tags/")',
        ]
    ).split()
    pending = sorted(
        (other_key, other)
        for name in names
        if name.startswith(settings.prefix)
        and (other := name[len(settings.prefix) :]) not in released
        and _is_stable(other)
        and (other_key := publish_release.parse_version(other)) > key
    )
    for _, other in reversed(pending):
        if tag_digest(f"{settings.image}:{other}", docker) is not None:
            return False, (
                f"{other} is tagged in the registry, but its release is not"
                " published yet"
            )
    return True, "highest stable release"


def tag(
    settings: Settings, gh: Runner = _gh, docker: Runner = _docker
) -> dict[str, str]:
    """Tag the digest with the version and, if it is the highest, `latest`.

    Args:
        settings: The settings.
        gh: Runs the GitHub CLI.
        docker: Runs Docker.

    Returns:
        The outputs: `version`, `latest` (`true` or `false`) and `tags` (the
        image references, space-separated).

    Raises:
        ReleaseError: If a tag can't be set, or doesn't point to the digest
            afterwards.
    """
    latest, reason = is_latest(settings, gh, docker)
    print(
        f"::notice title={TITLE}::latest {'set' if latest else 'not set'}: {reason}",
        file=sys.stderr,
    )
    source = f"{settings.image}@{settings.digest}"
    references = [f"{settings.image}:{settings.version}"]
    if latest:
        references.append(f"{settings.image}:latest")
    for reference in references:
        docker(["buildx", "imagetools", "create", "--tag", reference, source])
        actual = tag_digest(reference, docker)
        if actual != settings.digest:
            raise ReleaseError(
                f"{reference} points to {actual}, not to {settings.digest}"
            )
    return {
        "version": settings.version,
        "latest": str(latest).lower(),
        "tags": " ".join(references),
    }


def _annotation(message: str) -> str:
    """Return an error annotation, with the message escaped.

    Args:
        message: The message, possibly over several lines.

    Returns:
        The workflow command.
    """
    escaped = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return f"::error title={TITLE}::{escaped}"


def main(
    argv: Sequence[str] | None = None,
    env: dict[str, str] | None = None,
    gh: Runner = _gh,
    docker: Runner = _docker,
) -> int:
    """Run a command (see the module's docstring).

    Args:
        argv: Command-line arguments, without the program name; those of the
            process if `None`.
        env: Environment variables; those of the process if `None`.
        gh: Runs the GitHub CLI.
        docker: Runs Docker.

    Returns:
        The exit status: 0 on success, 1 on any error.
    """
    parser = argparse.ArgumentParser(description="Check and tag a release image.")
    parser.add_argument("command", choices=("check", "tag"))
    args = parser.parse_args(argv)
    env = dict(os.environ) if env is None else env
    try:
        settings = Settings.from_env(env)
        if args.command == "check":
            outputs = check(settings, docker)
        else:
            outputs = tag(settings, gh, docker)
    except ReleaseError as error:
        print(_annotation(str(error)), file=sys.stderr)
        return 1
    lines = "".join(f"{name}={value}\n" for name, value in outputs.items())
    print(lines, end="")
    if env.get("GITHUB_OUTPUT"):
        with open(env["GITHUB_OUTPUT"], "a", encoding="utf-8") as file:
            file.write(lines)
    return 0


if __name__ == "__main__":
    sys.exit(main())
