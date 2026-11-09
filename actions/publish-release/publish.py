#!/usr/bin/env python3
"""Check curated release notes and create the GitHub release of a tag.

The release body follows the organisation's format (see this action's
README):

1. An intro paragraph saying what the release brings, with a link to the
   upgrade or migration guide if there is one.
2. Grouped sections, in the order of `SECTIONS`, with empty ones left out;
   each bullet ends with its issue and pull request numbers, e.g.,
   `(#12, #34)`.
3. `## Commits`: GitHub's generated notes, verbatim (including "New
   Contributors"), without their `## What's Changed` header.
4. Last, GitHub's generated `**Full Changelog**: ...` line.

The curated notes (a file in the calling repository) hold parts 1 and 2;
`publish` adds parts 3 and 4 from GitHub's `generate-notes` API.

Commands:
    `check <notes>`: check that the curated notes exist and are in the
        format (offline).
    `publish`: check the curated notes, the settings and the repository,
        then create the release, or, with `CHECK_ONLY=true`, stop after the
        checks; reads its settings from the environment (see `Settings`).

Needs Python 3.10 or later.

Errors (and warnings) are printed as GitHub annotations to standard error.
Only the standard library and the GitHub CLI (`gh`) are used, so that the
action runs on GitHub-hosted Linux runners without installing anything.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

# Headings of the curated notes, in their order; all are optional
SECTIONS = (
    "Breaking changes",
    "Features",
    "Security",
    "Fixes",
    "Documentation",
    "Maintenance",
)
# Added from GitHub's generated notes, after the curated sections
COMMITS = "Commits"
# Header of GitHub's generated notes, which is dropped
WHATS_CHANGED = "## What's Changed"
# Start of the last line of GitHub's generated notes, which the curated notes
# must not have
FULL_CHANGELOG = "**Full Changelog**"

# ATX headings (`## Title`)
HEADING = re.compile(
    r" {0,3}(?P<level>#{1,6})(?:[ \t]+(?P<title>.*?))??(?:[ \t]+#*)?[ \t]*"
)
# Setext heading underlines (`---`, `===`) and thematic breaks (also `***`,
# `___`), which are rejected: a line of `-` or `=` under a paragraph makes it
# a heading
UNDERLINE = re.compile(r" {0,3}(?:(?:-[ \t]*)+|=+[ \t]*|(?:[*_][ \t]*){3,})")
# Opening and closing lines of fenced code blocks: a block closes with a line
# of the same character, at least as long as the opening one, and nothing else
FENCE = re.compile(r"[ \t]*(?P<marker>`{3,}|~{3,})(?P<rest>.*)")
# Top-level list items (bullets or numbered)
ITEM = re.compile(r"(?:[-*+]|[0-9]+[.)])(?:[ \t]|$)")
# The end of a bullet: its issue and pull request numbers, e.g., `(#12, #34)`
# (only the pull request's if it closes no issue)
REFERENCES = re.compile(r".*\(#[0-9]+(?:[,;][ \t]*#[0-9]+)*\)", re.ASCII)

BULLETS_ONLY = "Sections hold bullets only, e.g., - <change> (#12, #34)"

# Relative links (inline, also of images, or link reference definitions):
# destinations without a scheme (e.g., `https:`, `mailto:`), which GitHub
# resolves against the release page, not the docs
_NO_SCHEME = r"(?:<|(?!<))(?![a-z][a-z0-9+.-]*:)"
RELATIVE = re.compile(
    rf"\]\([ \t]*{_NO_SCHEME}[^)\s<>]"
    rf"|^ {{0,3}}\[[^\]]+\]:[ \t]*{_NO_SCHEME}[^\s<>]",
    re.ASCII | re.IGNORECASE,
)
RELATIVE_LINK = (
    "Relative link (e.g., to a page of the docs): it doesn't resolve in the"
    " GitHub release, so link absolutely (https://...)"
)

# Release versions: `MAJOR.MINOR[.PATCH]`, with an optional `v` and an
# optional pre-release (`a`, `alpha`, `b`, `beta`, `rc`, with an optional
# number), in any letter case, e.g., `v1.2.0`, `1.1`, `0.4.0rc1`,
# `v2.0.0-beta.2`, `1.2.0-RC1`
VERSION = re.compile(
    r"v?(?P<major>[0-9]+)\.(?P<minor>[0-9]+)(?:\.(?P<patch>[0-9]+))?"
    r"(?:[-.]?(?P<pre>a|alpha|b|beta|rc)(?:[-.]?(?P<number>[0-9]+))?)?",
    re.ASCII | re.IGNORECASE,
)
# Rank of pre-releases before the release of the same version
_PRE_RANK = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "rc": 2, None: 3}

Version = tuple[int, int, int, int, int]
Runner = Callable[[Sequence[str]], str]
Release = dict[str, object]


@dataclass(frozen=True)
class Finding:
    """A problem in the structure of curated release notes.

    Attributes:
        line: Number of the line (from 1).
        message: What is wrong.
    """

    line: int
    message: str


class ReleaseError(Exception):
    """A reason not to create the release, with what to do about it."""


def _is_comment(line: str) -> bool:
    """Return whether a line is a single HTML comment, which counts as blank.

    Comments over several lines are not supported. Lines are checked one by
    one, so this is no HTML filter (the notes are published as written).

    Args:
        line: Line of the notes.

    Returns:
        Whether the line, without surrounding whitespace, is one comment.
    """
    text = line.strip()
    return (
        len(text) >= len("<!---->")
        and text.startswith("<!--")
        and text.endswith("-->")
        and "-->" not in text[len("<!--") : -len("-->")]
    )


def _heading_finding(
    number: int, level: int, title: str, last: int | None
) -> Finding | None:
    """Return the problem of a heading of curated notes, if any.

    Args:
        number: Number of the heading's line.
        level: Level of the heading (number of `#`).
        title: Title of the heading.
        last: Index in `SECTIONS` of the last valid section before, if any.

    Returns:
        A finding unless the heading is a section of `SECTIONS` after `last`.
    """
    allowed = ", ".join(SECTIONS)
    if level != 2:
        return Finding(
            number,
            f"Heading of level {level} ('{title}'): only sections"
            f" ('## <title>') are allowed: {allowed}",
        )
    if title == COMMITS:
        return Finding(
            number,
            f"Section '{COMMITS}': the action adds it from GitHub's generated notes",
        )
    if title not in SECTIONS:
        return Finding(
            number, f"Unknown section '{title}': allowed are, in this order: {allowed}"
        )
    if last is not None and SECTIONS.index(title) <= last:
        return Finding(
            number,
            f"Section '{title}' after '{SECTIONS[last]}': sections are in this"
            f" order, each once: {allowed}",
        )
    return None


@dataclass
class _Checker:
    """State of the check of curated release notes, line by line.

    Attributes:
        findings: Findings so far.
        intro: Whether the intro has a paragraph (not only lists or code).
        heading_line: Line of the current heading (0 in the intro).
        valid: Whether the current heading is a valid section.
        bullets: Number of bullets in the current section.
        last: Index in `SECTIONS` of the last valid section, if any.
        item: Lines of the current bullet (number, text).
        fence: Marker of the open fenced code block (e.g., ```` ``` ````), if
            any.
        previous_blank: Whether the previous line is blank.
    """

    findings: list[Finding] = field(default_factory=list)
    intro: bool = False
    heading_line: int = 0
    valid: bool = False
    bullets: int = 0
    last: int | None = None
    item: list[tuple[int, str]] = field(default_factory=list)
    fence: str | None = None
    previous_blank: bool = True

    def run(self, lines: list[str]) -> list[Finding]:
        """Check the lines of curated notes.

        Args:
            lines: Lines of the notes.

        Returns:
            The findings, in the order of their lines.
        """
        for number, line in enumerate(lines, start=1):
            self._line(number, line)
        self._close_section()
        if self.fence:
            self.findings.append(Finding(len(lines), "Unclosed fenced code block"))
        if not self.intro:
            self.findings.append(Finding(max(len(lines), 1), "No intro paragraph"))
        return sorted(self.findings, key=lambda finding: finding.line)

    def _line(self, number: int, line: str) -> None:
        """Check a line.

        Args:
            number: Number of the line.
            line: Text of the line.
        """
        fence = FENCE.fullmatch(line)
        if self.fence or fence:
            self._code(number, line, fence)
            return
        if line.lstrip().startswith(FULL_CHANGELOG):
            self.findings.append(
                Finding(number, f"'{FULL_CHANGELOG}' line: the action adds GitHub's")
            )
        heading = HEADING.fullmatch(line)
        if heading:
            self._heading(number, len(heading["level"]), heading["title"] or "")
            return
        blank = not line.strip() or _is_comment(line)
        if not blank and UNDERLINE.fullmatch(line):
            self.findings.append(
                Finding(
                    number,
                    "Setext heading or thematic break: use no headings but the"
                    " sections, and no rules",
                )
            )
        elif self.heading_line == 0:
            # A paragraph, not a list
            self.intro = self.intro or not (blank or ITEM.match(line))
        elif blank:
            if self.item:
                # As a blank line (also comments)
                self.item.append((number, ""))
        elif ITEM.match(line):
            self._close_item()
            self.item = [(number, line)]
            self.bullets += 1
        elif self.item and (line[0] in " \t" or not self.previous_blank):
            # Indented content of the bullet, or a lazy continuation line of
            # its paragraph
            self.item.append((number, line))
        elif self.valid:
            self.findings.append(Finding(number, BULLETS_ONLY))
        self.previous_blank = blank

    def _code(self, number: int, line: str, fence: re.Match[str] | None) -> None:
        """Check a line of a fenced code block, or a fence.

        Code blocks belong to the intro or to a bullet.

        Args:
            number: Number of the line.
            line: Text of the line.
            fence: Match of `FENCE` on the line, if any.
        """
        if self.fence is None and fence:
            self.fence = fence["marker"]
            # Code blocks in the intro don't make it one
            if self.heading_line and not self.item and self.valid:
                self.findings.append(Finding(number, BULLETS_ONLY))
        elif (
            self.fence
            and fence
            and fence["marker"][0] == self.fence[0]
            and len(fence["marker"]) >= len(self.fence)
            and not fence["rest"].strip()
        ):
            self.fence = None
        if self.heading_line and self.item:
            self.item.append((number, line))
        self.previous_blank = False

    def _heading(self, number: int, level: int, title: str) -> None:
        """Check a heading, which starts a section.

        Args:
            number: Number of the heading's line.
            level: Level of the heading (number of `#`).
            title: Title of the heading.
        """
        self._close_section()
        title = title.strip()
        finding = _heading_finding(number, level, title, self.last)
        if finding:
            self.findings.append(finding)
        else:
            self.last = SECTIONS.index(title)
        self.heading_line, self.valid, self.bullets = number, finding is None, 0
        if not self.intro:
            self.findings.append(
                Finding(number, "No intro paragraph before the first section")
            )
            self.intro = True
        self.previous_blank = False

    def _close_item(self) -> None:
        """Check that the current bullet ends with its numbers, and end it."""
        content = [(number, line) for number, line in self.item if line.strip()]
        # The numbers may be wrapped over lines
        text = " ".join(line.strip() for _, line in content)
        # Only in valid sections, as invalid headings have findings already
        if self.valid and content and not REFERENCES.fullmatch(text):
            self.findings.append(
                Finding(
                    content[-1][0],
                    "Bullet doesn't end with its issue and pull request"
                    " numbers, e.g., (#12, #34)",
                )
            )
        self.item = []

    def _close_section(self) -> None:
        """End the current bullet and section; valid ones must have bullets."""
        self._close_item()
        if self.valid and self.bullets == 0:
            self.findings.append(Finding(self.heading_line, "Empty section"))


def check(markdown: str) -> list[Finding]:
    """Return the problems in the structure of curated release notes.

    Args:
        markdown: Curated release notes (parts 1 and 2 of the format).

    Returns:
        The findings, in the order of their lines; none if the notes have an
        intro paragraph (lists and code blocks alone don't count), then only
        headings of `SECTIONS` (level 2, each once, in their order, none
        empty), holding bullets only, each ending with its issue and pull
        request numbers, none of the parts that the action adds
        (`## Commits`, the `**Full Changelog**` line), and no relative links
        (`RELATIVE`). An HTML comment on a line of its own counts as a blank
        line.
    """
    lines = markdown.removeprefix("\ufeff").splitlines()
    findings = _Checker().run(lines)
    for number, line in enumerate(lines, start=1):
        if RELATIVE.search(line):
            findings.append(Finding(number, RELATIVE_LINK))
    return sorted(findings, key=lambda finding: finding.line)


def body(curated: str, generated: str) -> tuple[str, list[str]]:
    """Return the body of a release: curated notes, then generated ones.

    Args:
        curated: Curated release notes (parts 1 and 2 of the format); they
            are not checked here (see `check`).
        generated: GitHub's generated notes (the `body` of the
            `generate-notes` response).

    Returns:
        The body: the curated notes, then `## Commits` with the generated
        notes without their `## What's Changed` header (left out if they list
        no changes), whose last line is the `**Full Changelog**` line; and
        warnings about unexpected generated notes, which are then kept as
        they are (so that an unexpected format doesn't fail the release
        after its artefacts were published).
    """
    # Split at line breaks only (`splitlines` also splits at, e.g., U+2028,
    # which could make a title of a pull request a heading)
    text = generated.strip().replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    warnings = []
    # Also after a comment (e.g., with a configuration in `.github/release.yml`)
    if WHATS_CHANGED in lines:
        lines.remove(WHATS_CHANGED)
    if not lines or not lines[-1].startswith(f"{FULL_CHANGELOG}: "):
        warnings.append(f"Generated notes don't end with a '{FULL_CHANGELOG}: ' line")
        changes, last = "\n".join(lines).strip(), []
    else:
        changes, last = "\n".join(lines[:-1]).strip(), [lines[-1]]
    parts = [curated.removeprefix("\ufeff").strip()]
    if changes:
        parts.append(f"## {COMMITS}\n\n{changes}")
    return "\n\n".join(parts + last) + "\n", warnings


def parse_version(tag: str) -> Version | None:
    """Return the sort key of a release version, if a tag is one.

    Args:
        tag: Name of a tag, e.g., `v1.2.0`, `1.1` or `0.4.0rc1`.

    Returns:
        Major, minor and patch number, rank of the pre-release (`a` < `b` <
        `rc` < none) and its number, which sort as the versions do; `None`
        if the tag is no release version (`VERSION`).
    """
    match = VERSION.fullmatch(tag)
    if not match:
        return None
    return (
        int(match["major"]),
        int(match["minor"]),
        int(match["patch"] or 0),
        _PRE_RANK[match["pre"].lower() if match["pre"] else None],
        int(match["number"] or 0),
    )


def is_prerelease(tag: str, policy: str) -> bool:
    """Return whether the release of a tag is a pre-release.

    Args:
        tag: Name of the release's tag.
        policy: `true`, `false`, or `auto`: a pre-release if the major
            version is 0, or the version is an `a`, `b` or `rc` one.

    Returns:
        Whether the release is a pre-release.

    Raises:
        ReleaseError: If the policy is unknown, or `auto` and the tag is no
            release version.
    """
    if policy in ("true", "false"):
        return policy == "true"
    if policy != "auto":
        raise ReleaseError(
            f"Unknown pre-release policy '{policy}': use auto, true or false"
        )
    version = parse_version(tag)
    if version is None:
        raise ReleaseError(
            f"'{tag}' is no release version (e.g., v1.2.0, 1.2.0rc1): set"
            " `prerelease` to true or false"
        )
    return version[0] == 0 or version[3] != _PRE_RANK[None]


def previous_release(tag: str, releases: list[Release], tags: list[str]) -> str | None:
    """Return the tag that the generated notes of a release start from.

    Args:
        tag: Name of the release's tag.
        releases: Releases of the repository (as the REST API lists them).
        tags: Names of all tags of the repository.

    Returns:
        The tag of the highest published release (no draft) with a lower
        version, pre-releases included, except, for a final release, its own
        pre-releases (so that `1.2.0` starts at `1.1.0`, not at `1.2.0rc1`);
        without one, the highest such version tag (e.g., of releases made
        before the repository published GitHub releases); `None` without
        either (or if the tag is no release version), so that GitHub picks
        the start.
    """
    version = parse_version(tag)
    if version is None:
        return None
    if version[3] == _PRE_RANK[None]:
        # Below all pre-releases of the same version
        version = (*version[:3], -1, 0)

    def highest(names: list[str]) -> str | None:
        """Return the name with the highest version lower than the tag's.

        Args:
            names: Names of tags.

        Returns:
            The name, or `None` if no name has a lower version.
        """
        lower = [
            (key, name)
            for name in names
            if (key := parse_version(name)) is not None and key < version
        ]
        return max(lower)[1] if lower else None

    published = [str(r["tag_name"]) for r in releases if not r.get("draft")]
    return highest(published) or highest(tags)


def is_latest(tag: str, prerelease: bool, releases: list[Release]) -> bool | None:
    """Return whether the release of a tag becomes the latest release.

    Args:
        tag: Name of the release's tag.
        prerelease: Whether the release is a pre-release.
        releases: Releases of the repository (as the REST API lists them).

    Returns:
        `False` for pre-releases (GitHub never makes them the latest), and if
        a published release (no draft, no pre-release) has a higher version
        (e.g., for a patch of an older line); `None` (GitHub decides) if the
        tag is no release version; else `True`.
    """
    if prerelease:
        return False
    version = parse_version(tag)
    if version is None:
        return None
    return not any(
        (key := parse_version(str(r["tag_name"]))) is not None and key > version
        for r in releases
        if not r.get("draft") and not r.get("prerelease")
    )


def _gh(args: Sequence[str]) -> str:
    """Run the GitHub CLI and return its standard output.

    Args:
        args: Arguments of `gh`.

    Returns:
        The standard output.

    Raises:
        ReleaseError: If `gh` fails; with its standard error.
    """
    result = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ReleaseError(
            f"{shlex.join(['gh', *args])} failed: {result.stderr.strip()}"
        )
    return result.stdout


@dataclass(frozen=True)
class Settings:
    """Settings of `publish`, from the environment of the action's step.

    Attributes:
        repository: `<owner>/<repo>` (`GH_REPO`).
        tag: Name of the release's tag (`TAG`).
        notes: Path of the curated notes (`NOTES`).
        prerelease: Pre-release policy (`PRERELEASE`: auto, true or false).
        previous: Tag that the generated notes start from (`PREVIOUS_TAG`);
            empty to detect it (see `previous_release`).
        title: Title of the release (`TITLE`); empty for the tag.
        check_only: Whether to only check the release (`CHECK_ONLY`: true
            or false).
    """

    repository: str
    tag: str
    notes: Path
    prerelease: str = "auto"
    previous: str = ""
    title: str = ""
    check_only: bool = False

    @classmethod
    def from_env(cls, env: dict[str, str]) -> Settings:
        """Read the settings from environment variables.

        Args:
            env: Environment variables.

        Returns:
            The settings.

        Raises:
            ReleaseError: If `GH_REPO`, `TAG` or `NOTES` is missing, or
                `CHECK_ONLY` is neither `true` nor `false`.
        """
        missing = [name for name in ("GH_REPO", "TAG", "NOTES") if not env.get(name)]
        if missing:
            raise ReleaseError(f"Not set: {', '.join(missing)}")
        check_only = (env.get("CHECK_ONLY") or "false").lower()
        if check_only not in ("true", "false"):
            raise ReleaseError(
                f"Invalid check-only '{env['CHECK_ONLY']}': use true or false"
            )
        return cls(
            check_only=check_only == "true",
            repository=env["GH_REPO"],
            tag=env["TAG"],
            notes=Path(env["NOTES"]),
            prerelease=env.get("PRERELEASE") or "auto",
            previous=env.get("PREVIOUS_TAG", ""),
            title=env.get("TITLE", ""),
        )


def read_notes(path: Path) -> str:
    """Read curated notes and check them.

    Args:
        path: Path of the curated notes.

    Returns:
        The notes.

    Raises:
        ReleaseError: If the notes can't be read or have findings; the
            findings are printed as error annotations first.
    """
    try:
        curated = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ReleaseError(
            f"Can't read the curated notes {path}: {error}; add them in a pull"
            " request before the tag"
        ) from error
    findings = check(curated)
    for finding in findings:
        print(
            f"::error file={path},line={finding.line}::{finding.message}",
            file=sys.stderr,
        )
    if findings:
        raise ReleaseError(f"The curated notes {path} are not in the format")
    return curated


def _is_ours(
    release: Release, settings: Settings, curated: str, prerelease: bool
) -> bool:
    """Return whether an existing release is the one these settings create.

    The generated part of the body isn't compared, as it may differ on a
    re-run (e.g., if a release published since changes the previous tag).

    Args:
        release: The existing release (as the REST API lists it).
        settings: Settings of the release.
        curated: Curated notes of the release.
        prerelease: Whether the release is a pre-release.

    Returns:
        Whether the release's body starts with the curated notes (followed
        by nothing or a blank line), and its title and pre-release flag are
        those of the settings.
    """
    text = str(release.get("body") or "").replace("\r\n", "\n").strip()
    notes = curated.removeprefix("﻿").strip()
    return (
        text.startswith(notes)
        and (text == notes or text[len(notes) :].startswith("\n\n"))
        and release.get("name") == (settings.title or settings.tag)
        and bool(release.get("prerelease")) is prerelease
    )


def publish(settings: Settings, gh: Runner = _gh) -> tuple[str, str]:
    """Create the GitHub release of a tag, with curated and generated notes.

    Everything that can fail is checked before the release is created, and,
    with `check_only`, nothing else is done, so that the `prepare` job of a
    release workflow fails before any artefact is published.

    Args:
        settings: Settings of the release.
        gh: Runs the GitHub CLI with arguments and returns its output.

    Returns:
        The body of the release and its URL; with `check_only`, the curated
        notes and an empty URL.

    Raises:
        ReleaseError: If the notes have findings, the pre-release policy
            doesn't apply, the tag or the previous tag doesn't exist, or a
            release (or a draft) of the tag exists already, unless it is a
            published release with these curated notes, title and pre-release
            flag (see `_is_ours`; e.g., when a job is re-run
            after a creation that succeeded but wasn't reported); or if `gh`
            fails.
    """
    curated = read_notes(settings.notes)
    prerelease = is_prerelease(settings.tag, settings.prerelease)
    repo = settings.repository
    pages = json.loads(
        gh(["api", "--paginate", "--slurp", f"repos/{repo}/releases?per_page=100"])
    )
    releases = [release for page in pages for release in page]
    existing = [r for r in releases if r["tag_name"] == settings.tag]
    if any(r.get("draft") for r in existing):
        raise ReleaseError(
            f"A draft release of {settings.tag} exists: delete it (e.g., of a"
            " failed attempt) and re-run"
        )
    if existing and settings.check_only:
        raise ReleaseError(
            f"The release {settings.tag} exists already: releases are not"
            " changed or replaced, so release the next version"
        )
    tags = gh(
        [
            "api",
            "--paginate",
            f"repos/{repo}/git/matching-refs/tags",
            "--jq",
            '.[].ref | ltrimstr("refs/tags/")',
        ]
    ).split()
    for name, kind in ((settings.tag, "tag"), (settings.previous, "previous tag")):
        if name and name not in tags:
            raise ReleaseError(f"The {kind} {name} doesn't exist on GitHub")
    if settings.check_only:
        # Generating notes needs `contents: write`, which `prepare` lacks
        return curated, ""
    previous = settings.previous or previous_release(settings.tag, releases, tags)
    args = ["api", f"repos/{repo}/releases/generate-notes"]
    args += ["-f", f"tag_name={settings.tag}"]
    if previous:
        args += ["-f", f"previous_tag_name={previous}"]
    generated = gh([*args, "--jq", ".body"])
    text, warnings = body(curated, generated)
    for warning in warnings:
        print(f"::warning::{warning}; kept as they are", file=sys.stderr)
    if existing:
        release = existing[0]
        if _is_ours(release, settings, curated, prerelease):
            print(
                f"::notice::The release {settings.tag} exists already, with these"
                " curated notes, title and pre-release flag (created by an"
                " earlier attempt)",
                file=sys.stderr,
            )
            return str(release.get("body") or ""), str(release.get("html_url") or "")
        raise ReleaseError(
            f"The release {settings.tag} exists already, with other notes, title"
            " or pre-release flag: releases are not changed or replaced, so"
            " release the next version"
        )
    latest = is_latest(settings.tag, prerelease, releases)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".md", delete=False
    ) as file:
        file.write(text)
    try:
        url = gh(
            [
                "release",
                "create",
                settings.tag,
                "--verify-tag",
                "--title",
                settings.title or settings.tag,
                "--notes-file",
                file.name,
                f"--prerelease={str(prerelease).lower()}",
                *([] if latest is None else [f"--latest={str(latest).lower()}"]),
            ]
        )
    finally:
        os.unlink(file.name)
    return text, url.strip()


def _write(env_file: str | None, text: str) -> None:
    """Append text to a file that GitHub Actions reads, if it is set.

    Args:
        env_file: Path of the file (e.g., `GITHUB_OUTPUT`), or `None`.
        text: Text to append.
    """
    if env_file:
        with open(env_file, "a", encoding="utf-8") as file:
            file.write(text)


def main(
    argv: Sequence[str] | None = None,
    env: dict[str, str] | None = None,
    gh: Runner = _gh,
) -> int:
    """Run a command (see the module's docstring).

    Args:
        argv: Command-line arguments, without the program name; those of the
            process if `None`.
        env: Environment variables; those of the process if `None`.
        gh: Runs the GitHub CLI (see `publish`).

    Returns:
        The exit status: 0 on success, 1 on any error.
    """
    parser = argparse.ArgumentParser(
        description="Check curated release notes and create the GitHub release."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    check_parser = commands.add_parser("check", help="check curated notes")
    check_parser.add_argument("notes", type=Path, help="curated notes")
    commands.add_parser("publish", help="create the release (settings: env)")
    args = parser.parse_args(argv)
    env = dict(os.environ) if env is None else env
    try:
        if args.command == "check":
            read_notes(args.notes)
            return 0
        settings = Settings.from_env(env)
        text, url = publish(settings, gh)
    except ReleaseError as error:
        print(f"::error title=Publish release::{error}", file=sys.stderr)
        return 1
    if settings.check_only:
        return 0
    print(url)
    _write(env.get("GITHUB_OUTPUT"), f"url={url}\n")
    _write(env.get("GITHUB_STEP_SUMMARY"), text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
