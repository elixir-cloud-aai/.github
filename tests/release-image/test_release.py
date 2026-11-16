"""Tests of the script of the `release-image` action (`release.py`)."""

from __future__ import annotations

import dataclasses
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from collections.abc import Sequence
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, ClassVar
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "actions/release-image/release.py"
PUBLISH = ROOT / "actions/publish-release/publish.py"


def _load(name: str, path: Path) -> types.ModuleType:
    """Load a script of an action as a module (the directories aren't packages).

    Args:
        name: Name of the module.
        path: Path of the script.

    Returns:
        The module.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


release = _load("release", SCRIPT)
publish = _load("publish", PUBLISH)

REPO = "o/r"
IMAGE = "docker.io/org/app"
DIGEST = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64
RELEASES_PATH = f"repos/{REPO}/releases?per_page=100"
TAGS_PATH = f"repos/{REPO}/git/matching-refs/tags"


def _settings(**changes: str) -> Any:
    """Return settings of a release of `v1.2.0`, with changes.

    Args:
        **changes: Settings to change.

    Returns:
        The settings.
    """
    return dataclasses.replace(
        release.Settings(image=IMAGE, digest=DIGEST, tag="v1.2.0", repository=REPO),
        **changes,
    )


def _release(tag: str, *, draft: bool = False, prerelease: bool = False) -> dict:
    """Return a release as the REST API lists it.

    Args:
        tag: Name of its tag.
        draft: Whether it is a draft.
        prerelease: Whether it is a pre-release.

    Returns:
        The release.
    """
    return {"tag_name": tag, "draft": draft, "prerelease": prerelease}


class FakeGh:
    """A stand-in for the GitHub CLI with releases and tags.

    Attributes:
        releases: Releases of the repository (pages of the REST API).
        tags: Names of the repository's tags.
        calls: Arguments of each call.
    """

    def __init__(
        self, releases: list[dict] | None = None, tags: list[str] | None = None
    ) -> None:
        """Set the releases and tags.

        Args:
            releases: Releases; default is `v1.1.0`, published.
            tags: Tag names; default is those of the releases plus `v1.2.0`.
        """
        self.releases = [_release("v1.1.0")] if releases is None else releases
        self.tags = (
            [str(r["tag_name"]) for r in self.releases] + ["v1.2.0"]
            if tags is None
            else tags
        )
        self.calls: list[list[str]] = []

    def __call__(self, args: Sequence[str]) -> str:
        """Answer a call like `gh api` would.

        Args:
            args: Arguments of `gh`.

        Returns:
            The output of the call.

        Raises:
            AssertionError: For unexpected calls.
        """
        args = list(args)
        self.calls.append(args)
        if args == ["api", "--paginate", "--slurp", RELEASES_PATH]:
            # Two pages, as `--slurp` returns them
            middle = len(self.releases) // 2
            return json.dumps([self.releases[:middle], self.releases[middle:]])
        if args[:3] == ["api", "--paginate", TAGS_PATH]:
            return "".join(f"{tag}\n" for tag in self.tags)
        raise AssertionError(f"Unexpected call: {args}")


class FakeDocker:
    """A stand-in for `docker buildx imagetools` with a registry in memory.

    Attributes:
        manifests: Digests by reference (`<image>:<tag>` or
            `<image>@<digest>`).
        calls: Arguments of each call.
        error: Error to raise for every `inspect`, if any.
        broken: References that `create` doesn't move (to test the check
            after tagging).
    """

    def __init__(self, manifests: dict[str, str] | None = None) -> None:
        """Set the registry's content.

        Args:
            manifests: Digests by tag reference; the digest `DIGEST` is
                always pushed.
        """
        self.manifests = {f"{IMAGE}@{DIGEST}": DIGEST, **(manifests or {})}
        self.calls: list[list[str]] = []
        self.error: str | None = None
        self.broken: set[str] = set()

    def __call__(self, args: Sequence[str]) -> str:
        """Answer a call like `docker` would.

        Args:
            args: Arguments of `docker`.

        Returns:
            The output of the call.

        Raises:
            ReleaseError: For missing references, as `docker` fails for them.
            AssertionError: For unexpected calls.
        """
        args = list(args)
        self.calls.append(args)
        match args:
            case [
                "buildx",
                "imagetools",
                "inspect",
                ref,
                "--format",
                "{{json .Manifest}}",
            ]:
                if self.error:
                    raise release.ReleaseError(self.error)
                if ref not in self.manifests:
                    raise release.ReleaseError(f"ERROR: {ref}: not found")
                return (
                    json.dumps(
                        {
                            "mediaType": "application/vnd.oci.image.index.v1+json",
                            "digest": self.manifests[ref],
                            "size": 1,
                        }
                    )
                    + "\n"
                )
            case ["buildx", "imagetools", "create", "--tag", ref, source]:
                if ref not in self.broken:
                    self.manifests[ref] = self.manifests[source]
                return ""
        raise AssertionError(f"Unexpected call: {args}")

    def created(self) -> list[str]:
        """Return the references that were tagged.

        Returns:
            The references, in order.
        """
        return [c[4] for c in self.calls if c[2] == "create"]


class TestSettings(unittest.TestCase):
    """Reading and validating the settings."""

    ENV: ClassVar[dict[str, str]] = {
        "IMAGE": IMAGE,
        "DIGEST": DIGEST,
        "TAG": "v1.2.0",
        "TAG_PREFIX": "v",
        "LATEST": "auto",
        "GH_REPO": REPO,
    }

    def test_valid(self) -> None:
        """Good settings are read, stripped, with the version of the tag."""
        env = {name: f" {value} " for name, value in self.ENV.items()}
        settings = release.Settings.from_env(env)
        self.assertEqual(settings, _settings())
        self.assertEqual(settings.version, "1.2.0")
        for image in [
            "docker.io/elixircloud/tesk-api",
            "ghcr.io/elixir-cloud-aai/krini",
            "localhost:5000/release-image-test",
            "registry:5000/a/b/c",
            "quay.io/o/a_b__c-d.e",
        ]:
            with self.subTest(image=image):
                release.Settings.from_env({**self.ENV, "IMAGE": image})

    def test_prefix(self) -> None:
        """The version is the tag without the prefix (none for an empty one)."""
        cases = {
            ("foca-plugin-x-v1.2.0rc1", "foca-plugin-x-v"): "1.2.0rc1",
            ("1.2.0", ""): "1.2.0",
            ("chart-v0.1.0", "chart-v"): "0.1.0",
        }
        for (tag, prefix), version in cases.items():
            with self.subTest(tag=tag):
                env = {**self.ENV, "TAG": tag, "TAG_PREFIX": prefix}
                self.assertEqual(release.Settings.from_env(env).version, version)

    def test_latest_false(self) -> None:
        """With `latest: false`, no repository is needed."""
        env = {**self.ENV, "LATEST": "false", "GH_REPO": ""}
        self.assertEqual(release.Settings.from_env(env).latest, "false")

    def test_missing(self) -> None:
        """Missing required settings fail together."""
        with self.assertRaisesRegex(
            release.ReleaseError, "Not set: IMAGE, DIGEST, TAG, LATEST, GH_REPO"
        ):
            release.Settings.from_env({})

    def test_invalid(self) -> None:
        """Malformed settings fail with what is expected."""
        cases = {
            "IMAGE": [
                "elixircloud/tesk-api",
                "tesk-api",
                "docker.io/elixircloud/tesk-api:1.2.0",
                f"docker.io/elixircloud/tesk-api@{DIGEST}",
                "docker.io/Elixircloud/tesk-api",
                "docker.io/",
                "docker.io/a/-b",
                "docker.io/a b",
                "https://docker.io/a",
                "docker.io/a\nb",
            ],
            "DIGEST": [
                "a" * 64,
                "sha256:" + "a" * 63,
                "sha256:" + "A" * 64,
                "sha512:" + "a" * 64,
                DIGEST + "\nx",
            ],
            "TAG": ["v1.2", "1.2.0", "v1.2.0.dev1", "chart-v1.2.0", "v1.2.0 x"],
            "TAG_PREFIX": ["../v", "/v"],
            "LATEST": ["true", "Auto", "no"],
            "GH_REPO": ["o", "o/r/x", "o/r?x"],
        }
        for name, values in cases.items():
            for value in values:
                with (
                    self.subTest(name=name, value=value),
                    self.assertRaises(release.ReleaseError),
                ):
                    release.Settings.from_env({**self.ENV, name: value})


class TestModules(unittest.TestCase):
    """The rules of the other actions are used, not copied."""

    def test_same_code(self) -> None:
        """`latest` comes from publish-release, versions from check-release."""
        self.assertEqual(
            Path(release.publish_release.__file__),
            ROOT / "actions/publish-release/publish.py",
        )
        self.assertEqual(
            Path(release.check_release.__file__),
            ROOT / "actions/check-release/check.py",
        )
        self.assertTrue(callable(release.publish_release.is_latest))

    def test_stable(self) -> None:
        """Stable versions have no pre-release, in publish-release's order."""
        for version in ["0.1.0", "1.2.0", "10.0.0", "1.2"]:
            with self.subTest(version=version):
                self.assertTrue(release._is_stable(version))
        for version in ["1.2.0rc1", "1.2.0a0", "2.0.0-beta.1", "x", ""]:
            with self.subTest(version=version):
                self.assertFalse(release._is_stable(version))


class TestCheck(unittest.TestCase):
    """The check before attesting and signing."""

    def test_new_version(self) -> None:
        """A version without an image tag passes."""
        docker = FakeDocker()
        self.assertEqual(release.check(_settings(), docker), {"version": "1.2.0"})
        self.assertEqual(
            [c[3] for c in docker.calls], [f"{IMAGE}@{DIGEST}", f"{IMAGE}:1.2.0"]
        )

    def test_rerun(self) -> None:
        """A version tag of the same digest passes (a re-run), with a notice."""
        docker = FakeDocker({f"{IMAGE}:1.2.0": DIGEST})
        err = io.StringIO()
        with redirect_stderr(err):
            release.check(_settings(), docker)
        self.assertIn("::notice", err.getvalue())

    def test_other_digest(self) -> None:
        """A version tag of another digest fails."""
        docker = FakeDocker({f"{IMAGE}:1.2.0": OTHER})
        with self.assertRaisesRegex(
            release.ReleaseError, f"already points to {OTHER}.*never move"
        ):
            release.check(_settings(), docker)

    def test_missing_digest(self) -> None:
        """A digest that isn't in the image's repository fails."""
        docker = FakeDocker()
        with self.assertRaisesRegex(release.ReleaseError, "doesn't exist: push"):
            release.check(_settings(digest=OTHER), docker)

    def test_registry_error(self) -> None:
        """Registry errors other than a missing tag fail."""
        docker = FakeDocker()
        docker.error = "ERROR: unauthorized: authentication required"
        with self.assertRaisesRegex(
            release.ReleaseError, "Could not read.*unauthorized"
        ):
            release.check(_settings(), docker)

    def test_not_found_messages(self) -> None:
        """Both registries' messages for missing tags count as missing."""
        for message in ["ERROR: x: not found", "MANIFEST_UNKNOWN: manifest unknown"]:
            with self.subTest(message=message):
                docker = FakeDocker()
                docker.error = message
                self.assertIsNone(release.tag_digest(f"{IMAGE}:1.2.0", docker))

    def test_bad_manifest(self) -> None:
        """Output without a digest fails."""
        for output in ["", "[]", '{"digest": "x"}', "{}"]:
            with (
                self.subTest(output=output),
                self.assertRaisesRegex(release.ReleaseError, "Unexpected"),
            ):
                release.tag_digest("x", lambda args, output=output: output)


class TestLatest(unittest.TestCase):
    """The decision on `latest`."""

    def _latest(
        self, gh: FakeGh, docker: FakeDocker | None = None, **changes: str
    ) -> bool:
        """Return the decision.

        Args:
            gh: Stand-in for `gh`.
            docker: Stand-in for `docker`; default is an empty registry.
            **changes: Settings to change.

        Returns:
            Whether to tag `latest`.
        """
        latest, reason = release.is_latest(
            _settings(**changes), gh, docker or FakeDocker()
        )
        self.assertTrue(reason)
        return bool(latest)

    def test_highest(self) -> None:
        """The highest stable release becomes `latest`."""
        self.assertTrue(self._latest(FakeGh()))
        self.assertTrue(self._latest(FakeGh([])))

    def test_lower(self) -> None:
        """A patch of an older line doesn't; drafts don't count."""
        self.assertFalse(self._latest(FakeGh([_release("v1.3.0")])))
        self.assertTrue(self._latest(FakeGh([_release("v1.3.0", draft=True)])))

    def test_prerelease(self) -> None:
        """Pre-releases never become `latest`; published ones don't count."""
        self.assertFalse(self._latest(FakeGh(), tag="v1.2.0rc1"))
        gh = FakeGh([_release("v1.3.0rc1", prerelease=True)])
        self.assertTrue(self._latest(gh))
        self.assertEqual(len(gh.calls), 2)

    def test_major_zero(self) -> None:
        """Below 1.0.0, stable versions count, though GitHub pre-releases."""
        gh = FakeGh([_release("v0.21.0", prerelease=True)])
        self.assertTrue(self._latest(gh, tag="v0.22.0"))
        gh = FakeGh([_release("v0.22.0", prerelease=True)])
        self.assertFalse(self._latest(gh, tag="v0.21.1"))

    def test_same_as_publish_release(self) -> None:
        """From 1.0.0, the decision is publish-release's `is_latest`."""
        tags = ["v1.0.0", "v1.1.0", "v1.2.0", "v1.2.1", "v2.0.0", "v1.10.0"]
        for tag in tags:
            for highest in tags:
                releases = [_release(highest)]
                with self.subTest(tag=tag, highest=highest):
                    self.assertEqual(
                        self._latest(FakeGh(releases, [highest, tag]), tag=tag),
                        publish.is_latest(tag, False, releases),
                    )

    def test_never(self) -> None:
        """With `latest: false`, nothing is read."""
        gh = FakeGh()
        self.assertFalse(self._latest(gh, latest="false"))
        self.assertEqual(gh.calls, [])

    def test_prefix(self) -> None:
        """Only releases and tags with the prefix count."""
        releases = [_release("v9.0.0"), _release("chart-v1.0.0")]
        gh = FakeGh(releases, ["v9.0.0", "chart-v1.0.0", "chart-v1.2.0"])
        self.assertTrue(self._latest(gh, tag="chart-v1.2.0", prefix="chart-v"))
        releases = [_release("chart-v1.3.0"), _release("v1.0.0")]
        gh = FakeGh(releases)
        self.assertFalse(self._latest(gh, tag="chart-v1.2.0", prefix="chart-v"))

    def test_empty_prefix(self) -> None:
        """Without a prefix, tags of plain versions count."""
        gh = FakeGh([_release("1.3.0"), _release("v9.0.0")], ["1.3.0", "1.2.0"])
        self.assertFalse(self._latest(gh, tag="1.2.0", prefix=""))

    def test_pending_release(self) -> None:
        """A higher version tagged in the registry, not yet released, wins."""
        gh = FakeGh([_release("v1.1.0")], ["v1.1.0", "v1.2.0", "v1.3.0", "v1.4.0"])
        docker = FakeDocker({f"{IMAGE}:1.3.0": OTHER})
        self.assertFalse(self._latest(gh, docker))
        self.assertEqual(
            [c[3] for c in docker.calls], [f"{IMAGE}:1.4.0", f"{IMAGE}:1.3.0"]
        )

    def test_abandoned_tag(self) -> None:
        """A higher tag without image (e.g., a failed release) doesn't count."""
        gh = FakeGh([_release("v1.1.0")], ["v1.1.0", "v1.2.0", "v1.3.0", "v2.0.0rc1"])
        docker = FakeDocker({f"{IMAGE}:2.0.0rc1": OTHER})
        self.assertTrue(self._latest(gh, docker))
        self.assertEqual([c[3] for c in docker.calls], [f"{IMAGE}:1.3.0"])

    def test_unexpected_releases(self) -> None:
        """A malformed list of releases fails."""
        gh = FakeGh()
        with (
            mock.patch.object(gh, "releases", [{"draft": False}]),
            self.assertRaisesRegex(release.ReleaseError, "Unexpected list"),
        ):
            self._latest(gh)


class TestTag(unittest.TestCase):
    """Tagging and checking the tags."""

    def test_latest(self) -> None:
        """The highest release gets the version and `latest`."""
        docker = FakeDocker()
        err = io.StringIO()
        with redirect_stderr(err):
            outputs = release.tag(_settings(), FakeGh(), docker)
        self.assertEqual(
            outputs,
            {
                "version": "1.2.0",
                "latest": "true",
                "tags": f"{IMAGE}:1.2.0 {IMAGE}:latest",
            },
        )
        self.assertEqual(docker.created(), [f"{IMAGE}:1.2.0", f"{IMAGE}:latest"])
        self.assertEqual(docker.manifests[f"{IMAGE}:latest"], DIGEST)
        self.assertIn("latest set: highest stable release", err.getvalue())

    def test_version_only(self) -> None:
        """Lower releases get the version only; `latest` stays."""
        docker = FakeDocker({f"{IMAGE}:latest": OTHER})
        with redirect_stderr(io.StringIO()):
            outputs = release.tag(_settings(), FakeGh([_release("v1.3.0")]), docker)
        self.assertEqual(outputs["latest"], "false")
        self.assertEqual(docker.created(), [f"{IMAGE}:1.2.0"])
        self.assertEqual(docker.manifests[f"{IMAGE}:latest"], OTHER)

    def test_not_moved(self) -> None:
        """A tag that doesn't point to the digest afterwards fails."""
        docker = FakeDocker({f"{IMAGE}:latest": OTHER})
        docker.broken.add(f"{IMAGE}:latest")
        with (
            redirect_stderr(io.StringIO()),
            self.assertRaisesRegex(
                release.ReleaseError, f"{IMAGE}:latest points to {OTHER}"
            ),
        ):
            release.tag(_settings(), FakeGh(), docker)


class TestMain(unittest.TestCase):
    """The script as the action runs it."""

    def setUp(self) -> None:
        """Create a scratch directory and the environment of a release."""
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.output = self.path / "output"
        self.env = {**TestSettings.ENV, "GITHUB_OUTPUT": str(self.output)}

    def _main(
        self, command: str, gh: FakeGh | None = None, docker: FakeDocker | None = None
    ) -> tuple[int, str, str]:
        """Run `main`.

        Args:
            command: `check` or `tag`.
            gh: Stand-in for `gh`; default has `v1.1.0` released.
            docker: Stand-in for `docker`; default is an empty registry.

        Returns:
            The exit status, standard output and standard error.
        """
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = release.main(
                [command], self.env, gh or FakeGh(), docker or FakeDocker()
            )
        return status, out.getvalue(), err.getvalue()

    def test_check(self) -> None:
        """`check` writes the version."""
        self.assertEqual(self._main("check"), (0, "version=1.2.0\n", ""))
        self.assertEqual(self.output.read_text(encoding="utf-8"), "version=1.2.0\n")

    def test_tag(self) -> None:
        """`tag` writes the version, `latest` and the tags."""
        status, out, _ = self._main("tag")
        lines = f"version=1.2.0\nlatest=true\ntags={IMAGE}:1.2.0 {IMAGE}:latest\n"
        self.assertEqual((status, out), (0, lines))
        self.assertEqual(self.output.read_text(encoding="utf-8"), lines)
        # Outside GitHub Actions, only to standard output
        del self.env["GITHUB_OUTPUT"]
        self.assertEqual(self._main("tag")[:2], (0, lines))

    def test_error(self) -> None:
        """Errors are one escaped annotation; no outputs are written."""
        docker = FakeDocker({f"{IMAGE}:1.2.0": OTHER})
        docker.error = "50%\r\n::error::x"
        status, out, err = self._main("check", docker=docker)
        self.assertEqual((status, out), (1, ""))
        self.assertEqual(err.count("\n"), 1)
        self.assertTrue(err.startswith("::error title=Release image::"), err)
        self.assertIn("50%25%0D%0A::error::x", err)
        self.assertFalse(self.output.exists())

    def test_invalid_settings(self) -> None:
        """Invalid settings fail before any call."""
        self.env["DIGEST"] = "latest"
        gh, docker = FakeGh(), FakeDocker()
        status, _, err = self._main("tag", gh, docker)
        self.assertEqual(status, 1)
        self.assertIn("::error title=Release image::Invalid digest 'latest'", err)
        self.assertEqual((gh.calls, docker.calls), ([], []))

    def test_script(self) -> None:
        """The script runs as the action calls it, with stand-ins on the path."""
        bin_dir = self.path / "bin"
        bin_dir.mkdir()
        log = self.path / "calls"
        manifest = json.dumps({"digest": DIGEST})
        (bin_dir / "docker").write_text(
            "#!/bin/sh\n"
            f'echo "docker $*" >> "{log}"\n'
            # The version's tag exists once it was created
            'case "$3 $4" in\n'
            f'  "inspect {IMAGE}:1.2.0") if ! grep -q create "{log}"; then\n'
            '      echo "ERROR: not found" >&2; exit 1; fi\n'
            f"    echo '{manifest}' ;;\n"
            f"  inspect*) echo '{manifest}' ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        (bin_dir / "gh").write_text(
            f'#!/bin/sh\necho "gh $*" >> "{log}"\n'
            'case "$*" in *releases*) echo "[[]]" ;; esac\n',
            encoding="utf-8",
        )
        for stub in bin_dir.iterdir():
            stub.chmod(0o755)
        env = {**self.env, "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"}
        for command in ("check", "tag"):
            result = subprocess.run(
                [sys.executable, "-I", str(SCRIPT), command],
                capture_output=True,
                text=True,
                cwd=self.path,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.output.read_text(encoding="utf-8"),
            "version=1.2.0\n"
            f"version=1.2.0\nlatest=true\ntags={IMAGE}:1.2.0 {IMAGE}:latest\n",
        )
        calls = log.read_text(encoding="utf-8").splitlines()
        self.assertIn(
            f"docker buildx imagetools create --tag {IMAGE}:latest {IMAGE}@{DIGEST}",
            calls,
        )
        self.assertEqual(len(calls), 8, calls)

    def test_run(self) -> None:
        """`_run` returns the output of a program, and fails with its error."""
        self.assertEqual(release._run("sh", ["-c", "echo out"]), "out\n")
        with self.assertRaisesRegex(release.ReleaseError, "failed: bad"):
            release._run("sh", ["-c", "echo bad >&2; exit 1"])
        with mock.patch.object(release, "_run", return_value="x") as run:
            self.assertEqual(release._docker(["a"]), "x")
            self.assertEqual(release._gh(["b"]), "x")
        self.assertEqual(
            run.call_args_list, [mock.call("docker", ["a"]), mock.call("gh", ["b"])]
        )

    def test_load(self) -> None:
        """A script of another action that can't be loaded fails the import."""
        with self.assertRaises(ImportError):
            release._load("missing", self.path / "missing.txt")


if __name__ == "__main__":
    unittest.main()
