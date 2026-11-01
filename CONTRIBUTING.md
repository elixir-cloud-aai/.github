# Contributing

Thanks for your interest in the projects of
[ELIXIR On-Cloud](https://elixir-on.cloud/)! Bug reports, feature requests,
discussions, documentation and code are all welcome. This guide applies to
every repository of the [organisation](https://github.com/elixir-cloud-aai).

- Follow our
  [code of conduct](https://github.com/elixir-cloud-aai/.github/blob/main/CODE_OF_CONDUCT.md).
- Report vulnerabilities privately, as described in the
  [security policy](https://github.com/elixir-cloud-aai/.github/blob/main/SECURITY.md),
  never in public issues.
- Ask questions in the [Q&A][q-a] category of our
  [discussion board][discussions], on [Slack][slack] or by email to
  [cloud-service@elixir-europe.org](mailto:cloud-service@elixir-europe.org).

## Getting started

1. Find an issue in the repository you are interested in, or open one (see
   [Issues first](#issues-first)).
2. Join our [Slack][slack] and introduce yourself in `#oss-community`: your
   skills and experience, your GitHub username and the issues you are
   interested in (or send a direct message to a project lead if you don't
   want to share these publicly).
3. Once the maintainers have added you to a team of the GitHub organisation,
   you can assign issues to yourself. Only ELIXIR members can join the team
   `members`; verified contributors who aren't ELIXIR members join the team
   `oss-contributors`.
4. Set up a development environment, as described in the repository's
   documentation (see [Repository specifics](#repository-specifics)), and
   start coding.

One-time contributors can skip steps 2 and 3 and open pull requests from
forks; some checks may need a maintainer's approval to run for them.

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
- Pull requests prepared with AI agents follow the same rules. They are
  opened as drafts, and a named person is responsible for them and answers
  review comments.

## Commit messages and pull request titles

Commit messages and pull request titles follow the
[Conventional Commits](https://www.conventionalcommits.org/) specification;
the maintainers use the title of a pull request as the commit message of its
squash merge:

```text
<type>[(<scope>)][!]: <description>
```

- The whole subject line has at most 50 characters.
- The description starts with a verb in the imperative mood (e.g., `add`,
  `fix`), but not with a capitalised word (acronyms such as `API` are fine),
  and has no trailing period.
- `!` (and a `BREAKING CHANGE:` footer in the body) marks breaking changes.
- The type names the predominant reason for the change:

| Type       | Changes                                             |
| ---------- | --------------------------------------------------- |
| `feat`     | new functionality                                   |
| `fix`      | bug fixes                                           |
| `perf`     | performance improvements                            |
| `refactor` | code changes that neither add features nor fix bugs |
| `style`    | formatting, docstrings and type hints of the code   |
| `build`    | build system, packaging and dependencies            |
| `ci`       | CI and release workflows                            |
| `docs`     | documentation                                       |
| `test`     | tests                                               |
| `chore`    | other maintenance, e.g., `.gitignore`               |
| `revert`   | reverts of earlier commits                          |

Use `feat`, `fix`, `perf`, `refactor` and `style` only for changes to what is
deployed or published: the app or library, its Helm chart or its packages.
Everything else uses `build`, `ci`, `docs`, `test` or `chore`. Where a
repository has the `PR title` check, it enforces these rules for pull request
titles.

## Citation metadata

In repositories with a `CITATION.cff` file
([Citation File Format](https://citation-file-format.github.io/)), the
authors are the people who committed at least 100 lines (lines added) to the
release branch, not counting bots and generated files. They are ordered by
lines, then by commits; equal contributors are listed alphabetically by
family name and marked with an asterisk (*). Affiliations come from public
ORCID records only. To add or correct your entry (e.g., your name,
[ORCID iD](https://orcid.org/) or affiliation), open a pull request that
changes only your entry; don't add e-mail addresses.

## Repository specifics

Repositories don't have their own `CONTRIBUTING.md`. Their development setup,
the checks to run locally, language guidelines, the release process and the
documentation build are described in their documentation, linked from the
"Contributing" section of their README.

[discussions]: <https://github.com/orgs/elixir-cloud-aai/discussions>
[q-a]: <https://github.com/orgs/elixir-cloud-aai/discussions/categories/q-a>
[slack]: <https://join.slack.com/t/elixir-cloud/shared_invite/zt-4f6zdhi84-X4YBkJHxhYmVIHJkRfY2JQ>
