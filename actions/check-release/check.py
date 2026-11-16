#!/usr/bin/env python3
"""Check a release tag and its commit before anything of a release is built.

Run in the `prepare` job of a release workflow (see this action's README).
The release fails unless:

1. the tag is annotated, named as pushed, signed with a signature that
   GitHub verified, and points to the commit of the run;
2. the tag is a release version (`<prefix>MAJOR.MINOR.PATCH`, optionally
   with an `a`, `alpha`, `b`, `beta` or `rc` pre-release and its number);
3. the commit is on the release branch;
4. the CI workflow has a successful run for a push of the commit;
5. the citation metadata (`CITATION.cff`) of the commit has the version and
   a release date that is not in the future, and the package version that
   the caller passes, if any, is the version.

Everything is read from the GitHub API, nothing from the checkout, so that
the checks don't depend on the checkout and run nothing of the tagged
commit. All checks run, and each finding is printed as an error annotation
to standard error. On success, the outputs `version`, `prerelease` and
`sha` are written to `GITHUB_OUTPUT`.

The settings are read from the environment (see `Settings`). Needs Python
3.10 or later. Only the standard library and the GitHub CLI (`gh`) are used,
so that the action runs on GitHub-hosted Linux runners without installing
anything.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import shlex
import subprocess
import sys
import urllib.parse
from collections.abc import Callable, Sequence
from dataclasses import dataclass

TITLE = "Check release"

# Release versions after the tag prefix: `MAJOR.MINOR.PATCH` without leading
# zeros, optionally with a pre-release (`a`, `alpha`, `b`, `beta` or `rc`,
# with a number), e.g., `1.2.0`, `1.2.0rc1`, `2.0.0-alpha.50`, `1.0.0-rc1`
VERSION = re.compile(
    r"(?P<major>0|[1-9][0-9]*)\.(?P<minor>0|[1-9][0-9]*)\.(?P<patch>0|[1-9][0-9]*)"
    r"(?:[-.]?(?P<pre>a|alpha|b|beta|rc)[-.]?(?P<number>0|[1-9][0-9]*))?",
    re.ASCII,
)
# Inputs that go into API paths and queries
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", re.ASCII)
COMMIT = re.compile(r"[0-9a-f]{40}", re.ASCII)
# Branch names: no `..`, no leading or trailing `/` or `.` (git doesn't allow
# them in ref names either); tag prefixes may end with `/` or `.`
BRANCH = re.compile(r"(?![./])(?!.*\.\.)[A-Za-z0-9._/-]*(?<![/.])", re.ASCII)
PREFIX = re.compile(r"(?![./])(?!.*\.\.)[A-Za-z0-9._/-]*", re.ASCII)
WORKFLOW = re.compile(r"[A-Za-z0-9_.-]+", re.ASCII)
# Relative paths without `..` (empty for no check)
CITATION_PATH = re.compile(
    r"(?!/)(?!(?:.*/)?\.\.(?:/|$))[A-Za-z0-9_./-]*(?<!/)", re.ASCII
)
# Top-level keys of `CITATION.cff` that are checked, with a one-line scalar
# value (plain, or in single or double quotes) and an optional comment
CFF_KEY = re.compile(
    r"(?P<key>version|date-released)[ \t]*:[ \t]*"
    r"(?:\"(?P<double>[^\"\\]*)\"|'(?P<single>[^']*)'|(?P<plain>[^ \t#'\"][^#]*?))"
    r"[ \t]*(?:#.*)?",
    re.ASCII,
)
DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", re.ASCII)
# Latest time zone (UTC+14): a release date is in the future only if it is
# after the current date everywhere
LATEST_OFFSET = datetime.timedelta(hours=14)

Runner = Callable[[Sequence[str]], str]


class CheckError(Exception):
    """A reason not to release, with what to do about it."""


@dataclass(frozen=True)
class Settings:
    """Settings of the check, from the environment of the action's step.

    Attributes:
        repository: `<owner>/<repo>` (`GH_REPO`).
        tag: Name of the release's tag (`TAG`).
        commit: Commit SHA that the tag must point to (`COMMIT`).
        prefix: Part of the tag before the version (`TAG_PREFIX`), e.g.,
            `v` or `chart-v`.
        branch: Branch that the commit must be on (`BRANCH`).
        workflow: File name or ID of the CI workflow (`WORKFLOW`).
        ci_branch: Branch of the push that CI must have passed for
            (`CI_BRANCH`); empty for any branch.
        citation: Path of the citation metadata in the repository
            (`CITATION`); empty for no check.
        version: Package version that must equal the release version
            (`VERSION`); empty for no check.
    """

    repository: str
    tag: str
    commit: str
    prefix: str = "v"
    branch: str = "main"
    workflow: str = "ci.yml"
    ci_branch: str = "dev"
    citation: str = "CITATION.cff"
    version: str = ""

    @classmethod
    def from_env(cls, env: dict[str, str]) -> Settings:
        """Read and validate the settings from environment variables.

        Args:
            env: Environment variables.

        Returns:
            The settings.

        Raises:
            CheckError: If a required setting is missing or a setting is
                malformed.
        """
        required = ("GH_REPO", "TAG", "COMMIT", "BRANCH", "WORKFLOW")
        missing = [name for name in required if not env.get(name, "").strip()]
        if missing:
            raise CheckError(f"Not set: {', '.join(missing)}")
        settings = cls(
            repository=env["GH_REPO"].strip(),
            tag=env["TAG"].strip(),
            commit=env["COMMIT"].strip(),
            prefix=env.get("TAG_PREFIX", "").strip(),
            branch=env["BRANCH"].strip(),
            workflow=env["WORKFLOW"].strip(),
            ci_branch=env.get("CI_BRANCH", "").strip(),
            citation=env.get("CITATION", "").strip(),
            version=env.get("VERSION", "").strip(),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        """Check that the settings are well-formed.

        Raises:
            CheckError: For the first malformed setting.
        """
        checks = (
            (REPOSITORY, self.repository, "repository", "<owner>/<repo>"),
            (COMMIT, self.commit, "commit", "a full, lower-case commit SHA"),
            (PREFIX, self.prefix, "tag-prefix", "e.g., v or chart-v"),
            (BRANCH, self.branch, "branch", "a branch name"),
            (WORKFLOW, self.workflow, "workflow", "e.g., ci.yml"),
            (BRANCH, self.ci_branch, "ci-branch", "a branch name, or empty"),
            (CITATION_PATH, self.citation, "citation", "a file path, or empty"),
        )
        for pattern, value, name, expected in checks:
            if not pattern.fullmatch(value):
                raise CheckError(f"Invalid {name} '{value}': expected {expected}")


def release_version(tag: str, prefix: str) -> str:
    """Return the version of a release tag.

    Args:
        tag: Name of the tag, e.g., `v1.2.0` or `chart-v1.0.0rc1`.
        prefix: Part of the tag before the version, e.g., `v` or `chart-v`.

    Returns:
        The tag without the prefix, e.g., `1.2.0`.

    Raises:
        CheckError: If the tag doesn't start with the prefix, or the rest is
            no release version (`VERSION`).
    """
    if not tag.startswith(prefix) or not VERSION.fullmatch(tag[len(prefix) :]):
        raise CheckError(
            f"Tag '{tag}' is no release version: expected"
            f" {prefix}MAJOR.MINOR.PATCH, optionally with a pre-release"
            f" (e.g., {prefix}1.2.0, {prefix}1.2.0rc1, {prefix}1.2.0-beta.2)"
        )
    return tag[len(prefix) :]


def is_prerelease(version: str) -> bool:
    """Return whether a release version is a pre-release.

    The rule of `publish-release`'s `prerelease: auto`.

    Args:
        version: A release version (`VERSION`).

    Returns:
        Whether the major version is 0 or the version has a pre-release.

    Raises:
        ValueError: If the version is no release version.
    """
    match = VERSION.fullmatch(version)
    if not match:
        raise ValueError(f"No release version: {version}")
    return match["major"] == "0" or match["pre"] is not None


def _gh(args: Sequence[str]) -> str:
    """Run the GitHub CLI and return its standard output.

    Args:
        args: Arguments of `gh`.

    Returns:
        The standard output.

    Raises:
        CheckError: If `gh` fails; with its standard error.
    """
    result = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise CheckError(f"{shlex.join(['gh', *args])} failed: {result.stderr.strip()}")
    return result.stdout


def _api(gh: Runner, path: str) -> dict[str, object]:
    """Read a JSON object from the GitHub REST API.

    Args:
        gh: Runs the GitHub CLI.
        path: Path of the endpoint, with its query.

    Returns:
        The response.

    Raises:
        CheckError: If the call fails or the response is no JSON object.
    """
    output = gh(["api", path])
    try:
        response = json.loads(output)
    except json.JSONDecodeError as error:
        raise CheckError(f"Unexpected response of {path}: {error}") from error
    if not isinstance(response, dict):
        raise CheckError(f"Unexpected response of {path}: no object")
    return response


def _quote(text: str) -> str:
    """Quote text for a path of the GitHub API, keeping slashes.

    Args:
        text: A tag, branch or file path.

    Returns:
        The quoted text.
    """
    return urllib.parse.quote(text, safe="/")


def check_tag(settings: Settings, gh: Runner) -> None:
    """Check that the tag is annotated, signed and points to the commit.

    Args:
        settings: The settings.
        gh: Runs the GitHub CLI.

    Raises:
        CheckError: If the tag doesn't exist, is not annotated, has no
            signature that GitHub verified, names another tag, or doesn't
            point to the commit.
    """
    repo, tag = settings.repository, settings.tag
    try:
        ref = _api(gh, f"repos/{repo}/git/ref/tags/{_quote(tag)}")
    except CheckError as error:
        raise CheckError(f"Could not look up the tag '{tag}': {error}") from error
    target = ref.get("object")
    if not isinstance(target, dict) or ref.get("ref") != f"refs/tags/{tag}":
        raise CheckError(f"Unexpected response for the tag '{tag}': {ref}")
    if target.get("type") != "tag":
        raise CheckError(f"Tag '{tag}' is not annotated: tag with git tag -s")
    object_sha = target.get("sha")
    if not isinstance(object_sha, str) or not COMMIT.fullmatch(object_sha):
        raise CheckError(f"Unexpected response for the tag '{tag}': {ref}")
    tag_object = _api(gh, f"repos/{repo}/git/tags/{object_sha}")
    verification = tag_object.get("verification")
    if not isinstance(verification, dict) or verification.get("verified") is not True:
        reason = verification.get("reason") if isinstance(verification, dict) else None
        raise CheckError(
            f"Tag '{tag}' has no signature that GitHub verified ({reason}): sign"
            " it with git tag -s and a key registered with GitHub"
        )
    if tag_object.get("tag") != tag:
        raise CheckError(
            f"Tag '{tag}' points to a tag object named '{tag_object.get('tag')}'"
        )
    pointee = tag_object.get("object")
    if not isinstance(pointee, dict) or pointee.get("type") != "commit":
        raise CheckError(f"Tag '{tag}' doesn't point to a commit")
    if pointee.get("sha") != settings.commit:
        raise CheckError(
            f"Tag '{tag}' points to {pointee.get('sha')}, not to the commit of"
            f" the run ({settings.commit}); was it moved?"
        )


def check_branch(settings: Settings, gh: Runner) -> None:
    """Check that the commit is on the release branch.

    Args:
        settings: The settings.
        gh: Runs the GitHub CLI.

    Raises:
        CheckError: If the commit is not the head of the branch or one of
            its ancestors, or the comparison fails.
    """
    branch, commit = settings.branch, settings.commit
    path = f"repos/{settings.repository}/compare/{_quote(branch)}...{commit}?per_page=1"
    try:
        status = _api(gh, path).get("status")
    except CheckError as error:
        raise CheckError(
            f"Could not compare {commit} with '{branch}': {error}"
        ) from error
    if status not in ("identical", "behind"):
        raise CheckError(
            f"Release commit {commit} is not on '{branch}' (status: {status}):"
            f" merge it into '{branch}', then re-run this workflow"
        )


def check_ci(settings: Settings, gh: Runner) -> None:
    """Check that the CI workflow passed for a push of the commit.

    Runs for pull requests test merge commits, not the commit itself, so
    only runs for pushes count; re-runs that succeeded count.

    Args:
        settings: The settings.
        gh: Runs the GitHub CLI.

    Raises:
        CheckError: If there is no such run, or the lookup fails.
    """
    query = {
        "head_sha": settings.commit,
        "event": "push",
        "status": "success",
        "per_page": "1",
    }
    if settings.ci_branch:
        query["branch"] = settings.ci_branch
    path = (
        f"repos/{settings.repository}/actions/workflows/"
        f"{_quote(settings.workflow)}/runs?{urllib.parse.urlencode(query)}"
    )
    try:
        count = _api(gh, path).get("total_count")
    except CheckError as error:
        raise CheckError(
            f"Could not look up the runs of {settings.workflow}: {error}"
        ) from error
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        push = f"a push of {settings.commit}"
        if settings.ci_branch:
            push += f" to '{settings.ci_branch}'"
        raise CheckError(
            f"No successful run of the CI workflow ({settings.workflow}) for"
            f" {push}; once CI passed for it, re-run this workflow"
        )


def read_citation(text: str) -> dict[str, str]:
    """Read the top-level `version` and `date-released` of citation metadata.

    Only one-line scalars are read (plain or quoted), which is how
    `CITATION.cff` files set them; no YAML parser is needed.

    Args:
        text: Content of `CITATION.cff`.

    Returns:
        The values found, by key.

    Raises:
        CheckError: If a key is set twice, or its value is not a one-line
            scalar.
    """
    values: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        key = line.split(":", 1)[0].strip()
        if line[:1] in (" ", "\t") or key not in ("version", "date-released"):
            continue
        match = CFF_KEY.fullmatch(line.rstrip())
        if not match:
            raise CheckError(
                f"Line {number} of the citation metadata: {key} must be a"
                f" one-line value, e.g., {key}: "
                + ("1.2.0" if key == "version" else "2026-01-31")
            )
        if key in values:
            raise CheckError(f"Line {number} of the citation metadata: {key} set twice")
        values[key] = next(
            value
            for value in match.group("double", "single", "plain")
            if value is not None
        )
    return values


def check_citation(
    settings: Settings, version: str, now: datetime.datetime, gh: Runner
) -> list[str]:
    """Check the citation metadata of the commit against the version.

    Args:
        settings: The settings.
        version: The release version.
        now: The current time (aware).
        gh: Runs the GitHub CLI.

    Returns:
        The findings: version not the release version, release date
        missing, malformed or in the future.

    Raises:
        CheckError: If the file can't be read or parsed.
    """
    path = (
        f"repos/{settings.repository}/contents/{_quote(settings.citation)}"
        f"?ref={settings.commit}"
    )
    try:
        text = gh(["api", "-H", "Accept: application/vnd.github.raw+json", path])
    except CheckError as error:
        raise CheckError(
            f"Could not read {settings.citation} of {settings.commit}: {error}"
        ) from error
    values = read_citation(text)
    findings = []
    cited = values.get("version")
    if cited != version:
        findings.append(
            f"{settings.citation} has version '{cited or ''}', expected"
            f" '{version}': set it in the release-prep pull request"
        )
    released = values.get("date-released", "")
    try:
        date = (
            datetime.date.fromisoformat(released) if DATE.fullmatch(released) else None
        )
    except ValueError:
        date = None
    if date is None:
        findings.append(
            f"{settings.citation} has no valid date-released ('{released}'):"
            " set it (YYYY-MM-DD) in the release-prep pull request"
        )
    elif date > (now + LATEST_OFFSET).date():
        findings.append(f"{settings.citation} has date-released {date} in the future")
    return findings


def check(
    settings: Settings, gh: Runner = _gh, now: datetime.datetime | None = None
) -> tuple[list[str], dict[str, str]]:
    """Run all checks of the release.

    Args:
        settings: The settings.
        gh: Runs the GitHub CLI.
        now: The current time (aware); default is now.

    Returns:
        The findings (empty if the release may go ahead) and the outputs
        (`version`, `prerelease`, `sha`; empty if there are findings).
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    findings: list[str] = []
    version = ""
    try:
        version = release_version(settings.tag, settings.prefix)
    except CheckError as error:
        findings.append(str(error))
    for step in (check_tag, check_branch, check_ci):
        try:
            step(settings, gh)
        except CheckError as error:
            findings.append(str(error))
    if version and settings.version and settings.version != version:
        findings.append(
            f"Package version is '{settings.version}', expected '{version}' (the"
            " tag's): set it in the release-prep pull request"
        )
    if version and settings.citation:
        try:
            findings.extend(check_citation(settings, version, now, gh))
        except CheckError as error:
            findings.append(str(error))
    if findings:
        return findings, {}
    return [], {
        "version": version,
        "prerelease": str(is_prerelease(version)).lower(),
        "sha": settings.commit,
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
    env: dict[str, str] | None = None,
    gh: Runner = _gh,
    now: datetime.datetime | None = None,
) -> int:
    """Check the release (see the module's docstring).

    Args:
        env: Environment variables; those of the process if `None`.
        gh: Runs the GitHub CLI.
        now: The current time (aware); default is now.

    Returns:
        The exit status: 0 if the release may go ahead, 1 otherwise.
    """
    env = dict(os.environ) if env is None else env
    try:
        settings = Settings.from_env(env)
    except CheckError as error:
        print(_annotation(str(error)), file=sys.stderr)
        return 1
    findings, outputs = check(settings, gh, now)
    for finding in findings:
        print(_annotation(finding), file=sys.stderr)
    if findings:
        return 1
    lines = "".join(f"{name}={value}\n" for name, value in outputs.items())
    print(lines, end="")
    if env.get("GITHUB_OUTPUT"):
        with open(env["GITHUB_OUTPUT"], "a", encoding="utf-8") as file:
            file.write(lines)
    return 0


if __name__ == "__main__":
    sys.exit(main())
