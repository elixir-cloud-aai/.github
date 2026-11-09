"""Tests of the script of the `publish-release` action (`publish.py`)."""

from __future__ import annotations

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
SCRIPT = ROOT / "actions/publish-release/publish.py"

# The action's directory is not a package, so the script is loaded from its
# file
_spec = importlib.util.spec_from_file_location("publish", SCRIPT)
assert _spec and _spec.loader
publish = importlib.util.module_from_spec(_spec)
sys.modules["publish"] = publish
_spec.loader.exec_module(publish)

CURATED = """\
The release brings a feature. See the [upgrade
guide](https://example.org/upgrading/).

## Breaking changes

- A breaking change, described
  over two lines (#1, #2)
- Another one, with a lazy
continuation line (#3; #4, #5)

## Features

- A feature with an example (#6, #7):

  ```yaml
  key: value
  ## not a heading
  ```

  And more text about it (#8)
* A bullet with another marker (#9)

## Maintenance

1. A numbered item (#10)
"""

# As GitHub's `generate-notes` API returns them (`body`)
GENERATED = """\
## What's Changed
* feat: add a feature by @someone in https://github.com/o/r/pull/7
* fix: fix a bug by @newcomer in https://github.com/o/r/pull/11

## New Contributors
* @newcomer made their first contribution in https://github.com/o/r/pull/11

**Full Changelog**: https://github.com/o/r/compare/v0.2.0...v0.3.0"""

VALID = [
    CURATED,
    # The intro alone, and sections with closing hashes
    "A fix release.\n",
    "Intro.\n\n## Fixes ##\n\n- Fix (#1)\n",
    # Code blocks in the intro, headings in code blocks
    "Intro.\n\n```text\n## Unknown\n```\n\n## Fixes\n\n- Fix (#1)\n",
    # Fences close only with the same character, at least as long, and
    # nothing else on the line
    "Intro.\n\n## Fixes\n\n- Fix (#1):\n\n  ````md\n  ```\n  ## No\n  ```\n"
    "  ````\n\n  More (#2)\n",
    "Intro.\n\n## Fixes\n\n- Fix (#1):\n\n  ```\n  ~~~\n  ``` x\n  ```\n\n"
    "  More (#2)\n",
    # HTML comments, and a byte order mark
    "<!-- Notes of 0.3.0 -->\nIntro.\n\n## Fixes\n\n<!-- comment -->\n- Fix (#1)\n",
    "\ufeffIntro.\n\n## Fixes\n\n- Fix (#1)\n",
    "Intro.\n\n## Fixes\n\n- Fix (#1)\n    <!-- c -->\n- Fix (#2)\n<!-- c -->\n",
    "Intro.\n\n## Fixes\n\n- Fix (#1)\n\n<!-- c -->\n\n- Fix (#2)\n",
    "<!-- a --> Intro <!-- b -->\n\n## Fixes\n\n- Fix (#1)\n",
    # Code blocks may show the generated parts
    "Intro.\n\n```md\n**Full Changelog**: https://x/compare/a...b\n```\n",
    # Numbers wrapped over lines
    "Intro.\n\n## Fixes\n\n- Fix (#1,\n  #2; #3,\n  #4)\n",
    # Hashes that are no headings
    "Intro.\n\n## Fixes\n\n- Fix of\n#12 (#13)\n",
    # Absolute links (with a scheme) and other brackets
    "Intro, see [docs](https://example.org/en/latest/).\n",
    "Intro, write to [us](mailto:x@example.org).\n",
    "Intro, see [docs](<https://example.org/a b>).\n",
    "Intro, see [docs][1].\n\n[1]: https://example.org/\n",
    "Intro with brackets [x] (y) and `code`.\n",
]

INVALID = [
    # No intro
    ("", [(1, "No intro paragraph")]),
    ("<!-- comment -->\n", [(1, "No intro paragraph")]),
    # Lists and code blocks are no intro paragraph
    ("- Item\n\n## Fixes\n\n- Fix (#1)\n", [(3, "No intro paragraph")]),
    ("```\ncode\n```\n\n## Fixes\n\n- Fix (#1)\n", [(5, "No intro paragraph")]),
    ("<!-- comment -->\n## Fixes\n\n- Fix (#1)\n", [(2, "No intro paragraph")]),
    ("\ufeff## Fixes\n\n- Fix (#1)\n", [(1, "No intro paragraph")]),
    ("\n\n", [(2, "No intro paragraph")]),
    # Other headings
    ("# App 0.3.0\n\nIntro.\n", [(1, "Heading of level"), (1, "No intro paragraph")]),
    (
        "Intro.\n\n## Fixes\n\n### API\n\n- Fix (#1)\n",
        [(3, "Empty section"), (5, "Heading of level")],
    ),
    ("Intro.\n\n## New features\n\n- Feature (#1)\n", [(3, "Unknown section 'New")]),
    ("Intro.\n\n#\n", [(3, "Heading of level")]),
    # Setext headings and thematic breaks
    ("Intro\n===\n", [(2, "Setext heading or")]),
    ("Intro.\n\n## Fixes\n\n- Fix (#1)\n\n---\n", [(7, "Setext heading or")]),
    ("Intro.\n\n***\n", [(3, "Setext heading or")]),
    # Order, duplicates and empty sections
    (
        "Intro.\n\n## Fixes\n\n- Fix (#1)\n\n## Features\n\n- Feature (#2)\n",
        [(7, "Section 'Features' after")],
    ),
    (
        "Intro.\n\n## Fixes\n\n- Fix (#1)\n\n## Fixes\n\n- Fix (#2)\n",
        [(7, "Section 'Fixes' after")],
    ),
    ("Intro.\n\n## Fixes\n\n## Maintenance\n\n- Chore (#1)\n", [(3, "Empty section")]),
    ("Intro.\n\n## Fixes\n", [(3, "Empty section")]),
    # Parts that the action adds
    (
        "Intro.\n\n## Commits\n\n* fix by @a in https://x/pull/1\n",
        [(3, "Section 'Commits': the")],
    ),
    (
        "Intro.\n\n**Full Changelog**: https://x/compare/a...b\n",
        [(3, "'**Full Changelog**' line:")],
    ),
    # Sections hold bullets only
    (
        "Intro.\n\n## Fixes\n\n- Fix (#1)\n\nA paragraph.\n",
        [(7, "Sections hold bullets")],
    ),
    (
        "Intro.\n\n## Fixes\n\nA paragraph.\n\n- Fix (#1)\n",
        [(5, "Sections hold bullets")],
    ),
    (
        "Intro.\n\n## Fixes\n\n```\ncode\n```\n\n- Fix (#1)\n",
        [(5, "Sections hold bullets")],
    ),
    # Bullets end with their issue and pull request numbers
    (
        "Intro.\n\n## Fixes\n\n- Fix\n- Fix (#1).\n- Fix (#1) more\n"
        "- Fix (1, 2)\n- Fix (#a)\n- Fix #1\n",
        [(line, "Bullet doesn't end") for line in range(5, 11)],
    ),
    (
        "Intro.\n\n## Fixes\n\n- Fix (#1):\n\n  More text.\n",
        [(7, "Bullet doesn't end")],
    ),
    # Unclosed code blocks
    (
        "Intro.\n\n## Fixes\n\n- Fix (#1)\n\n  ```\n  code\n",
        [(8, "Bullet doesn't end"), (8, "Unclosed fenced code")],
    ),
    # Relative links, which don't resolve in GitHub releases
    ("Intro, see [Migrating](migration-0.3.md).\n", [(1, "Relative link (e.g.,")]),
    ("Intro, see [the guide](../migration/#steps).\n", [(1, "Relative link (e.g.,")]),
    ("Intro, see [docs](/en/v0.3.0/).\n", [(1, "Relative link (e.g.,")]),
    ("Intro, see [section](#fixes).\n", [(1, "Relative link (e.g.,")]),
    ("Intro, see [docs](<docs/index.md>).\n", [(1, "Relative link (e.g.,")]),
    ("Intro, see ![logo](images/logo.svg).\n", [(1, "Relative link (e.g.,")]),
    ("Intro, see [docs][1].\n\n[1]: docs/index.md\n", [(3, "Relative link (e.g.,")]),
]


def _messages(markdown: str) -> list[tuple[int, str]]:
    """Return the line and the start of the message of each finding.

    Args:
        markdown: Curated release notes.

    Returns:
        Line and first three words of the message of each finding.
    """
    return [
        (finding.line, " ".join(finding.message.split()[:3]))
        for finding in publish.check(markdown)
    ]


# Tags of the repository that `FakeGh` serves by default
TAGS = ["v0.9.0", "v1.0.0", "v1.1.0", "v1.2.0"]


def _release(
    tag: str, *, draft: bool = False, prerelease: bool = False, body: str = ""
) -> dict[str, object]:
    """Return a release as the REST API lists it (the fields used).

    Args:
        tag: Name of the release's tag.
        draft: Whether the release is a draft.
        prerelease: Whether the release is a pre-release.
        body: Body of the release.

    Returns:
        The release.
    """
    return {
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
        "body": body,
        "html_url": f"https://github.com/o/r/releases/tag/{tag}",
    }


class FakeGh:
    """A stand-in for the GitHub CLI that serves fixed API responses.

    Attributes:
        releases: Releases of the repository.
        tags: Names of the tags of the repository.
        generated: Body of the `generate-notes` response.
        calls: Arguments of each call.
        notes: Notes file content of each `release create` call.
        fail: Start of the arguments of calls that fail.
    """

    def __init__(
        self,
        releases: list[dict[str, object]] | None = None,
        tags: list[str] | None = None,
        generated: str = GENERATED,
        fail: Sequence[str] = (),
    ) -> None:
        """Set the responses.

        Args:
            releases: Releases of the repository.
            tags: Names of the tags of the repository.
            generated: Body of the `generate-notes` response.
            fail: Start of the arguments of calls that fail.
        """
        self.releases = releases or []
        self.tags = TAGS if tags is None else tags
        self.generated = generated
        self.calls: list[list[str]] = []
        self.notes: list[str] = []
        self.fail = list(fail)

    def __call__(self, args: Sequence[str]) -> str:
        """Answer a call like `gh` would.

        Args:
            args: Arguments of `gh`.

        Returns:
            The output of the call.

        Raises:
            ReleaseError: For calls listed in `fail`.
            AssertionError: For unexpected calls.
        """
        args = list(args)
        self.calls.append(args)
        if self.fail and args[: len(self.fail)] == self.fail:
            raise publish.ReleaseError("gh failed: HTTP 422")
        if args[:3] == ["api", "--paginate", "--slurp"]:
            # Two pages, as `--slurp` prints them
            half = len(self.releases) // 2
            return json.dumps([self.releases[:half], self.releases[half:]])
        if args[:2] == ["api", "--paginate"] and "matching-refs" in args[2]:
            return "".join(f"{tag}\n" for tag in self.tags)
        if args[1].endswith("/releases/generate-notes"):
            return self.generated + "\n"
        if args[:2] == ["release", "create"]:
            path = args[args.index("--notes-file") + 1]
            self.notes.append(Path(path).read_text(encoding="utf-8"))
            return f"https://github.com/o/r/releases/tag/{args[2]}\n"
        raise AssertionError(f"Unexpected call: {args}")


class TestCheck(unittest.TestCase):
    """Tests of the check of curated notes."""

    def test_valid(self) -> None:
        """Notes in the format have no findings."""
        for markdown in VALID:
            with self.subTest(markdown=markdown):
                self.assertEqual(publish.check(markdown), [])

    def test_invalid(self) -> None:
        """Notes that differ from the format have findings."""
        for markdown, messages in INVALID:
            with self.subTest(markdown=markdown):
                self.assertEqual(_messages(markdown), messages)


class TestBody(unittest.TestCase):
    """Tests of the release body."""

    def test_body(self) -> None:
        """The body is the curated notes, then the generated ones, no header."""
        text, warnings = publish.body(CURATED, GENERATED)
        changes = GENERATED.removeprefix("## What's Changed\n")
        self.assertEqual(text, f"{CURATED.strip()}\n\n## Commits\n\n{changes}\n")
        self.assertTrue(
            text.endswith(
                "\n\n**Full Changelog**: https://github.com/o/r/compare/v0.2.0...v0.3.0\n"
            )
        )
        self.assertIn("## New Contributors", text)
        self.assertNotIn("What's Changed", text)
        self.assertEqual(warnings, [])

    def test_byte_order_mark(self) -> None:
        """A byte order mark of the curated notes is left out."""
        text, _ = publish.body("\ufeffIntro.\n", GENERATED)
        self.assertTrue(text.startswith("Intro.\n"))

    def test_comment(self) -> None:
        """The header is also dropped after a comment (of a configuration)."""
        generated = (
            f"<!-- Release notes generated using configuration -->\n\n{GENERATED}"
        )
        text, warnings = publish.body("Intro.\n", generated)
        self.assertTrue(
            text.startswith(
                "Intro.\n\n## Commits\n\n<!-- Release notes generated using"
                " configuration -->\n\n* feat: add a feature"
            )
        )
        self.assertNotIn("What's Changed", text)
        self.assertEqual(warnings, [])

    def test_no_changes(self) -> None:
        """Without changes in the generated notes, the body has no `Commits`."""
        generated = "**Full Changelog**: https://github.com/o/r/commits/v0.3.0\n"
        self.assertEqual(
            publish.body("Intro.\n", generated),
            (
                "Intro.\n\n**Full Changelog**: https://github.com/o/r/commits/v0.3.0\n",
                [],
            ),
        )

    def test_crlf(self) -> None:
        """Generated notes with CRLF or CR line endings are normalised."""
        for newline in ("\r\n", "\r"):
            with self.subTest(newline=repr(newline)):
                generated = GENERATED.replace("\n", newline) + newline
                self.assertEqual(
                    publish.body(CURATED, generated), publish.body(CURATED, GENERATED)
                )

    def test_unexpected_generated(self) -> None:
        """Generated notes without a final `**Full Changelog**` line are kept."""
        for generated, commits in [
            ("", ""),
            (
                "## What's Changed\n* fix by @a in https://x/pull/1\n",
                "\n\n## Commits\n\n* fix by @a in https://x/pull/1",
            ),
            (
                "**Full Changelog**: https://x/commits/v1\n\nMore text.\n",
                "\n\n## Commits\n\n**Full Changelog**: https://x/commits/v1"
                "\n\nMore text.",
            ),
        ]:
            warning = "Generated notes don't end with a '**Full Changelog**: ' line"
            with self.subTest(generated=generated):
                self.assertEqual(
                    publish.body("Intro.\n", generated),
                    (f"Intro.{commits}\n", [warning]),
                )

    def test_splits_at_line_breaks_only(self) -> None:
        """Other line separators (e.g., U+2028) start no line."""
        generated = "* x\u2028## Security by @a in u\n\n**Full Changelog**: c\n"
        text, warnings = publish.body("Intro.\n", generated)
        self.assertNotIn("\n## Security", text)
        self.assertEqual(warnings, [])


class TestVersions(unittest.TestCase):
    """Tests of versions, pre-releases and the previous and latest release."""

    def test_parse_version(self) -> None:
        """Release versions sort as versions; other tags are none."""
        order = [
            "0.9.0",
            "v1.0",
            "v1.1",
            "1.2.0a1",
            "1.2.0-alpha.2",
            "v1.2.0b1",
            "1.2.0rc1",
            "1.2.0rc2",
            "v1.2.0",
            "1.2.1",
            "1.10.0",
            "v2.0.0",
        ]
        keys = [publish.parse_version(tag) for tag in order]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(len(set(keys)), len(keys))
        self.assertEqual(publish.parse_version("v1.1"), publish.parse_version("1.1.0"))
        self.assertEqual(
            publish.parse_version("1.2.0-RC1"), publish.parse_version("1.2.0rc1")
        )
        for tag in ("v0.8.2_trs", "latest", "1", "v1.2.3.4", "1.2.0rc", "x1.2.0"):
            with self.subTest(tag=tag):
                if tag == "1.2.0rc":
                    # A pre-release without a number is the first one
                    self.assertEqual(
                        publish.parse_version(tag), publish.parse_version("1.2.0rc0")
                    )
                else:
                    self.assertIsNone(publish.parse_version(tag))

    def test_is_prerelease(self) -> None:
        """`auto` marks versions below 1.0.0 and `a`, `b`, `rc` versions."""
        for tag, expected in [
            ("v0.22.0", True),
            ("1.0.0rc1", True),
            ("v2.0.0-beta.1", True),
            ("v1.2.0", False),
            ("1.0", False),
        ]:
            with self.subTest(tag=tag):
                self.assertIs(publish.is_prerelease(tag, "auto"), expected)
        self.assertIs(publish.is_prerelease("v0.1.0", "false"), False)
        self.assertIs(publish.is_prerelease("v1.0.0", "true"), True)
        self.assertIs(publish.is_prerelease("nightly", "true"), True)

    def test_is_prerelease_errors(self) -> None:
        """Unknown policies, and `auto` for other tags, are errors."""
        with self.assertRaisesRegex(publish.ReleaseError, "Unknown pre-release"):
            publish.is_prerelease("v1.0.0", "yes")
        with self.assertRaisesRegex(publish.ReleaseError, "no release version"):
            publish.is_prerelease("nightly", "auto")

    def test_previous_release(self) -> None:
        """The previous release is the highest lower published one."""
        releases = [
            _release("v1.0.0"),
            _release("v1.1.0rc1", prerelease=True),
            _release("v1.1.0"),
            _release("v1.3.0"),
            _release("v1.2.0rc1", draft=True),
            _release("nightly"),
        ]
        tags = ["v1.1.5", "v1.2.0rc1", "v0.9.0"]
        self.assertEqual(publish.previous_release("v1.2.0", releases, tags), "v1.1.0")
        # A final release starts before its own pre-releases; a pre-release
        # after the previous one
        self.assertEqual(publish.previous_release("v1.1.0", releases, tags), "v1.0.0")
        self.assertEqual(
            publish.previous_release("v1.1.0rc2", releases, tags), "v1.1.0rc1"
        )
        self.assertEqual(publish.previous_release("v1.0.1", releases, tags), "v1.0.0")

    def test_previous_release_from_tags(self) -> None:
        """Without a lower release, the highest lower version tag counts."""
        tags = ["v0.7.2", "v0.8.2", "v0.8.2_trs", "v1.0", "v1.1", "v1.2.0", "v1.3"]
        drafts = [_release("v1.1.5", draft=True)]
        self.assertEqual(publish.previous_release("v1.2.0", drafts, tags), "v1.1")
        self.assertEqual(
            publish.previous_release("v1.2.0", [], [*tags, "v1.2.0rc1"]), "v1.1"
        )
        self.assertIsNone(publish.previous_release("v0.7.2", [], tags))
        self.assertIsNone(publish.previous_release("nightly", [], tags))

    def test_is_latest(self) -> None:
        """A release is the latest unless a published release is higher."""
        releases = [
            _release("v1.0.0"),
            _release("v2.0.0rc1", prerelease=True),
            _release("v3.0.0", draft=True),
            _release("nightly"),
        ]
        self.assertIs(publish.is_latest("v1.1.0", False, releases), True)
        self.assertIs(publish.is_latest("v1.1.0", True, releases), False)
        self.assertIs(publish.is_latest("v0.9.1", False, releases), False)
        self.assertIsNone(publish.is_latest("nightly-2", False, releases))


class TestPublish(unittest.TestCase):
    """Tests of the creation of the release."""

    def setUp(self) -> None:
        """Write curated notes to a temporary directory."""
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.notes = Path(self.directory.name) / "1.2.0.md"
        self.notes.write_text(CURATED, encoding="utf-8")
        self.settings = publish.Settings(
            repository="o/r", tag="v1.2.0", notes=self.notes
        )

    def test_publish(self) -> None:
        """The release gets the body, flags and the detected previous tag."""
        gh = FakeGh(releases=[_release("v1.1.0"), _release("v0.9.0")])
        text, url = publish.publish(self.settings, gh)
        self.assertEqual(text, publish.body(CURATED, GENERATED)[0])
        self.assertEqual(url, "https://github.com/o/r/releases/tag/v1.2.0")
        self.assertEqual(gh.notes, [text])
        self.assertIn(
            [
                "api",
                "repos/o/r/releases/generate-notes",
                "-f",
                "tag_name=v1.2.0",
                "-f",
                "previous_tag_name=v1.1.0",
                "--jq",
                ".body",
            ],
            gh.calls,
        )
        create = gh.calls[-1]
        path = Path(create[create.index("--notes-file") + 1])
        self.assertEqual(
            create,
            [
                "release",
                "create",
                "v1.2.0",
                "--verify-tag",
                "--title",
                "v1.2.0",
                "--notes-file",
                str(path),
                "--prerelease=false",
                "--latest=true",
            ],
        )
        # The notes file is removed
        self.assertFalse(path.exists())

    def test_publish_settings(self) -> None:
        """Previous tag, title and pre-release policy are passed on."""
        gh = FakeGh(releases=[_release("v1.1.0")])
        settings = publish.Settings(
            repository="o/r",
            tag="v1.2.0",
            notes=self.notes,
            prerelease="true",
            previous="v1.0.0",
            title="App 1.2.0",
        )
        publish.publish(settings, gh)
        self.assertIn("previous_tag_name=v1.0.0", gh.calls[-2])
        self.assertIn("App 1.2.0", gh.calls[-1])
        self.assertIn("--prerelease=true", gh.calls[-1])
        self.assertIn("--latest=false", gh.calls[-1])

    def test_publish_without_previous(self) -> None:
        """Without a lower release or tag, GitHub picks the start."""
        gh = FakeGh(tags=["v1.2.0"])
        publish.publish(self.settings, gh)
        self.assertFalse(any("previous_tag_name" in arg for arg in gh.calls[-2]))

    def test_publish_other_tag(self) -> None:
        """For tags that are no release versions, GitHub picks the latest."""
        gh = FakeGh(tags=["nightly"])
        settings = publish.Settings(
            repository="o/r", tag="nightly", notes=self.notes, prerelease="false"
        )
        publish.publish(settings, gh)
        self.assertFalse(any(arg.startswith("--latest") for arg in gh.calls[-1]))

    def test_publish_draft_exists(self) -> None:
        """A draft of the tag fails, before notes are generated."""
        gh = FakeGh(releases=[_release("v1.1.0"), _release("v1.2.0", draft=True)])
        with self.assertRaisesRegex(publish.ReleaseError, "draft release"):
            publish.publish(self.settings, gh)
        self.assertEqual(len(gh.calls), 1)

    def test_publish_exists(self) -> None:
        """A published release of the tag with another body fails."""
        gh = FakeGh(releases=[_release("v1.1.0"), _release("v1.2.0", body="Old.")])
        with self.assertRaisesRegex(publish.ReleaseError, "with another body"):
            publish.publish(self.settings, gh)
        self.assertFalse(any(call[0] == "release" for call in gh.calls))

    def test_publish_exists_same_body(self) -> None:
        """A re-run after a creation that succeeded passes, without changes."""
        text = publish.body(CURATED, GENERATED)[0]
        gh = FakeGh(releases=[_release("v1.1.0"), _release("v1.2.0", body=text)])
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = publish.publish(self.settings, gh)
        self.assertEqual(result, (text, "https://github.com/o/r/releases/tag/v1.2.0"))
        self.assertFalse(any(call[0] == "release" for call in gh.calls))
        self.assertIn("::notice::The release v1.2.0 exists already", stderr.getvalue())

    def test_publish_missing_tags(self) -> None:
        """A missing tag or previous tag fails before notes are generated."""
        for tag, previous, message in [
            ("v1.3.0", "", "The tag v1.3.0 doesn't exist"),
            ("v1.2.0", "v1.0.5", "The previous tag v1.0.5 doesn't exist"),
        ]:
            with self.subTest(tag=tag, previous=previous):
                gh = FakeGh()
                settings = publish.Settings(
                    repository="o/r", tag=tag, notes=self.notes, previous=previous
                )
                with self.assertRaisesRegex(publish.ReleaseError, message):
                    publish.publish(settings, gh)
                self.assertEqual(len(gh.calls), 2)

    def test_publish_no_version(self) -> None:
        """`auto` fails for tags that are no versions, before any call."""
        for tag, policy in [("nightly", "auto"), ("v1.2.0", "yes")]:
            with self.subTest(tag=tag, policy=policy):
                gh = FakeGh()
                settings = publish.Settings(
                    repository="o/r", tag=tag, notes=self.notes, prerelease=policy
                )
                with self.assertRaises(publish.ReleaseError):
                    publish.publish(settings, gh)
                self.assertEqual(gh.calls, [])

    def test_check_only(self) -> None:
        """`check_only` checks the repository, and generates and creates nothing."""
        gh = FakeGh(releases=[_release("v1.1.0")])
        settings = publish.Settings(
            repository="o/r", tag="v1.2.0", notes=self.notes, check_only=True
        )
        self.assertEqual(publish.publish(settings, gh), (CURATED, ""))
        self.assertEqual(len(gh.calls), 2)
        self.assertFalse(any("generate-notes" in " ".join(c) for c in gh.calls))

    def test_check_only_exists(self) -> None:
        """`check_only` fails for a published release of the tag."""
        text = publish.body(CURATED, GENERATED)[0]
        gh = FakeGh(releases=[_release("v1.2.0", body=text)])
        settings = publish.Settings(
            repository="o/r", tag="v1.2.0", notes=self.notes, check_only=True
        )
        with self.assertRaisesRegex(publish.ReleaseError, "release the next"):
            publish.publish(settings, gh)

    def test_publish_invalid_notes(self) -> None:
        """Notes with findings fail before any call."""
        self.notes.write_text("## Fixes\n\n- Fix (#1)\n", encoding="utf-8")
        gh = FakeGh()
        stderr = io.StringIO()
        with (
            redirect_stderr(stderr),
            self.assertRaisesRegex(publish.ReleaseError, "not in the format"),
        ):
            publish.publish(self.settings, gh)
        self.assertEqual(gh.calls, [])
        self.assertIn(f"::error file={self.notes},line=1::No intro", stderr.getvalue())

    def test_publish_missing_notes(self) -> None:
        """Missing notes fail before any call."""
        self.notes.unlink()
        gh = FakeGh()
        with self.assertRaisesRegex(publish.ReleaseError, "Can't read the curated"):
            publish.publish(self.settings, gh)
        self.assertEqual(gh.calls, [])

    def test_publish_gh_fails(self) -> None:
        """A failing `gh release create` fails, and the notes file is removed."""
        gh = FakeGh(fail=["release", "create"])
        with self.assertRaisesRegex(publish.ReleaseError, "HTTP 422"):
            publish.publish(self.settings, gh)
        path = Path(gh.calls[-1][gh.calls[-1].index("--notes-file") + 1])
        self.assertFalse(path.exists())

    def test_publish_unexpected_generated(self) -> None:
        """Unexpected generated notes are kept, with a warning."""
        gh = FakeGh(generated="Changes.")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            text, _ = publish.publish(self.settings, gh)
        self.assertTrue(text.endswith("## Commits\n\nChanges.\n"))
        self.assertIn("::warning::Generated notes don't end", stderr.getvalue())


class TestMain(unittest.TestCase):
    """Tests of the command line."""

    def setUp(self) -> None:
        """Write curated notes and files of GitHub Actions to a directory."""
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.notes = self.path / "1.2.0.md"
        self.notes.write_text(CURATED, encoding="utf-8")
        self.env = {
            "GH_REPO": "o/r",
            "TAG": "v1.2.0",
            "NOTES": str(self.notes),
            "PRERELEASE": "",
            "PREVIOUS_TAG": "",
            "TITLE": "",
            "GITHUB_OUTPUT": str(self.path / "output"),
            "GITHUB_STEP_SUMMARY": str(self.path / "summary"),
        }

    def _main(self, argv: list[str], gh: FakeGh | None = None) -> tuple[int, str, str]:
        """Run `main` and capture its output.

        Args:
            argv: Command-line arguments.
            gh: Stand-in for the GitHub CLI.

        Returns:
            Exit status, standard output and standard error.
        """
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = publish.main(argv, self.env, gh or FakeGh())
        return status, stdout.getvalue(), stderr.getvalue()

    def test_check(self) -> None:
        """`check` passes for notes in the format."""
        self.assertEqual(self._main(["check", str(self.notes)]), (0, "", ""))

    def test_check_findings(self) -> None:
        """`check` prints findings as error annotations."""
        self.notes.write_text("Intro.\n\n## Fixes\n", encoding="utf-8")
        status, stdout, stderr = self._main(["check", str(self.notes)])
        self.assertEqual((status, stdout), (1, ""))
        self.assertTrue(
            stderr.startswith(f"::error file={self.notes},line=3::Empty section\n")
        )

    def test_check_missing(self) -> None:
        """`check` fails for missing notes."""
        status, _, stderr = self._main(["check", str(self.path / "x.md")])
        self.assertEqual(status, 1)
        self.assertIn("::error title=Publish release::Can't read", stderr)

    def test_publish(self) -> None:
        """`publish` prints the URL, sets the output and writes the summary."""
        status, stdout, stderr = self._main(["publish"])
        url = "https://github.com/o/r/releases/tag/v1.2.0"
        self.assertEqual((status, stdout, stderr), (0, f"{url}\n", ""))
        self.assertEqual(
            (self.path / "output").read_text(encoding="utf-8"), f"url={url}\n"
        )
        self.assertEqual(
            (self.path / "summary").read_text(encoding="utf-8"),
            publish.body(CURATED, GENERATED)[0],
        )

    def test_publish_missing_settings(self) -> None:
        """`publish` fails without the repository, tag or notes."""
        self.env = {"TAG": "v1.2.0"}
        status, _, stderr = self._main(["publish"])
        self.assertEqual(status, 1)
        self.assertIn("Not set: GH_REPO, NOTES", stderr)

    def test_publish_error(self) -> None:
        """`publish` fails with an error annotation."""
        gh = FakeGh(releases=[_release("v1.2.0", draft=True)])
        status, stdout, stderr = self._main(["publish"], gh)
        self.assertEqual((status, stdout), (1, ""))
        self.assertTrue(stderr.startswith("::error title=Publish release::A draft"))
        self.assertFalse((self.path / "output").exists())

    def test_publish_check_only(self) -> None:
        """With `CHECK_ONLY`, nothing is printed or written."""
        for value in ("true", "True"):
            with self.subTest(value=value):
                self.env["CHECK_ONLY"] = value
                self.assertEqual(self._main(["publish"]), (0, "", ""))
                self.assertFalse((self.path / "output").exists())
                self.assertFalse((self.path / "summary").exists())

    def test_publish_invalid_check_only(self) -> None:
        """`CHECK_ONLY` other than true or false fails before any call."""
        self.env["CHECK_ONLY"] = "yes"
        gh = FakeGh()
        status, _, stderr = self._main(["publish"], gh)
        self.assertEqual(status, 1)
        self.assertIn("Invalid check-only 'yes'", stderr)
        self.assertEqual(gh.calls, [])

    def test_script_publish(self) -> None:
        """The script runs as the action calls it, with a recording `gh`.

        The stand-in serves the API calls and records the arguments of every
        call, so that the real command lines (flags included) are checked.
        """
        bin_dir = self.path / "bin"
        bin_dir.mkdir()
        log = self.path / "gh.log"
        (bin_dir / "gh").write_text(
            "#!/bin/sh\n"
            f'printf "%s\\n" "$*" >> "{log}"\n'
            'case "$*" in\n'
            '  *"--slurp"*) echo "[[]]" ;;\n'
            '  *matching-refs*) printf "v1.1.0\\nv1.2.0\\n" ;;\n'
            f'  *generate-notes*) cat "{self.path / "generated.md"}" ;;\n'
            '  "release create"*) echo https://github.com/o/r/releases/tag/v1.2.0 ;;\n'
            "  *) exit 3 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        (bin_dir / "gh").chmod(0o755)
        (self.path / "generated.md").write_text(GENERATED, encoding="utf-8")
        env = {**self.env, "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"}
        result = subprocess.run(
            [sys.executable, "-I", str(SCRIPT), "publish"],
            capture_output=True,
            text=True,
            cwd=self.path,
            env=env,
            check=False,
        )
        url = "https://github.com/o/r/releases/tag/v1.2.0"
        self.assertEqual((result.returncode, result.stdout), (0, f"{url}\n"))
        calls = log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            calls[:3],
            [
                "api --paginate --slurp repos/o/r/releases?per_page=100",
                "api --paginate repos/o/r/git/matching-refs/tags"
                ' --jq .[].ref | ltrimstr("refs/tags/")',
                "api repos/o/r/releases/generate-notes -f tag_name=v1.2.0"
                " -f previous_tag_name=v1.1.0 --jq .body",
            ],
        )
        self.assertRegex(
            calls[3],
            r"^release create v1\.2\.0 --verify-tag --title v1\.2\.0 --notes-file"
            r" \S+\.md --prerelease=false --latest=true$",
        )

    def test_script(self) -> None:
        """The script runs as the action calls it (`check`)."""
        result = subprocess.run(
            [sys.executable, "-I", str(SCRIPT), "check", str(self.notes)],
            capture_output=True,
            text=True,
            cwd=self.path,
            check=False,
        )
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

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
            self.assertEqual(publish._gh(["ok", "x"]), "out x\n")
            with self.assertRaisesRegex(publish.ReleaseError, "gh no x failed: bad"):
                publish._gh(["no", "x"])


if __name__ == "__main__":
    unittest.main()
