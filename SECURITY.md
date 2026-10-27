# Security policy

This policy applies to every repository of
[ELIXIR Cloud & AAI](https://github.com/elixir-cloud-aai) that has no
`SECURITY.md` of its own.

## Reporting a vulnerability

Please report vulnerabilities privately, **not** in public issues, pull
requests or discussions:

- through GitHub's private vulnerability reporting: open the Security tab of
  the affected repository and select "Report a vulnerability"
  (`https://github.com/elixir-cloud-aai/<repository>/security/advisories/new`),
  or
- by email to
  [cloud-service@elixir-europe.org](mailto:cloud-service@elixir-europe.org).

Please include, as far as you can:

- the affected repository and version (release or commit);
- the relevant configuration (without secrets);
- steps to reproduce, ideally a minimal example;
- the impact, i.e., what an attacker can achieve.

## Supported versions

Security fixes are made in the latest release of each repository: they are
developed on the development branch (usually `dev`) and released in a new
version. Older versions get fixes only for critical issues, at the
maintainers' discretion.

## What happens next

The maintainers acknowledge the report, assess it, and, if they confirm it,
develop a fix in private. They publish the fix with a GitHub security advisory
(with a CVE where appropriate), coordinating the timing with the reporter, and
credit reporters who wish to be credited. The projects are maintained on a
best-effort basis: there are no guaranteed response or fix times.

## Scope

This policy covers the code of the organisation's repositories and the
artifacts published from them (e.g., packages, container images and Helm
charts). Vulnerabilities in deployments run by third parties go to their
operators, and those in dependencies to their projects; tell us too if they
affect one of our projects.
