# Gate

Checks the results of the jobs that a CI workflow's gate job needs, so that
the gate (`passed`, "CI passed") can be the only required check. It fails:

- when there are no results (empty `needs`);
- when a needed job failed or was cancelled;
- when a needed job was skipped and is not listed in `allow-skipped`.

It lists the offending jobs in the log and the step summary. It is a plain
script (bash and jq): no token, no third-party action.

## Usage

The gate job stays in the repository's `ci.yml`, so that the required check
keeps its name (a reusable workflow's check would be named
`CI passed / …`). Pin the commit and version of a
[release](https://github.com/elixir-cloud-aai/.github/releases) of this
repository; Dependabot (`github-actions` ecosystem) in the calling
repository bumps the pin to new releases (see
[RELEASING.md](../../RELEASING.md)):

```yaml
passed:
  name: CI passed
  runs-on: ubuntu-latest
  timeout-minutes: 5
  if: always()
  needs: [lint, test, push]
  permissions: {}
  steps:
    - name: Check results of all jobs
      uses: elixir-cloud-aai/.github/actions/gate@<commit SHA> # vX.Y.Z
      with:
        needs: ${{ toJSON(needs) }}
        # `push` is skipped on pull requests
        allow-skipped: ${{ github.event_name == 'pull_request' && 'push' || '' }}
```

## Inputs

- `needs` (required): the results of the needed jobs, as
  `${{ toJSON(needs) }}`.
- `allow-skipped`: the IDs of the jobs that may be skipped in this run,
  separated by whitespace; by default none. Compute it in the expression,
  e.g. from the event, so that a skip is allowed only where it is intended.

## Tests

`tests/gate/test.sh` runs the script on sets of job results (all success,
a failure, a cancel, allowed and unexpected skips, empty `needs`); the
`test` job of this repository's CI also runs it, and the action itself on
passing and failing results.
