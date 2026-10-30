[![ELIXIR On-Cloud][logo]][website]

Standards-based products and architecture patterns for federated analytics in
biomedical research, healthcare and beyond.

We are a [Driver Project][ga4gh-driver-projects] of the Global Alliance for
Genomics and Health (GA4GH), governed by the ELIXIR Compute Platform. We build
open, production-grade implementations of GA4GH APIs, and the framework and
patterns behind them, so that anyone can run them, anywhere. We are big
believers in Open Science: everything here is open source, developed in the
open and free to reuse. The nodes, funders and news are on our
[website][website].

## Key projects

- [**FOCA**][foca]: Python framework for building GA4GH API services from an
  OpenAPI specification, with auth, access control, plugins and a Helm
  library chart. ([docs][foca-docs])
- [**Cloud Registry**][cloud-registry]: a GA4GH Service Registry, so that
  clients can find your services in one place. ([docs][cloud-registry-docs])
- [**proTES**][protes]: a GA4GH Task Execution Service (TES) gateway that
  routes tasks across TES backends with pluggable middleware.
  ([docs][protes-docs])
- [**Cloud Components**][cloud-components]: web components for building
  frontends for GA4GH APIs. ([docs][cloud-components-docs])

## How we work

Our services are generic and easy to deploy on any infrastructure. We hold
them to the same best practices: typed, fully tested and documented code,
signed releases, automated security scans and CI that also runs for
contributors' forks. We write predominantly Python and TypeScript.

## Contribute

Contributions are welcome, from bug reports to code. Read our
[contributing guidelines][contributing] and the [code of
conduct][code-of-conduct], then open an issue or pull request in the
repository you're interested in. Report vulnerabilities as described in our
[security policy][security].

Contact: [cloud-service@elixir-europe.org](mailto:cloud-service@elixir-europe.org)

[cloud-components]: <https://github.com/elixir-cloud-aai/cloud-components>
[cloud-components-docs]: <https://cloud-components.2.rahtiapp.fi/>
[cloud-registry]: <https://github.com/elixir-cloud-aai/cloud-registry>
[cloud-registry-docs]: <https://cloud-registry.readthedocs.io/>
[code-of-conduct]: <https://github.com/elixir-cloud-aai/.github/blob/main/CODE_OF_CONDUCT.md>
[contributing]: <https://github.com/elixir-cloud-aai/.github/blob/main/CONTRIBUTING.md>
[foca]: <https://github.com/elixir-cloud-aai/foca>
[foca-docs]: <https://foca.readthedocs.io/>
[ga4gh-driver-projects]: <https://www.ga4gh.org/our-community/driver-projects/>
[logo]: logo_elixir_on_cloud.png
[protes]: <https://github.com/elixir-cloud-aai/proTES>
[protes-docs]: <https://protes.readthedocs.io/>
[security]: <https://github.com/elixir-cloud-aai/.github/blob/main/SECURITY.md>
[website]: <https://elixir-on.cloud/>
