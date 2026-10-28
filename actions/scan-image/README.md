# Scan image

Scans a Docker image for known vulnerabilities (and secrets) with
[Trivy](https://trivy.dev/):

- the findings that have a fix go to code scanning as SARIF (unless `upload`
  is `false`), so that the alerts show what can be acted on;
- if `report` is `true`, a full report, findings without a fix included, is
  uploaded as the workflow artifact `trivy-report-<category>` (JSON and
  table);
- then the step fails on critical and high findings that have a fix (unless
  `fail` is `false`).

Accepted findings are listed in `.trivyignore.yaml` in the caller's
workspace (the checked-out commit) and left out of all results. Use the
action in jobs without registry credentials or signing permissions, and give
the job `security-events: write` to upload to code scanning.

## Usage

With the commit and version of a release of this repository:

```yaml
permissions:
  contents: read
  security-events: write
steps:
  - name: Check out repository
    uses: actions/checkout@<commit SHA> # vX.Y.Z
    with:
      persist-credentials: false
  # ... build or pull the image ...
  - name: Scan image
    uses: elixir-cloud-aai/.github/actions/scan-image@<commit SHA> # vX.Y.Z
    with:
      image: my-app:ci
      category: trivy-my-app
```

## Inputs

- `image` (required): the image to scan, local or a registry reference.
- `category` (required): the code scanning category of the results, one per
  image variant.
- `upload`: upload the fixable findings to code scanning; default `true`
  (set it to `false`, e.g., for pull requests from forks).
- `report`: upload the full report as a workflow artifact; default `false`.
- `fail`: fail on fixable critical and high findings; default `true`.
- `trivy-version`: the version of the Trivy binary; default `v0.75.0`.
  Dependabot bumps the actions pinned inside this action, but not this
  version: update it by hand.

## Tests

The `test` job of this repository's CI scans a clean image (and checks the
full report) and an image with fixable findings (and expects the step to
fail).
