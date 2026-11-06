# Governance

This document applies to every repository of
[ELIXIR On-Cloud](https://github.com/elixir-cloud-aai); repositories don't
have their own `GOVERNANCE.md`. It describes who decides what, how decisions
are made, how the community relates to ELIXIR and GA4GH, and how
contributors take on more responsibility. It names roles, not people.

## Scope and oversight

- ELIXIR On-Cloud builds and maintains open-source implementations of the
  GA4GH Cloud APIs, and the framework and patterns behind them.
- It is governed by the ELIXIR Compute Platform, one of the five Platforms of
  [ELIXIR](https://elixir-europe.org/) (Data, Tools, Interoperability,
  Compute, Training). Its work is funded through multi-year Work Packages
  (typically two to three years) with defined milestones and deliverables,
  which set the main priorities.
- ELIXIR On-Cloud (formerly known as "ELIXIR Cloud & AAI") is a
  [Driver Project][ga4gh-driver-projects] of [GA4GH](https://www.ga4gh.org/):
  it implements GA4GH standards and feeds implementation experience back into
  them.

## Roles

- **Contributors:** anyone who contributes issues, discussions, reviews,
  documentation or code, following the [code of conduct][code-of-conduct]
  and the [contributing guidelines][contributing].
- **Members** (team `members`): contributors who are ELIXIR members. Only
  ELIXIR members can join teams of the organisation other than
  `oss-contributors`.
- **Verified open-source contributors** (team `oss-contributors`): regular
  contributors who aren't ELIXIR members.
- **Maintainers:** per repository, the code owners (`CODEOWNERS`). They review
  and merge pull requests and decide technical choices in their repository,
  within the org policies. Every repository has at least one code owner and a
  backup code owner.
- **Leads** (team `leads`): set the org policies (community files,
  contributing rules, CI, releases, security), are responsible for releases
  and the response to vulnerabilities (see the [security policy][security]),
  and appoint maintainers.

## Decisions

- Day to day: through issues and pull requests with review, by lazy
  consensus: a proposal goes ahead unless someone objects.
- Within a repository: its maintainers decide.
- Across repositories, on org policies and on disputes: the leads decide,
  after a discussion on the [discussion board][discussions] or in an issue.
- Org policies apply to every repository of the organisation; they are not
  optional.

## Becoming a maintainer

Maintainers are contributors with sustained contributions and reviews in a
repository. A maintainer or lead nominates them, and the leads appoint them.
Maintainers who are inactive for a long time become emeritus; repositories
that keep a list of maintainers list them as such in their documentation or
README.

## Changes to this document

Propose changes by pull request to
[this repository](https://github.com/elixir-cloud-aai/.github), as described
in the [contributing guidelines][contributing].

[code-of-conduct]: <https://github.com/elixir-cloud-aai/.github/blob/main/CODE_OF_CONDUCT.md>
[contributing]: <https://github.com/elixir-cloud-aai/.github/blob/main/CONTRIBUTING.md>
[discussions]: <https://github.com/orgs/elixir-cloud-aai/discussions>
[ga4gh-driver-projects]: <https://www.ga4gh.org/our-community/driver-projects/>
[security]: <https://github.com/elixir-cloud-aai/.github/blob/main/SECURITY.md>
