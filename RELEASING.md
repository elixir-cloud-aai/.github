# Releasing

The composite actions in `actions/<name>/` are used by the other
repositories of the organisation, which pin them to the commit of a release:

```yaml
- uses: elixir-cloud-aai/.github/actions/<name>@<40-character SHA> # vX.Y.Z
```

The maintainer releases them from signed version tags, as in the other
repositories of the organisation. Dependabot (`github-actions` ecosystem) in
each calling repository then proposes to bump the pin to the commit of the
latest release and updates the `# vX.Y.Z` comment. A change here reaches a
repository only when that repository merges the bump, so every release must
be safe to adopt on its own.

## When to release

Release when a change to a file under `actions/` other than Markdown, i.e.,
something that callers run, has been merged. Changes to docs, CI, tests or
workflow templates alone don't need a release, as every release gives each
caller a Dependabot pull request; they appear in the notes of the next
release. A release may cover several merged pull requests. Milestones are
not used here: a change must be complete and safe for callers when it is
merged.

## How to release

1. **Pick the version** (see [Versions](#versions)) from the Conventional
   Commits messages (the pull request titles) since the last release.
2. **Release preparation:** open a pull request `docs: add notes of vX.Y.Z`
   that adds the curated notes `docs/releases/vX.Y.Z.md` (see [Release
   notes](#release-notes)), and merge it once CI passed. A draft from the
   commits since the last release (`vA.B.C`; review it and delete its
   `TODO` line):

   ```sh
   GH_REPO=elixir-cloud-aai/.github bash .github/scripts/release.sh \
     draft vX.Y.Z vA.B.C origin/main > docs/releases/vX.Y.Z.md
   ```

3. **Tag** the merged commit on `main` with a signed annotated tag, once CI
   passed for it, and push the tag:

   ```sh
   git switch main && git pull --ff-only
   git tag -s vX.Y.Z -m vX.Y.Z
   git push origin vX.Y.Z
   ```

4. **Approve** the `Publish release` job of the `Release` workflow run in
   the `release` environment.

The `Release` workflow (`.github/workflows/release.yml`) runs for every
pushed `v*` tag. Its `prepare` job (`Prepare release`) fails, before
anything is published, unless:

- the tag is annotated and has a signature that GitHub verified;
- its commit is on `main`, and CI passed for the push of that commit;
- the version is the next one after the last release
  (`.github/scripts/release.sh check`): one major, minor or patch step
  after the highest `vX.Y.Z` tag on an ancestor of the commit, and at
  least the step that the commits since need which changed the actions; a
  release without such a commit only gets a warning;
- `docs/releases/vX.Y.Z.md` exists in the tagged commit and is finished
  and in the format below (`release.sh lint`).

The `publish` job (`Publish release`) then waits for approval in the
`release` environment and creates the GitHub release `vX.Y.Z` with the
curated notes followed by GitHub's generated notes (`release.sh notes`). A
failed run can be re-run once the cause is fixed; a re-run after the
release exists only updates its notes. Release tags are protected by tag
rulesets (only release tags; created by the maintainer only; immutable),
and tags and releases are never changed or reused: a release with a mistake
(e.g., a wrong version) is fixed by the next release. If `Prepare release`
fails for a reason in the tagged commit (e.g., the notes), nothing is
published, but the tag stays: fix the cause in a pull request and release
the next version. A re-run of a run whose release exists changes nothing;
edit the notes by hand if they need more context.

## Repository settings

The maintainer keeps these settings, which the workflow relies on:

- **Environment `release`** with the leads team as required reviewers, so
  that `Publish release` waits for approval.
- **Tag rulesets** as in the other repositories: `v*` tags other than
  `vX.Y.Z` are prohibited; release tags can only be created by the
  maintainer (bypass), not updated or deleted.
- **Immutable releases.**
- A signing key (GPG or SSH) of the maintainer registered on GitHub, so
  that GitHub verifies the tag signatures.

## Versions

- Releases are semantic versions, `vMAJOR.MINOR.PATCH`, for the repository
  as a whole (not per action).
- Breaking changes, such as a new required input, a removed input or output,
  or changed check semantics, only go into a new major version: mark them in
  the pull request title (e.g., `feat(gate)!: …`) and say in its description
  what callers have to change.
- New actions and new inputs are features (`feat`), even if they only serve
  CI.
- There are no moving tags (`v1`, `latest`). Callers pin commits, and
  Dependabot bumps a pin `@<SHA> # vX.Y.Z` whose commit carries a version tag
  to the commit of the latest version tag. It moves a pin to a commit
  without a version tag to the latest commit of `main` instead, and leaves
  the comment as it was, so pin the commit of a release.

## Release notes

The curated notes `docs/releases/vX.Y.Z.md` start with the title
`# vX.Y.Z` (which the release leaves out), followed by:

1. An intro paragraph that names the changed actions and, for a major
   release, points to the breaking changes and says what callers have to
   change.
2. Grouped sections, empty ones left out, in this order:
   `## Breaking changes`, `## Features`, `## Security`, `## Fixes`,
   `## Documentation`, `## Maintenance`. Each bullet ends with its issue and
   pull request numbers. The draft (`release.sh draft`) puts breaking
   changes of the actions (as for the version) into `## Breaking changes`;
   otherwise scope `security` into `## Security`, `feat` into
   `## Features`, `fix` into `## Fixes`, `docs` into `## Documentation`,
   and all other types into `## Maintenance`, where Dependabot's updates
   (`build(deps)`) share one bullet.

No other headings and no `TODO`. The workflow appends:

1. `## Commits`: GitHub's generated notes, without their `## What's Changed`
   header.
2. The last line: GitHub's generated `**Full Changelog**: …` line.
