# Security policy

This policy applies to every repository of
[ELIXIR On-Cloud](https://github.com/elixir-cloud-aai); repositories don't
have their own `SECURITY.md`.

## Reporting a vulnerability

Please report vulnerabilities privately, **not** in public issues, pull
requests or discussions:

- through GitHub's private vulnerability reporting: open the Security tab of
  the affected repository and select "Report a vulnerability"
  (`https://github.com/elixir-cloud-aai/<repository>/security/advisories/new`);
  if the Security tab has no such button, use email instead; or
- by email to
  [cloud-service@elixir-europe.org](mailto:cloud-service@elixir-europe.org).

Report a vulnerability to the repository of the component that has it (e.g.,
FOCA for the framework, not the app you found it in); if you are unsure,
report it where you found it, and the maintainers route it.

Please include, as far as you can:

- the affected repository and package(s), with their versions (release or
  commit);
- the versions of the components they run with (e.g., the FOCA version of an
  app) and the relevant configuration (without secrets);
- steps to reproduce, ideally a minimal example;
- the impact, i.e., what an attacker can achieve.

## Supported versions

Only the latest release of each repository is supported: security fixes are
released in a new version of its latest release series (the latest minor
version). In repositories that publish several packages, fixes are released
for each affected package, and for any package that pins it. Older versions
get fixes only for critical issues, at the maintainers' discretion.

## What happens next

The maintainers acknowledge the report, assess it, and, if they confirm it,
develop a fix in private. They publish the fix with a GitHub security advisory
(with a CVE where appropriate), coordinating the timing with the reporter, and
credit reporters who wish to be credited. The projects are maintained on a
best-effort basis: there are no guaranteed response or fix times.

## Scope

This policy covers the code of the organisation's repositories and the
artefacts published from them (e.g., packages, container images and Helm
charts). Vulnerabilities in deployments run by third parties go to their
operators, and those in dependencies to their projects; tell us too if they
affect one of our projects.
