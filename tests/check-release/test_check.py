"""Tests of the script of the `check-release` action (`check.py`)."""

from __future__ import annotations

import dataclasses
import datetime
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Sequence
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "actions/check-release/check.py"
PUBLISH = ROOT / "actions/publish-release/publish.py"


def _load(name: str, path: Path) -> object:
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


check = _load("check", SCRIPT)
publish = _load("publish", PUBLISH)

REPO = "o/r"
COMMIT = "0123456789abcdef0123456789abcdef01234567"
OTHER = "89abcdef0123456789abcdef0123456789abcdef"
TAG_OBJECT = "fedcba9876543210fedcba9876543210fedcba98"
NOW = datetime.datetime(2026, 11, 16, 12, 0, tzinfo=datetime.timezone.utc)
CITATION = """\
cff-version: 1.2.0
title: Example
version: 1.2.0
date-released: 2026-11-16
authors:
  - family-names: Doe
    version: not this one
"""

TAG_PATH = f"repos/{REPO}/git/ref/tags/v1.2.0"
OBJECT_PATH = f"repos/{REPO}/git/tags/{TAG_OBJECT}"
COMPARE_PATH = f"repos/{REPO}/compare/main...{COMMIT}?per_page=1"
RUNS_PATH = (
    f"repos/{REPO}/actions/workflows/ci.yml/runs?head_sha={COMMIT}"
    "&event=push&status=success&per_page=1&branch=dev"
)
CITATION_PATH = f"repos/{REPO}/contents/CITATION.cff?ref={COMMIT}"


def _settings(**changes: str) -> object:
    """Return settings of a good release of `v1.2.0`, with changes.

    Args:
        **changes: Settings to change.

    Returns:
        The settings.
    """
    return dataclasses.replace(
        check.Settings(repository=REPO, tag="v1.2.0", commit=COMMIT), **changes
    )


def _responses(tag: str = "v1.2.0") -> dict[str, object]:
    """Return the API responses of a good release.

    Args:
        tag: Name of the tag.

    Returns:
        Responses by path: JSON objects, text, or exceptions to raise.
    """
    return {
        f"repos/{REPO}/git/ref/tags/{tag}": {
            "ref": f"refs/tags/{tag}",
            "object": {"type": "tag", "sha": TAG_OBJECT},
        },
        OBJECT_PATH: {
            "tag": tag,
            "object": {"type": "commit", "sha": COMMIT},
            "verification": {"verified": True, "reason": "valid"},
        },
        COMPARE_PATH: {"status": "behind"},
        RUNS_PATH: {"total_count": 1},
        CITATION_PATH: CITATION,
    }


class FakeGh:
    """A stand-in for the GitHub CLI that serves fixed API responses.

    Attributes:
        responses: Responses by API path: JSON objects, text, or exceptions
            to raise.
        calls: Arguments of each call.
    """

    def __init__(self, responses: dict[str, object] | None = None) -> None:
        """Set the responses.

        Args:
            responses: Responses by API path; default is a good release.
        """
        self.responses = _responses() if responses is None else responses
        self.calls: list[list[str]] = []

    def __call__(self, args: Sequence[str]) -> str:
        """Answer a call like `gh api` would.

        Args:
            args: Arguments of `gh`.

        Returns:
            The output of the call.

        Raises:
            CheckError: For paths without a response (as `gh` on HTTP 404),
                or with an exception as their response.
        """
        args = list(args)
        self.calls.append(args)
        if args[0] != "api":
            raise AssertionError(f"Unexpected call: {args}")
        path = args[-1]
        response = self.responses.get(path)
        if response is None:
            raise check.CheckError(f"gh api {path} failed: Not Found (HTTP 404)")
        if isinstance(response, Exception):
            raise response
        if isinstance(response, str):
            return response
        return json.dumps(response)


class TestVersions(unittest.TestCase):
    """Release versions of tags, and the pre-release rule."""

    def test_valid(self) -> None:
        """Release versions, with and without pre-releases, pass."""
        cases = {
            ("v1.2.0", "v"): "1.2.0",
            ("v0.10.0", "v"): "0.10.0",
            ("v1.2.0rc1", "v"): "1.2.0rc1",
            ("v1.2.0a0", "v"): "1.2.0a0",
            ("v2.0.0-alpha.50", "v"): "2.0.0-alpha.50",
            ("v1.0.0-rc1", "v"): "1.0.0-rc1",
            ("v1.2.0-beta.2", "v"): "1.2.0-beta.2",
            ("chart-v1.0.0", "chart-v"): "1.0.0",
            ("plugin-x-v1.2.0b1", "plugin-x-v"): "1.2.0b1",
            ("1.2.0", ""): "1.2.0",
        }
        for (tag, prefix), version in cases.items():
            with self.subTest(tag=tag):
                self.assertEqual(check.release_version(tag, prefix), version)

    def test_invalid(self) -> None:
        """Tags that are no release versions after the prefix fail."""
        cases = [
            ("1.2.0", "v"),
            ("v1.2", "v"),
            ("v01.2.0", "v"),
            ("v1.02.0", "v"),
            ("v1.2.0.dev1", "v"),
            ("v1.2.0rc", "v"),
            ("v1.2.0rc01", "v"),
            ("v1.2.0RC1", "v"),
            ("v1.2.0+build", "v"),
            ("v1.2.0 ", "v"),
            ("chart-v1.0.0", "v"),
            ("v1.0.0", "chart-v"),
            ("vv1.0.0", "v"),
        ]
        for tag, prefix in cases:
            with self.subTest(tag=tag, prefix=prefix):
                with self.assertRaisesRegex(check.CheckError, "no release version"):
                    check.release_version(tag, prefix)

    def test_prerelease(self) -> None:
        """Pre-releases as `prerelease: auto` of publish-release decides."""
        versions = [
            "0.1.0",
            "0.10.0rc1",
            "1.0.0",
            "1.2.0",
            "1.2.0a1",
            "1.2.0b2",
            "1.2.0rc1",
            "2.0.0-alpha.50",
            "2.0.0-beta.1",
            "1.0.0-rc1",
            "10.0.0",
        ]
        for version in versions:
            with self.subTest(version=version):
                self.assertEqual(
                    check.is_prerelease(version),
                    publish.is_prerelease(f"v{version}", "auto"),
                )
        self.assertFalse(check.is_prerelease("1.2.0"))
        self.assertTrue(check.is_prerelease("0.9.0"))
        self.assertTrue(check.is_prerelease("1.2.0rc1"))
        with self.assertRaises(ValueError):
            check.is_prerelease("1.2")


class TestCitation(unittest.TestCase):
    """Reading `version` and `date-released` of citation metadata."""

    def test_read(self) -> None:
        """Top-level one-line values are read; nested keys are ignored."""
        self.assertEqual(
            check.read_citation(CITATION),
            {"version": "1.2.0", "date-released": "2026-11-16"},
        )

    def test_quotes_and_comments(self) -> None:
        """Quoted values and comments are read as YAML would."""
        text = (
            'version: "1.2.0"  # set in the release-prep PR\n'
            "date-released: '2026-11-16'\n"
        )
        self.assertEqual(
            check.read_citation(text),
            {"version": "1.2.0", "date-released": "2026-11-16"},
        )
        self.assertEqual(
            check.read_citation("version : 1.2.0 # comment\n"), {"version": "1.2.0"}
        )

    def test_missing(self) -> None:
        """Missing keys are left out."""
        self.assertEqual(check.read_citation("title: x\n"), {})

    def test_invalid(self) -> None:
        """Keys set twice and values that aren't one-line scalars fail."""
        cases = {
            "version: 1.2.0\nversion: 1.3.0\n": "set twice",
            "version:\n  1.2.0\n": "one-line value",
            'version: "1.2.0\n': "one-line value",
            "date-released: # none\n": "one-line value",
        }
        for text, message in cases.items():
            with self.subTest(text=text):
                with self.assertRaisesRegex(check.CheckError, message):
                    check.read_citation(text)


class TestSettings(unittest.TestCase):
    """Settings from the environment."""

    ENV = {
        "GH_REPO": REPO,
        "TAG": "v1.2.0",
        "COMMIT": COMMIT,
        "TAG_PREFIX": "v",
        "BRANCH": "main",
        "WORKFLOW": "ci.yml",
        "CI_BRANCH": "dev",
        "CITATION": "CITATION.cff",
        "VERSION": "",
    }

    def test_valid(self) -> None:
        """The settings are read, with optional ones empty."""
        env = {**self.ENV, "TAG_PREFIX": "", "CI_BRANCH": "", "CITATION": ""}
        settings = check.Settings.from_env(env)
        self.assertEqual(
            settings,
            check.Settings(
                repository=REPO,
                tag="v1.2.0",
                commit=COMMIT,
                prefix="",
                ci_branch="",
                citation="",
            ),
        )

    def test_missing(self) -> None:
        """Required settings must be set."""
        env = {**self.ENV, "TAG": "", "COMMIT": " "}
        del env["GH_REPO"]
        with self.assertRaisesRegex(check.CheckError, "Not set: GH_REPO, TAG, COMMIT"):
            check.Settings.from_env(env)

    def test_invalid(self) -> None:
        """Malformed settings fail before any API call."""
        cases = {
            "GH_REPO": "o/r/x",
            "COMMIT": COMMIT.upper(),
            "TAG_PREFIX": "../v",
            "BRANCH": "main?x=1",
            "WORKFLOW": "../ci.yml",
            "CI_BRANCH": "dev..main",
            "CITATION": "../CITATION.cff",
        }
        for name, value in cases.items():
            with self.subTest(name=name):
                with self.assertRaisesRegex(check.CheckError, "Invalid"):
                    check.Settings.from_env({**self.ENV, name: value})
        for citation in ("/CITATION.cff", "docs/", "a/../b"):
            with self.subTest(citation=citation):
                with self.assertRaisesRegex(check.CheckError, "Invalid citation"):
                    check.Settings.from_env({**self.ENV, "CITATION": citation})


class TestCheck(unittest.TestCase):
    """The checks, against API responses."""

    def _check(
        self, gh: FakeGh | None = None, **changes: str
    ) -> tuple[list[str], dict[str, str]]:
        """Run the checks.

        Args:
            gh: Stand-in for `gh`; default is a good release.
            **changes: Settings to change.

        Returns:
            The findings and outputs.
        """
        return check.check(_settings(**changes), gh or FakeGh(), NOW)

    def _finding(self, gh: FakeGh, message: str, **changes: str) -> None:
        """Assert that the checks fail with exactly one finding.

        Args:
            gh: Stand-in for `gh`.
            message: Part of the expected finding.
            **changes: Settings to change.
        """
        findings, outputs = self._check(gh, **changes)
        self.assertEqual(len(findings), 1, findings)
        self.assertIn(message, findings[0])
        self.assertEqual(outputs, {})

    def test_good(self) -> None:
        """A good release passes, with its outputs."""
        gh = FakeGh()
        self.assertEqual(
            self._check(gh, version="1.2.0"),
            ([], {"version": "1.2.0", "prerelease": "false", "sha": COMMIT}),
        )
        self.assertEqual(
            [call[-1] for call in gh.calls],
            [TAG_PATH, OBJECT_PATH, COMPARE_PATH, RUNS_PATH, CITATION_PATH],
        )
        self.assertEqual(
            gh.calls[-1],
            ["api", "-H", "Accept: application/vnd.github.raw+json", CITATION_PATH],
        )

    def test_head_of_branch(self) -> None:
        """The commit may be the head of the branch."""
        responses = _responses()
        responses[COMPARE_PATH] = {"status": "identical"}
        self.assertEqual(self._check(FakeGh(responses))[0], [])

    def test_prerelease_and_prefix(self) -> None:
        """A prefixed pre-release tag passes, as a pre-release."""
        responses = _responses("chart-v1.2.0rc1")
        responses[CITATION_PATH] = CITATION.replace(
            "\nversion: 1.2.0\n", "\nversion: 1.2.0rc1\n"
        )
        findings, outputs = self._check(
            FakeGh(responses), tag="chart-v1.2.0rc1", prefix="chart-v"
        )
        self.assertEqual(findings, [])
        self.assertEqual(outputs["version"], "1.2.0rc1")
        self.assertEqual(outputs["prerelease"], "true")

    def test_options(self) -> None:
        """Without `ci_branch`, any branch counts; without `citation`, no check."""
        responses = _responses()
        runs = RUNS_PATH.removesuffix("&branch=dev")
        responses[runs] = responses.pop(RUNS_PATH)
        del responses[CITATION_PATH]
        gh = FakeGh(responses)
        self.assertEqual(self._check(gh, ci_branch="", citation="")[0], [])
        self.assertEqual(len(gh.calls), 4)
        responses[runs] = {"total_count": 0}
        self._finding(
            FakeGh(responses),
            f"for a push of {COMMIT}; once CI passed",
            ci_branch="",
            citation="",
        )

    def test_quoted_paths(self) -> None:
        """Branch, workflow and file paths are quoted; slashes are kept."""
        responses = _responses()
        responses[f"repos/{REPO}/compare/release/1.x...{COMMIT}?per_page=1"] = (
            responses.pop(COMPARE_PATH)
        )
        responses[RUNS_PATH.replace("branch=dev", "branch=release%2F1.x")] = (
            responses.pop(RUNS_PATH)
        )
        responses[f"repos/{REPO}/contents/docs/CITATION.cff?ref={COMMIT}"] = (
            responses.pop(CITATION_PATH)
        )
        findings, _ = self._check(
            FakeGh(responses),
            branch="release/1.x",
            ci_branch="release/1.x",
            citation="docs/CITATION.cff",
        )
        self.assertEqual(findings, [])

    def test_lightweight_tag(self) -> None:
        """A lightweight tag fails."""
        responses = _responses()
        responses[TAG_PATH] = {
            "ref": "refs/tags/v1.2.0",
            "object": {"type": "commit", "sha": COMMIT},
        }
        self._finding(FakeGh(responses), "is not annotated")

    def test_missing_tag(self) -> None:
        """A tag that doesn't exist (any more) fails."""
        responses = _responses()
        del responses[TAG_PATH]
        self._finding(FakeGh(responses), "Could not look up the tag 'v1.2.0'")

    def test_other_ref(self) -> None:
        """A response for another ref (e.g., a prefix match) fails."""
        responses = _responses()
        responses[TAG_PATH] = {
            "ref": "refs/tags/v1.2.0.1",
            "object": {"type": "tag", "sha": TAG_OBJECT},
        }
        self._finding(FakeGh(responses), "Unexpected response")
        responses[TAG_PATH] = {"ref": "refs/tags/v1.2.0", "object": {"type": "tag"}}
        self._finding(FakeGh(responses), "Unexpected response")

    def test_unverified(self) -> None:
        """A tag without a verified signature fails, with GitHub's reason."""
        responses = _responses()
        responses[OBJECT_PATH]["verification"] = {
            "verified": False,
            "reason": "unsigned",
        }
        self._finding(FakeGh(responses), "no signature that GitHub verified (unsigned)")
        responses[OBJECT_PATH]["verification"] = {"verified": "true"}
        self._finding(FakeGh(responses), "no signature that GitHub verified")
        del responses[OBJECT_PATH]["verification"]
        self._finding(FakeGh(responses), "no signature that GitHub verified (None)")

    def test_other_name(self) -> None:
        """A tag whose tag object has another name fails."""
        responses = _responses()
        responses[OBJECT_PATH]["tag"] = "v1.1.0"
        self._finding(FakeGh(responses), "named 'v1.1.0'")

    def test_other_commit(self) -> None:
        """A tag that points to another commit, or to a tag, fails."""
        responses = _responses()
        responses[OBJECT_PATH]["object"] = {"type": "commit", "sha": OTHER}
        self._finding(FakeGh(responses), f"points to {OTHER}, not to the commit")
        responses[OBJECT_PATH]["object"] = {"type": "tag", "sha": OTHER}
        self._finding(FakeGh(responses), "doesn't point to a commit")

    def test_not_on_branch(self) -> None:
        """A commit that is not on the branch fails."""
        for status in ("ahead", "diverged"):
            with self.subTest(status=status):
                responses = _responses()
                responses[COMPARE_PATH] = {"status": status}
                self._finding(FakeGh(responses), f"is not on 'main' (status: {status})")
        responses = _responses()
        del responses[COMPARE_PATH]
        self._finding(FakeGh(responses), "Could not compare")

    def test_no_ci_run(self) -> None:
        """No successful CI run for a push of the commit fails."""
        for count in (0, None, "1", True):
            with self.subTest(count=count):
                responses = _responses()
                responses[RUNS_PATH] = {"total_count": count}
                self._finding(
                    FakeGh(responses),
                    f"No successful run of the CI workflow (ci.yml) for a push of"
                    f" {COMMIT} to 'dev'",
                )
        responses = _responses()
        responses[RUNS_PATH] = "not JSON"
        self._finding(FakeGh(responses), "Could not look up the runs of ci.yml")
        responses[RUNS_PATH] = []
        self._finding(FakeGh(responses), "no object")

    def test_package_version(self) -> None:
        """A package version that isn't the release version fails."""
        self._finding(FakeGh(), "Package version is '1.2.0rc1'", version="1.2.0rc1")

    def test_citation_version(self) -> None:
        """A citation version that isn't the release version fails."""
        for text in (
            CITATION.replace("\nversion: 1.2.0", "\nversion: 1.1.0"),
            CITATION.replace("\nversion: 1.2.0\n", "\n"),
        ):
            with self.subTest(text=text):
                responses = _responses()
                responses[CITATION_PATH] = text
                self._finding(FakeGh(responses), "expected '1.2.0'")

    def test_citation_date(self) -> None:
        """A release date that is missing, malformed or in the future fails."""
        cases = {
            "": "no valid date-released ('')",
            "date-released: 2026-02-30\n": "no valid date-released ('2026-02-30')",
            "date-released: 16.11.2026\n": "no valid date-released",
            "date-released: 2026-11-18\n": "date-released 2026-11-18 in the future",
        }
        for line, message in cases.items():
            with self.subTest(line=line):
                responses = _responses()
                responses[CITATION_PATH] = CITATION.replace(
                    "date-released: 2026-11-16\n", line
                )
                self._finding(FakeGh(responses), message)

    def test_citation_date_time_zones(self) -> None:
        """Tomorrow's date passes while it is tomorrow somewhere (UTC+14)."""
        responses = _responses()
        responses[CITATION_PATH] = CITATION.replace("2026-11-16", "2026-11-17")
        late = NOW.replace(hour=10)
        self.assertEqual(check.check(_settings(), FakeGh(responses), late)[0], [])
        early = NOW.replace(hour=9, minute=59)
        findings = check.check(_settings(), FakeGh(responses), early)[0]
        self.assertEqual(len(findings), 1)
        self.assertIn("in the future", findings[0])

    def test_citation_unreadable(self) -> None:
        """Missing or malformed citation metadata fails."""
        responses = _responses()
        del responses[CITATION_PATH]
        self._finding(FakeGh(responses), f"Could not read CITATION.cff of {COMMIT}")
        responses[CITATION_PATH] = "version:\n  - 1.2.0\n"
        self._finding(FakeGh(responses), "one-line value")

    def test_all_findings(self) -> None:
        """All checks run, and every finding is reported."""
        responses = _responses()
        responses[OBJECT_PATH]["verification"] = {
            "verified": False,
            "reason": "unsigned",
        }
        responses[COMPARE_PATH] = {"status": "diverged"}
        responses[RUNS_PATH] = {"total_count": 0}
        responses[CITATION_PATH] = "version: 1.1.0\n"
        findings, outputs = self._check(FakeGh(responses), version="1.1.0")
        self.assertEqual(len(findings), 6, findings)
        self.assertEqual(outputs, {})

    def test_no_version(self) -> None:
        """Without a release version, the version checks are skipped."""
        responses = _responses("v1.2")
        gh = FakeGh(responses)
        findings, _ = self._check(gh, tag="v1.2", version="1.2")
        self.assertEqual(len(findings), 1, findings)
        self.assertIn("no release version", findings[0])
        self.assertNotIn(CITATION_PATH, [call[-1] for call in gh.calls])


class TestMain(unittest.TestCase):
    """The script as the action runs it."""

    def setUp(self) -> None:
        """Create a scratch directory and the environment of a good release."""
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.output = self.path / "output"
        self.env = {
            **TestSettings.ENV,
            "VERSION": "1.2.0",
            "GITHUB_OUTPUT": str(self.output),
        }

    def _main(self, gh: FakeGh | None = None) -> tuple[int, str, str]:
        """Run `main`.

        Args:
            gh: Stand-in for `gh`; default is a good release.

        Returns:
            The exit status, standard output and standard error.
        """
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = check.main(self.env, gh or FakeGh(), NOW)
        return status, out.getvalue(), err.getvalue()

    def test_good(self) -> None:
        """A good release passes and writes the outputs."""
        lines = f"version=1.2.0\nprerelease=false\nsha={COMMIT}\n"
        self.assertEqual(self._main(), (0, lines, ""))
        self.assertEqual(self.output.read_text(encoding="utf-8"), lines)
        # Outside GitHub Actions, only to standard output
        del self.env["GITHUB_OUTPUT"]
        self.assertEqual(self._main(), (0, lines, ""))

    def test_findings(self) -> None:
        """Each finding is an error annotation; no outputs are written."""
        responses = _responses()
        responses[COMPARE_PATH] = {"status": "diverged"}
        responses[RUNS_PATH] = {"total_count": 0}
        status, out, err = self._main(FakeGh(responses))
        self.assertEqual((status, out), (1, ""))
        lines = err.splitlines()
        self.assertEqual(len(lines), 2, err)
        for line in lines:
            self.assertTrue(line.startswith("::error title=Check release::"), line)
        self.assertFalse(self.output.exists())

    def test_escaped(self) -> None:
        """Annotations are one line each, with `%`, CR and LF escaped."""
        responses = _responses()
        responses[COMPARE_PATH] = check.CheckError("50%\r\n::error::x")
        status, _, err = self._main(FakeGh(responses))
        self.assertEqual(status, 1)
        self.assertEqual(err.count("\n"), 1)
        self.assertIn("50%25%0D%0A::error::x", err)

    def test_invalid_settings(self) -> None:
        """Invalid settings fail before any API call."""
        self.env["COMMIT"] = "HEAD"
        gh = FakeGh()
        status, _, err = self._main(gh)
        self.assertEqual(status, 1)
        self.assertIn("::error title=Check release::Invalid commit 'HEAD'", err)
        self.assertEqual(gh.calls, [])

    def test_script(self) -> None:
        """The script runs as the action calls it, with `gh` on the path."""
        bin_dir = self.path / "bin"
        bin_dir.mkdir()
        log = self.path / "calls"
        responses = self.path / "responses"
        responses.mkdir()
        for name, path in {
            "ref": TAG_PATH,
            "object": OBJECT_PATH,
            "compare": COMPARE_PATH,
            "runs": RUNS_PATH,
            "citation": CITATION_PATH,
        }.items():
            response = _responses()[path]
            text = response if isinstance(response, str) else json.dumps(response)
            (responses / name).write_text(text, encoding="utf-8")
        (bin_dir / "gh").write_text(
            "#!/bin/sh\n"
            f'echo "$*" >> "{log}"\n'
            'eval "last=\\${$#}"\n'
            'case "${last}" in\n'
            f'  */git/ref/tags/*) cat "{responses}/ref" ;;\n'
            f'  */git/tags/*) cat "{responses}/object" ;;\n'
            f'  */compare/*) cat "{responses}/compare" ;;\n'
            f'  */runs\\?*) cat "{responses}/runs" ;;\n'
            f'  */contents/*) cat "{responses}/citation" ;;\n'
            "  *) exit 3 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        (bin_dir / "gh").chmod(0o755)
        env = {**self.env, "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"}
        result = subprocess.run(
            [sys.executable, "-I", str(SCRIPT)],
            capture_output=True,
            text=True,
            cwd=self.path,
            env=env,
            check=False,
        )
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        self.assertIn("version=1.2.0\n", self.output.read_text(encoding="utf-8"))
        self.assertEqual(len(log.read_text(encoding="utf-8").splitlines()), 5)

    def test_gh(self) -> None:
        """`_gh` returns the output of `gh`, and fails with its error."""
        bin_dir = self.path / "bin"
        bin_dir.mkdir()
        stub = bin_dir / "gh"
        stub.write_text(
            '#!/bin/sh\nif [ "$1" = ok ]; then echo "out $2"; else echo "bad" >&2;'
            " exit 1; fi\n",
            encoding="utf-8",
        )
        stub.chmod(0o755)
        path = f"{bin_dir}:{os.environ.get('PATH', '')}"
        with mock.patch.dict(os.environ, {"PATH": path}):
            self.assertEqual(check._gh(["ok", "x"]), "out x\n")
            with self.assertRaisesRegex(check.CheckError, "gh fail y failed: bad"):
                check._gh(["fail", "y"])


if __name__ == "__main__":
    unittest.main()
