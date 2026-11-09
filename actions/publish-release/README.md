# Publish release

Creates the GitHub release of a tag in the organisation's release notes
format, from the release workflow:

1. the **curated notes** of the release, a file in the calling repository
   (e.g., `docs/releases/1.2.0.md`): an intro paragraph saying what the
   release brings, with a link to the upgrade or migration guide if there is
   one, then grouped sections, empty ones left out, in this order:
   `## Breaking changes`, `## Features`, `## Security`, `## Fixes`,
   `## Documentation`, `## Maintenance`; each bullet ends with its issue and
   pull request numbers, e.g., `(#12, #34)`;
2. `## Commits`: GitHub's [generated release notes][generated-notes],
   verbatim (including "New Contributors"), without their
   `## What's Changed` header;
3. last, GitHub's generated `**Full Changelog**: …` line.

With `check-only`, the action only checks that the release can be created
(the curated notes, the settings, the tags and the existing releases; see
[Behaviour](#behaviour)), so that the `prepare` job of the release workflow
fails before anything is published.

## Usage

Pin the commit and version of a
[release](https://github.com/elixir-cloud-aai/.github/releases) of this
repository; Dependabot (`github-actions` ecosystem) in the calling
repository bumps the pin to new releases (see
[RELEASING.md](../../RELEASING.md)). The action runs on GitHub-hosted Linux
runners (it needs Python 3.10 or later as `python3`, and `gh`) and needs a
checkout of the tagged commit for the curated notes:

```yaml
jobs:
  prepare:
    name: Prepare release
    permissions:
      contents: read
    steps:
      - name: Check out repository
        uses: actions/checkout@<commit SHA> # vX.Y.Z
        with:
          persist-credentials: false
      # ... check the tag, set `version` ...
      - name: Check release notes
        uses: elixir-cloud-aai/.github/actions/publish-release@<commit SHA> # vX.Y.Z
        with:
          notes: docs/releases/${{ steps.version.outputs.version }}.md
          check-only: "true"

  # ... build, scan and publish the artefacts ...

  publish:
    name: Publish release
    needs: [prepare, push]
    permissions:
      contents: write
    steps:
      - name: Check out repository
        uses: actions/checkout@<commit SHA> # vX.Y.Z
        with:
          persist-credentials: false
      - name: Create release
        uses: elixir-cloud-aai/.github/actions/publish-release@<commit SHA> # vX.Y.Z
        with:
          notes: docs/releases/${{ needs.prepare.outputs.version }}.md
```

Run `publish` last, after all artefacts are published, so that the release
appears only once everything it announces exists.

## Inputs

- `notes` (required): the path of the curated notes, relative to the
  workspace.
- `tag`: the tag of the release, which must exist on GitHub
  (`gh release create --verify-tag`); default is the tag of the workflow run
  (`github.ref_name`).
- `prerelease`: `auto` (default), `true` or `false`. `auto` makes a
  pre-release of versions below 1.0.0 and of `a`, `b` and `rc` versions
  (e.g., `v0.4.0`, `1.2.0rc1`, `v2.0.0-beta.1`), and fails for tags that are
  no versions.
- `previous-tag`: the tag that GitHub's generated notes start from; it must
  exist. Default is the highest lower version with a published release
  (pre-releases included, drafts not), except, for a final release, its own
  pre-releases, so that `## Commits` of `1.2.0` covers everything since
  `1.1.0`, not since `1.2.0rc1`; without one, the highest such version tag
  (e.g., of releases made before the repository published GitHub
  releases); without either, GitHub picks the start.
- `title`: the title of the release; default is the tag.
- `check-only`: `true` to only check that the release can be created,
  `false` (default) to create it; other values fail.
- `token`: the token for the GitHub API; default is the job's
  `GITHUB_TOKEN`, which needs `contents: write`, or `contents: read` with
  `check-only`.

## Outputs

- `url`: the URL of the created release (empty with `check-only`).

## Behaviour

- **Checks first:** the curated notes must exist and be in the format: an
  intro paragraph (lists and code blocks alone don't count), then only the
  sections above (level 2, each once, in order, none empty), holding bullets
  only, each ending with its numbers; no `## Commits` section and no
  `**Full Changelog**` line, which the action adds; no relative links, which
  don't resolve on the release page. An HTML comment on a line of its own
  counts as a blank line (and stays in the release, invisible). Findings are
  error annotations with file and line. Then the settings: the
  `prerelease` policy (`auto` needs a version tag), the tag and
  `previous-tag` must exist. All of this, and the existing releases below,
  is also checked with `check-only`, before anything is published (but
  drafts are visible only with `contents: write`, so `check-only` with
  `contents: read` doesn't see them).
- **No changes to existing releases:** if a draft of the tag exists, the
  action fails before it generates notes: delete the draft (e.g., of a
  failed attempt) and re-run. If a published release of the tag exists,
  `check-only` fails (release the next version); creating it passes without
  changes only if the release has the same body (e.g., when the job is
  re-run after a creation that succeeded but wasn't reported), and fails
  otherwise. Published releases are never changed (with immutable releases,
  they can't be).
- **Latest release:** a pre-release is never the latest release; a release
  is the latest unless a published release (not a pre-release) has a
  higher version, e.g., for a patch of an older line. For tags that are no
  versions, GitHub decides.
- **Unexpected generated notes** (no final `**Full Changelog**` line) are
  kept as they are, with a warning, so that a change of GitHub's format
  doesn't fail the release after the artefacts are published.
- The body of the release also goes to the job summary.

The action's script, [`publish.py`](publish.py), uses the Python standard
library and `gh` only; its tests are in
[`tests/publish-release/`](../../tests/publish-release/).

[generated-notes]: <https://docs.github.com/en/repositories/releasing-projects-on-github/automatically-generated-release-notes>
