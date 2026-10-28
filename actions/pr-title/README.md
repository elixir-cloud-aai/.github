# PR title

Checks that a pull request title follows the organisation's convention, as
the title becomes the commit message of the squash merge:

- the format `<type>[(<scope>)][!]: <description>`
  ([Conventional Commits](https://www.conventionalcommits.org/)), with one of
  the allowed types;
- at most 50 characters **in total**, scope included;
- a description that doesn't start with an uppercase letter;
- no trailing period or whitespace, and only one line.

The check reports every rule that failed, with the title's length. It is a
plain script: no token, no third-party action.

## Usage

Add `.github/workflows/pr-title.yml` to the repository, with the commit and
version of a release of this repository:

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
