# PR title

Checks that a pull request title follows the organisation's convention, as
the title becomes the commit message of the squash merge (GitHub appends the
pull request number, as in `(#123)`, which doesn't count):

- the format `<type>[(<scope>)][!]: <description>`
  ([Conventional Commits](https://www.conventionalcommits.org/)), with one of
  the allowed types;
- at most 50 characters **in total**, scope included;
- a description that doesn't start with a capitalised word (`Add`), while
  acronyms and names with more capitals or digits (`API`, `OpenAPI`, `S3`)
  are fine; a plain capitalised name (`Docker`) can't be told from a verb
  and fails;
- no trailing period, ellipsis or whitespace, and only one line.

Lengths count Unicode code points, so a decomposed accent counts twice. The
action is for `pull_request` events; an empty title fails.

The check reports every rule that failed, with the title's length. It is a
plain script: no token, no third-party action.

## Usage

Add the workflow from Actions → New workflow (template "PR title", from
`workflow-templates/pr-title.yml`), or add `.github/workflows/pr-title.yml`
by hand. Pin the commit and version of a
[release](https://github.com/elixir-cloud-aai/.github/releases) of this
repository; Dependabot (`github-actions` ecosystem) in the calling
repository bumps the pin to new releases (see
[RELEASING.md](../../RELEASING.md)):

```yaml
---
# Checks that pull request titles follow the organisation's convention, as
# they become the commit messages of squash merges. A workflow of its own,
# so that editing a title reruns only this check, not CI
name: PR title
on:
  pull_request:
    types: [opened, edited, synchronize, reopened, ready_for_review]

permissions: {}

# A newer run (e.g. after the title was edited again) cancels older ones, so
# that the check reports on the current title
concurrency:
  group: pr-title-${{ github.event.pull_request.number }}
  cancel-in-progress: true

jobs:
  title:
    name: PR title
    # Dependabot's titles often exceed 50 characters; a skipped job counts
    # as passed for required checks
    if: github.event.pull_request.user.login != 'dependabot[bot]'
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - name: Check PR title
        uses: elixir-cloud-aai/.github/actions/pr-title@<commit SHA> # vX.Y.Z
```

Then require the check `PR title` in the repository's ruleset, next to
`CI passed`, once it has reported on a pull request.

Dependabot doesn't update `workflow-templates/` in this repository, so the
template's pin may be older than the latest release: in the repository that
adds the workflow, Dependabot bumps it like any other pin.

## Inputs

- `title`: the title to check; by default, the pull request's title.
- `types`: the allowed types, separated by whitespace; by default `build
  chore ci docs feat fix perf refactor revert style test`.
- `max-length`: the maximum length of the whole title, in characters; by
  default `50`.

## Tests

`tests/pr-title/test.sh` runs the script on good and bad titles; the `test`
job of this repository's CI also runs it, and the action itself on a good
and a bad title.
