<!-- markdownlint-disable MD033 MD041 -- logo first; <picture> for dark mode -->
<a href="https://elixir-on.cloud/">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="profile/logo_elixir_on_cloud_night.png">
    <img src="profile/logo_elixir_on_cloud.png" alt="ELIXIR On-Cloud">
  </picture>
</a>
<!-- markdownlint-enable MD033 MD041 -->

# Community health files and shared actions

[![License][badge-license]][badge-url-license]
[![Build_status][badge-build-status]][badge-url-build-status]

Organisation-wide defaults and shared CI building blocks for the repositories
of [ELIXIR On-Cloud](https://elixir-on.cloud/): the community health files
that GitHub uses for every repository without its own version, the
organisation's profile page, composite actions and workflow templates.

## Community health files

GitHub uses these files for every repository of the organisation that doesn't
have its own version (see GitHub's documentation on [default community health
files][gh-health-files]):

- [code of conduct](CODE_OF_CONDUCT.md);
- [contributing guidelines](CONTRIBUTING.md);
- [security policy](SECURITY.md);
- [issue templates](.github/ISSUE_TEMPLATE/);
- [pull request template](.github/pull_request_template.md).

A repository can override any of them by adding a file of the same name.
Prefer changing the defaults here over adding repository-specific copies, so
that all repositories follow the same rules.

[`profile/README.md`](profile/README.md) is the organisation's home page on
GitHub.

## Shared actions

Composite actions, in `actions/<name>/`, that the other repositories share
and pin to the commit of a release:

- [`gate`](actions/gate/README.md): checks the results of the jobs a CI gate
  needs.
- [`pr-title`](actions/pr-title/README.md): checks pull request titles.
- [`scan-image`](actions/scan-image/README.md): scans Docker images with
  Trivy.

[`workflow-templates/`](workflow-templates/) offers the `PR title` workflow as
a template for new workflows in the organisation's repositories.

The maintainer releases the actions from signed version tags;
[`RELEASING.md`](RELEASING.md) describes how they are versioned and released.

## Development

CI (`.github/workflows/ci.yml`) runs the [pre-commit](https://pre-commit.com)
hooks of `.pre-commit-config.yaml`: YAML syntax and GitHub's schemas (issue
forms, workflows, actions, Dependabot), Markdown style (markdownlint),
secrets (gitleaks), shell scripts (shellcheck) and the workflows
(actionlint). Its `test` job runs the tests of the composite actions
(`tests/<action>/test.sh`), the actions themselves and the tests of the
release scripts (`tests/release/test.sh`). Run them locally before you push:

```sh
pre-commit install
pre-commit run --all-files
# The whole checkout, as in CI (also untracked and ignored files)
pre-commit run --all-files --hook-stage manual gitleaks-all
bash tests/pr-title/test.sh
bash tests/gate/test.sh
bash tests/release/test.sh
```

## Contributing

Contributions are welcome! See the [contributing guidelines](CONTRIBUTING.md)
and mind our [code of conduct](CODE_OF_CONDUCT.md). Report vulnerabilities as
described in our [security policy](SECURITY.md).

[badge-build-status]: <https://github.com/elixir-cloud-aai/.github/actions/workflows/ci.yml/badge.svg>
[badge-license]: <https://img.shields.io/badge/license-Apache%202.0-blue.svg>
[badge-url-build-status]: <https://github.com/elixir-cloud-aai/.github/actions/workflows/ci.yml>
[badge-url-license]: <https://www.apache.org/licenses/LICENSE-2.0>
[gh-health-files]: <https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/creating-a-default-community-health-file>
