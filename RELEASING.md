# Releasing

The composite actions in `actions/<name>/` are used by the other
repositories of the organisation, which pin them by commit:

```yaml
- uses: elixir-cloud-aai/.github/actions/<name>@<40-character SHA> # vX.Y.Z
```

Dependabot bumps these pins in the calling repositories, but only to commits
that carry a release tag. A change here reaches a repository when that
repository merges the bump, so every release must be safe to adopt on its
own.

## Versions

- Releases are semantic versions, `vMAJOR.MINOR.PATCH`, for the repository
  as a whole (not per action).
- Breaking changes, such as a new required input, a removed input or output,
  or changed check semantics, only go into a new major version.
- There are no moving tags (`v1`, `latest`): callers pin commits, and
  Dependabot needs the exact tags to update `@<sha> # vX.Y.Z`.
- The first release, `v1.0.0`, is cut once the first action has landed.

## Steps

1. Make sure that CI passed on the commit of `main` to release, and that its
   milestone `vX.Y.Z` has no open issues left.
2. Create a signed, annotated tag on that commit and push it:

   ```sh
   git tag -s vX.Y.Z -m "vX.Y.Z" <commit>
   git push origin vX.Y.Z
   ```

3. Draft a GitHub release from the tag, with notes in the organisation's
   format (below), and publish it. Immutable releases are switched on for
   this repository, so a published release and its tag can't be changed or
   reused: fix a mistake with a new patch release.

## Release notes

1. An intro paragraph on what the release brings. For a major release, say
   exactly what callers have to change.
2. Grouped sections, empty ones left out, in this order:
   `## Breaking changes`, `## Features`, `## Security`, `## Fixes`,
   `## Documentation`, `## Maintenance`. Each bullet ends with its issue and
   pull request numbers.
3. `## Commits`: GitHub's generated notes, copied verbatim (including "New
   Contributors"), without their `## What's Changed` header.
4. The last line is GitHub's generated `**Full Changelog**: …` line.
