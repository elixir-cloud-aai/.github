# .github

Organisation-wide defaults for [ELIXIR Cloud & AAI](https://github.com/elixir-cloud-aai).

GitHub uses the community health files in this repository for every
repository of the organisation that doesn't have its own version:

- code of conduct
- contributing guidelines
- security policy
- issue templates
- pull request template

A repository can override any of them by adding a file of the same name.
Prefer changing the defaults here over adding repository-specific copies, so
that all repositories follow the same rules.

See GitHub's documentation on
[default community health files](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/creating-a-default-community-health-file).

The repository also holds composite actions, in `actions/<name>/`, that the
other repositories share and pin by commit. [RELEASING.md](RELEASING.md)
describes how they are versioned and released.

- [`gate`](actions/gate/README.md): checks the results of the jobs a CI
  gate needs.
- [`pr-title`](actions/pr-title/README.md): checks pull request titles.
- [`scan-image`](actions/scan-image/README.md): scans Docker images with
  Trivy.

## Development

CI (`.github/workflows/ci.yml`) runs the [pre-commit](https://pre-commit.com)
hooks of `.pre-commit-config.yaml`: YAML syntax and GitHub's schemas (issue
forms, workflows, actions, Dependabot), Markdown style (markdownlint),
secrets (gitleaks), shell scripts (shellcheck) and the workflows
(actionlint). Its `test` job runs the tests of the composite actions
(`tests/<action>/test.sh`) and the actions themselves. Run them locally
before you push:

```sh
pre-commit install
pre-commit run --all-files
# The whole checkout, as in CI (also untracked and ignored files)
pre-commit run --all-files --hook-stage manual gitleaks-all
bash tests/pr-title/test.sh
```
