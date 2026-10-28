# Contributing

Thanks for your interest in the projects of
[ELIXIR Cloud & AAI](https://github.com/elixir-cloud-aai)! Bug reports,
feature requests, discussions, documentation and code are all welcome. This
guide applies to every repository that has no contributing guide of its own;
the [contributor guide of ELIXIR
On-Cloud](https://elixir-cloud-aai.github.io/contribute/) describes how to
join the community.

- Follow our
  [code of conduct](https://github.com/elixir-cloud-aai/.github/blob/main/CODE_OF_CONDUCT.md).
- Report vulnerabilities privately, as described in the
  [security policy](https://github.com/elixir-cloud-aai/.github/blob/main/SECURITY.md),
  never in public issues.

## Issues first

- Before you change code, open or find an issue and agree on the approach
  with the maintainers, so that no work is in vain.
- Write issues concisely, with enough context (links, logs, screenshots) for
  others to start working on them; bug reports need steps to reproduce.
- Keep issues small enough to be resolved by one focused pull request; split
  larger ones into several issues.

## Pull requests

- Work on a feature branch, named after the type and topic of the change,
  e.g., `fix/<topic>` or `docs/<topic>`; if you are not a member of the
  organisation, on a branch of your fork.
- Branch from an up-to-date `dev`, the development branch, and open the pull
  request against `dev`, as a draft until it is ready for review. Where `dev`
  exists, `main` only holds releases; in repositories without `dev`, use the
  default branch instead.
- Each pull request resolves one issue, and resolves it completely: put
  `Closes #<issue>` in the description, and say what changes, why, and how
  you verified it. If GitHub doesn't close the issue on the merge, the
  maintainers do.
- Add or update tests with every change, and update the documentation.
- CI must pass.
- When you mark the pull request as ready for review, automated reviewers
  (Sourcery, GitHub Copilot) review it, and a maintainer reviews external
  contributions. Address every comment, by a change or by a reply that says
  why you disagree.
- Once the checks pass and all conversations are resolved, the maintainers
  squash-merge the pull request.

## Commit messages and pull request titles

Commit messages and pull request titles follow the
[Conventional Commits](https://www.conventionalcommits.org/) specification;
the maintainers use the title of a pull request as the commit message of its
squash merge:

```text
<type>[(<scope>)][!]: <description>
```

- The subject line has at most 50 characters.
- The description starts with a lowercase verb in the imperative mood
  (e.g., `add`, `fix`) and has no trailing period.
- `!` (and a `BREAKING CHANGE:` footer in the body) marks breaking changes.
- The type is one of `feat`, `fix`, `perf`, `refactor`, `style`, `build`,
  `ci`, `docs`, `test`, `chore` and `revert`.
- Where a repository has the `PR title` check, it enforces these rules for
  pull request titles.

## Repository specifics

Repositories add their own details, such as the development setup, the
checks to run locally, language guidelines and the release process, in their
contributing docs (e.g.,
[FOCA](https://foca.readthedocs.io/en/latest/contributing/) and
[Cloud Registry](https://cloud-registry.readthedocs.io/en/latest/contributing/)).
Where they differ from this guide, the repository's docs apply.
