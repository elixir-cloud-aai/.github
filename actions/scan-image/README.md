# Scan image

Scans a Docker image for known vulnerabilities (and secrets) with
[Trivy](https://trivy.dev/):

- the findings that have a fix go to code scanning as SARIF (unless `upload`
  is `false`), so that the alerts show what can be acted on;
- if `report` is `true`, a full report, findings without a fix included, is
  uploaded as the workflow artifact `trivy-report-<category>` (JSON and
  table);
- if `fail-on-pip` is `true`, the step fails if the image contains pip (see
  [pip in images](#pip-in-images));
- then the step fails on critical and high findings that have a fix, and on
  critical and high secrets (unless `fail` is `false`).

Accepted findings are listed in `.trivyignore.yaml` in the caller's
workspace (the checked-out commit) and left out of all results; the file
must exist, and changes to it need review like code. Use the
action in jobs without registry credentials or signing permissions, and give
the job `security-events: write` to upload to code scanning.

## Usage

Pin the commit and version of a
[release](https://github.com/elixir-cloud-aai/.github/releases) of this
repository; Dependabot (`github-actions` ecosystem) in the calling
repository bumps the pin to new releases (see
[RELEASING.md](../../RELEASING.md)):

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

- `image` (required): the image to scan, local or a registry reference
  (preferably by digest, as each Trivy step resolves it again).
- `category` (required): the code scanning category of the results, one per
  image variant; also part of the report's artifact name, so use only
  letters, digits, `-`, `_` and `.`.
- `upload`: upload the fixable findings to code scanning; default `true`
  (set it to `false`, e.g., for pull requests from forks).
- `report`: upload the full report as a workflow artifact; default `false`.
- `fail`: fail on fixable critical and high findings; default `true`.
- `fail-on-pip`: fail if the image contains pip; default `false` (see
  [pip in images](#pip-in-images)).
- `trivy-version`: the version of the Trivy binary; default `v0.75.0`.
  Dependabot bumps the actions pinned inside this action, but not this
  version: update it by hand.

## pip in images

pip brings vendored packages that image scans flag, and app images don't
need it at runtime: install the packages with [uv](https://docs.astral.sh/uv/)
instead (as FOCA's image does since 0.20.0). To keep pip from coming back,
e.g., through a new base image or an install step, set `fail-on-pip` to
`true` once an image is free of it:

```yaml
- name: Scan image
  uses: elixir-cloud-aai/.github/actions/scan-image@<commit SHA> # vX.Y.Z
  with:
    image: my-app:ci
    category: trivy-my-app
    fail-on-pip: "true"
```

The check lists all packages of the image with Trivy (written to
`trivy-packages.json` in the workspace) and fails if pip is among them:

- as an installed Python package, i.e., a `pip-*.dist-info` anywhere in the
  image (site-packages of the system Python, of a virtual environment or of
  a user installation), or a conda package;
- as an OS package, e.g., `python3-pip` (Debian, Ubuntu, Fedora) or
  `py3-pip` (Alpine); the wheel-only `python3-pip-whl` that Debian's `venv`
  module needs doesn't count.

A `pip` executable without its package can't run, so the check doesn't look
for one on the `PATH`. Wheels of pip that aren't installed (e.g., the one
that `ensurepip` bundles) don't count either. The check fails before the
check of the findings, so a scan with pip shows only that failure; the
log and the step summary list the packages found.

The default is `false`, so that callers keep passing when they bump the pin
and turn the check on per image. The published images of the latest
releases that contain pip (checked on 2026-11-13) are those of
`cloud-registry` and `pubgrade-updater` (from `Pubgrade`); the images of
`foca`, `protes`, `trs-filer`, `pubgrade`, `pubgrade-sidecar`, `tesk-api`
and `tesk-core` (taskmaster and filer) contain none, so their scans can turn
the check on now.

## Tests

The `test` job of this repository's CI tests the pip check on Trivy reports
(`tests/scan-image/test.sh`), and scans a clean image (and checks the full
report and the package list, with `fail-on-pip`), an image with fixable
findings and an image with pip (and expects the step to fail in both
cases).
