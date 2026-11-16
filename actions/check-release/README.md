# Check release

Checks the tag and the commit of a release in the `prepare` job of the
release workflow, so that the workflow fails before anything is built or
published. The release fails unless:

- the **tag** is annotated (`git tag -s`), its tag object has the tag's
  name, it has a signature that GitHub verified, and it points to the
  commit of the run (`github.sha`; e.g., not moved since the push);
- the tag is a **release version**: `tag-prefix` (default `v`), then
  `MAJOR.MINOR.PATCH` without leading zeros, optionally with a pre-release
  `a`, `alpha`, `b`, `beta` or `rc` and its number (e.g., `v1.2.0`,
  `v1.2.0rc1`, `v2.0.0-alpha.50`, `v1.0.0-rc1`, `chart-v1.0.0`). This is
  stricter than what publish-release accepts (lower case only, patch and
  pre-release number required), so that all repositories tag alike;
- the commit is on the **release branch** (`branch`, default `main`): the
  head of the branch (looked up as a branch, so a tag of the same name
  doesn't count) or one of its ancestors;
- **CI passed** for the commit: the CI workflow (`workflow`, default
  `ci.yml`) has a successful run for a push of the commit (to `ci-branch`,
  default `dev`). Runs for pull requests test merge commits, not the commit
  itself, so they don't count; re-runs that succeeded do;
- the **citation metadata** (`citation`, default `CITATION.cff`) of the
  commit has the release version as `version` and a `date-released`
  (`YYYY-MM-DD`) that is not in the future (in any time zone): Zenodo
  archives the release with the citation metadata of the tagged commit.
  The date isn't compared with the previous release, so a date left over
  from it passes: the release-prep pull request sets both;
- the **package version** that the caller passes (`version`), if any, is
  the release version.

All checks run, and each finding is an error annotation; only the checks
that need the version (citation metadata, package version) are skipped if
the tag is no release version. Everything is read from the GitHub API at
the commit, nothing from the checkout, so the action runs nothing of the
tagged commit and needs no checkout (only the caller's step that reads the
package version does).

## Branches

The defaults fit repositories that develop on `dev`, where CI runs for
each push, and move `main` forward to the release commit
(`git push origin <sha>:main`, a fast-forward), so that the commit on
`main` is the very commit that CI tested on `dev`. If changes are merged
into `main` directly (as in this repository), the release commit's CI run
is a push to `main`: set `ci-branch: main`, or empty for a push to any
branch.

## Usage

Pin the commit and version of a
[release](https://github.com/elixir-cloud-aai/.github/releases) of this
repository; Dependabot (`github-actions` ecosystem) in the calling
repository bumps the pin to new releases (see
[RELEASING.md](../../RELEASING.md)). The action runs on GitHub-hosted Linux
runners (it needs Python 3.10 or later as `python3`, and `gh`). The job
needs `contents: read` and `actions: read`:

```yaml
jobs:
  prepare:
    name: Prepare release
    runs-on: ubuntu-latest
    permissions:
      contents: read
      # Read the CI runs of the release commit
      actions: read
    outputs:
      version: ${{ steps.release.outputs.version }}
      prerelease: ${{ steps.release.outputs.prerelease }}
      sha: ${{ steps.release.outputs.sha }}
    steps:
      # For the package version and the release notes; check-release
      # itself needs no checkout
      - name: Check out repository
        uses: actions/checkout@<commit SHA> # vX.Y.Z
        with:
          persist-credentials: false
      # Optional: the package version, compared with the tag
      - name: Read package version
        id: package
        run: echo "version=$(jq -r .version package.json)" >> "${GITHUB_OUTPUT}"
      - name: Check release tag and commit
        id: release
        uses: elixir-cloud-aai/.github/actions/check-release@<commit SHA> # vX.Y.Z
        with:
          version: ${{ steps.package.outputs.version }}
      - name: Check release notes
        uses: elixir-cloud-aai/.github/actions/publish-release@<commit SHA> # vX.Y.Z
        with:
          notes: docs/releases/${{ steps.release.outputs.version }}.md
          commit: ${{ steps.release.outputs.sha }}
          check-only: "true"
```

Later jobs use the outputs of `prepare` (e.g.,
`needs.prepare.outputs.version`) instead of parsing the tag again. The
`release` environment's protection rules (required reviewers) are what
control publishing; these checks guard against mistakes, such as releases
of unmerged or untested commits.

Repositories that release from another branch set `branch` (e.g.,
cloud-components: `branch: dev`); tags with a prefix set `tag-prefix`
(e.g., `chart-v` for `chart-v1.0.0`, `my-plugin-v` for
`my-plugin-v1.2.0`).

## Inputs

- `tag`: the tag of the release; default is the tag of the workflow run
  (`github.ref_name`).
- `commit`: the commit SHA that the tag must point to; default is the
  commit of the workflow run (`github.sha`).
- `tag-prefix`: the part of the tag before the version; default `v`. Empty
  for tags without a prefix (e.g., `1.2.0`).
- `branch`: the branch that the commit must be on; default `main`.
- `workflow`: the file name of the CI workflow that must have passed for a
  push of the commit; default `ci.yml`.
- `ci-branch`: the branch of that push; default `dev`. Empty for a push to
  any branch.
- `citation`: the path of the citation metadata in the repository; default
  `CITATION.cff`. Empty for no check (repositories without citation
  metadata). Only one-line values of the top-level `version` and
  `date-released` are read (plain or quoted), as `CITATION.cff` files set
  them.
- `version`: the package version, as written in the package metadata (e.g.,
  `pyproject.toml`, `package.json`, `pom.xml` or `Chart.yaml`), which must
  be exactly the release version; default is no check. The caller reads it,
  as each ecosystem has its own file.
- `token`: the token for the GitHub API; default is the job's
  `GITHUB_TOKEN`, which needs `contents: read` and `actions: read`.

## Outputs

Set only if all checks passed:

- `version`: the release version, the tag without `tag-prefix` (e.g.,
  `1.2.0`).
- `prerelease`: `true` for versions below 1.0.0 and for `a`, `b` and `rc`
  versions, else `false`: the rule of `prerelease: auto` of
  [publish-release](../publish-release/README.md).
- `sha`: the commit SHA of the release (`commit`).

## Tests

The action's script, [`check.py`](check.py), uses the Python standard
library and `gh` only. CI tests it on three levels:

- the script's unit tests in
  [`tests/check-release/`](../../tests/check-release/) (`unittest`, against
  a stand-in for `gh`): versions, citation metadata, settings and each
  check;
- the script against this repository's real API: a lightweight tag
  (`v1.0.0`), a moved tag, a commit on no branch and without CI runs, a
  tag that is no release version, and missing citation metadata, each with
  its expected error;
- the action itself, once, on this repository's tag `v1.2.0`: inputs
  reaching the script, and its outputs.
