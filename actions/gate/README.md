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

Let only a new head commit of a pull request cancel its runs in progress
(see [Cancelled runs](#cancelled-runs)), as in this repository's
`ci.yml`:

```yaml
concurrency:
  # Runs for pushes get their own group, so that none is dropped
  group: >-
    ${{ github.workflow }}-${{ github.event_name == 'push'
    && github.sha || github.ref }}
  cancel-in-progress: >-
    ${{ github.event_name == 'pull_request'
    && github.event.action == 'synchronize' }}
```

## Inputs

- `needs` (required): the results of the needed jobs, as
  `${{ toJSON(needs) }}`.
- `allow-skipped`: the IDs of the jobs that may be skipped in this run,
  separated by whitespace; by default none. Compute it in the expression,
  e.g. from the event, so that a skip is allowed only where it is intended.

## Cancelled runs

The gate job runs `always()`, so that it fails whenever a needed job failed
or was cancelled, whether by its `timeout-minutes`, by `fail-fast` in a
matrix, by hand or with the whole run. A cancelled run thus leaves a failed
`CI passed` on its commit, and as the newest result of a check on a commit
counts, that failure blocks the merge until a newer run on the same commit
passes.

That is harmless when the cancelled run was testing an old commit, but it
blocks a pull request when a newer run on the **same** commit cancels it,
e.g. a run for editing the description, marking the pull request ready or
reopening it (event `pull_request`, actions `edited`, `ready_for_review`,
`reopened`): the cancelled run's failed gate is then the newest result on
the commit until the newer run's gate reports, and stays so if it never
does. Therefore only a new head commit (action
`synchronize`) may cancel the runs of a pull request in progress
(`cancel-in-progress` above); a run for another action waits until the run
in progress has finished, and replaces a waiting one. A waiting run that is
replaced never starts any job, so it leaves no `CI passed` at all.

The gate job doesn't use `if: ${{ !cancelled() }}`, which would skip it in
cancelled runs: GitHub counts a skipped required check as passed
([Troubleshooting required status
checks](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks#handling-skipped-but-required-checks)),
so a run cancelled by hand, or replaced by a newer run that hasn't reported
yet, would allow the merge without tests.

A run cancelled by hand, or by rerunning a run of an older commit (a rerun
keeps its event, so it cancels the run in progress on the head commit),
fails the gate: rerun the head commit's run, or push, before you merge.

The price: after an event other than a push, e.g. marking a pull request
ready, its result comes only after the run in progress and then a whole new
run. Trigger CI only on the `pull_request` actions that it needs (`types`).

## Tests

`tests/gate/test.sh`:

- runs the script on sets of job results (all success, a failure, a
  cancel, allowed and unexpected skips, empty `needs`);
- checks that the gate jobs of this repository's CI and of the example
  above run `always()`, and that only a new head commit of a pull request
  cancels runs in progress.

The `test` job of this repository's CI runs it, and the action itself on
passing and failing results. How GitHub applies the conditions and the
concurrency group shows only in real runs.
