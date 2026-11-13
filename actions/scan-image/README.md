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

pip brings vendored packages that image scans flag, and app images rarely
need it at runtime: install the packages with
[uv](https://docs.astral.sh/uv/) instead. To keep pip from coming back,
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

The check lists all packages of the image with Trivy and fails if pip is
among them:

- as a Python package, e.g., a `pip-*.dist-info` anywhere in the image
  (site-packages of the system Python, of a virtual environment or of a
  user installation), or as a conda package;
- as an OS package: `pip`, `py*-pip` or `python*-pip` (e.g., `python3-pip`
  on Debian and Ubuntu, `py3-pip` on Alpine, `py3.13-pip` on Wolfi,
  `python3.12-pip` on Fedora), also with the prefix `platform-` (RHEL 8);
  packages that only ship pip's wheel or bytecode, such as Debian's
  `python3-pip-whl` (which the `venv` module needs) or Alpine's
  `py3-pip-pyc`, don't count.

Not found: pip's zipapp (`pip.pyz`) and other copies of pip that aren't
installed as a package, e.g., the wheel that `ensurepip` bundles. The check
fails before the check of the findings, so a scan with pip shows only that
failure; the log and the step summary list the packages found. The package
list stays in the workspace as `trivy-packages.json` (it isn't uploaded;
the action removes the file at the start of the check, also when the check
is off). The check needs `jq` on the runner, as GitHub-hosted runners have.

The default is `false`, so that callers keep passing when they bump the pin
and can turn the check on one image at a time.

## Tests

The `test` job of this repository's CI tests the pip check on made-up
Trivy reports and on reports cut down from real scans
(`tests/scan-image/test.sh`, `tests/scan-image/fixtures/`), and scans a
clean image (and checks the full report and the package list, with
`fail-on-pip`), an image with fixable findings (and expects the step to
fail) and an image with pip (which passes by default and fails with
`fail-on-pip`).
