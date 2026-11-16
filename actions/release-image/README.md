# Release image

Releases an image that the release workflow pushed by digest (untagged)
and scanned, in the job that publishes it. For the image and the digest,
in this order:

1. **checks** the image name (fully qualified, without tag or digest), the
   **digest** (`sha256:` and 64 hex digits), the tag (a release version
   after `tag-prefix`, as [check-release](../check-release/README.md)
   accepts it), and that the digest exists in the image's repository;
2. fails if the version's image tag (`X.Y.Z`) already points to **another
   digest**: published versions never move (e.g., after "Re-run all jobs",
   which builds a new digest). A re-run with the same digest passes;
3. **attests** the build provenance of the digest
   (`actions/attest-build-provenance`, pushed to the registry);
4. **signs** the digest with cosign (keyless, with the workflow's OIDC
   identity); the signature covers every tag of the digest;
5. checks the version's image tag again (another run may have set it in
   the meantime), then **tags** the digest `X.Y.Z`, decides whether it is
   the highest stable release, and if so tags it `latest` (see
   [Latest](#latest)); tags copy the digest as is (no new index around a
   single manifest), and each is checked to point to the digest.

The first step fails before anything is attested, signed or tagged.

## Latest

The image gets `latest` by the rule that
[publish-release](../publish-release/README.md) uses for the GitHub
release's "Latest" flag, with the same code (`is_latest` in
`publish.py`): if no published release (drafts don't count) has a higher
stable version than this one, and this one is stable. Stable versions have
no pre-release (`a`, `alpha`, `b`, `beta`, `rc`), so pre-releases never
become `latest`, and a patch of an older line (e.g., `1.2.1` after `1.3.0`)
doesn't move it back. From 1.0.0, a release counts as a pre-release by
GitHub's flag, as for publish-release. The decision is made after `X.Y.Z`
is tagged, from the releases as they are then, so that a re-run of an older
release doesn't move it back either.

From 1.0.0, the image's `latest` and the GitHub release marked "Latest"
are therefore the same release. Below 1.0.0, publish-release makes every
GitHub release a pre-release, which GitHub never marks "Latest"; the image
still gets `latest` for the highest stable version (e.g., `0.22.0`), as the
release workflows of the organisation did before, so that `latest` isn't
stuck before 1.0.0.

The GitHub release of a version is published after its image (in the
`publish` job), so a higher version can be in between: tagged in the
registry, but not released yet. A higher stable version tag of the
repository whose image tag exists counts as released, so that a release of
a lower version that runs in between doesn't take `latest` from it; a
higher tag without an image (e.g., a release that failed before tagging)
doesn't count. Two releases of one image that decide `latest` at the same
time can still both set it, the lower one last: registries have no atomic
"set if unchanged", so release jobs of one image run one at a time (see the
concurrency group in [Usage](#usage)).

With `tag-prefix`, only releases and tags that are the prefix followed
by a version as publish-release reads it count (e.g., `1.2.0` or `2.0`,
not `v1.2.0`; with `tag-prefix: chart-v`, a release `v9.0.0` doesn't keep `chart-v1.2.0`
from `latest`, but `chart-v1.3.0` does). With `latest: false`, the image
never gets `latest` (e.g., for images that operators set by digest, or one
repository with images of several packages), and the GitHub API isn't
read.

## Usage

Pin the commit and version of a
[release](https://github.com/elixir-cloud-aai/.github/releases) of this
repository; Dependabot (`github-actions` ecosystem) in the calling
repository bumps the pin to new releases (see
[RELEASING.md](../../RELEASING.md)). The action runs on GitHub-hosted Linux
runners (it needs Python 3.10 or later as `python3`, `gh`, and Docker with
Buildx for `docker buildx imagetools`) and needs no checkout. The caller
logs in to the registry, and the job needs `contents: read` (the releases
and tags, for `latest`), `id-token: write` (the signing certificate) and
`attestations: write`:

```yaml
env:
  # Fully qualified (`docker.io/`), as the attestation needs it
  IMAGE_NAME: docker.io/${{ vars.DOCKERHUB_ORG || 'elixircloud' }}/my-app

jobs:
  # prepare (check-release), push (by digest), scan (scan-image) ...

  release-image:
    name: Release image
    needs: [prepare, push, scan]
    runs-on: ubuntu-latest
    environment: release
    # One release at a time, so that `latest` is decided and set by one run
    # before the next one decides it
    concurrency:
      group: ${{ github.workflow }}-release-image
      cancel-in-progress: false
    permissions:
      contents: read
      id-token: write # Sigstore signing certificates
      attestations: write # GitHub artifact attestations
    steps:
      - name: Log in to Docker Hub
        uses: docker/login-action@<commit SHA> # vX.Y.Z
        with:
          username: ${{ secrets.DOCKERHUB_LOGIN }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}
      - name: Release image
        uses: elixir-cloud-aai/.github/actions/release-image@<commit SHA> # vX.Y.Z
        with:
          image: ${{ env.IMAGE_NAME }}
          digest: ${{ needs.push.outputs.digest }}
```

The `push` job passes the digest of `docker/build-push-action` as a job
output (`digest: ${{ steps.push.outputs.digest }}`). Each release runs the
action once per image.

### Matrix jobs

Outputs of a matrix job can't tell its entries apart, so a `push` job with
a matrix of images hands each digest over as an artifact named after its
entry, and the release job, with the same matrix, reads it back. The
action checks the digest's format, so reading the file's first line is
all that is needed:

```yaml
  push:
    strategy:
      matrix:
        image: [taskmaster, filer]
    steps:
      # ... build and push by digest (step `push`) ...
      - name: Save image digest
        env:
          DIGEST: ${{ steps.push.outputs.digest }}
        run: echo "${DIGEST}" > "${RUNNER_TEMP}/digest.txt"
      - name: Upload image digest
        uses: actions/upload-artifact@<commit SHA> # vX.Y.Z
        with:
          name: digest-${{ matrix.image }}
          path: ${{ runner.temp }}/digest.txt
          # A re-run of all jobs pushes a new digest, which replaces the
          # artifact (and which the action then refuses)
          overwrite: true
          # Long enough for an approval of the `release` environment, or a
          # re-run of failed jobs, days later
          retention-days: 7

  release-image:
    needs: [prepare, push, scan]
    strategy:
      # A failing entry must not cancel another one between signing and
      # tagging
      fail-fast: false
      matrix:
        image: [taskmaster, filer]
    # ... environment, concurrency, permissions, login as above ...
    steps:
      - name: Download image digest
        uses: actions/download-artifact@<commit SHA> # vX.Y.Z
        with:
          name: digest-${{ matrix.image }}
          path: ${{ runner.temp }}
      - name: Read image digest
        id: digest
        # The first line only, so that the file can't set other outputs
        run: |
          read -r digest < "${RUNNER_TEMP}/digest.txt"
          echo "digest=${digest}" >> "${GITHUB_OUTPUT}"
      - name: Release image
        uses: elixir-cloud-aai/.github/actions/release-image@<commit SHA> # vX.Y.Z
        with:
          image: docker.io/elixircloud/${{ matrix.image }}
          digest: ${{ steps.digest.outputs.digest }}
```

In a matrix, the entries share a job-level concurrency group, and a group
holds one running and one pending job: put the entry's name in the group
(e.g., `${{ github.workflow }}-release-image-${{ matrix.image }}`), so that
releases of the same image run one at a time and the entries of one release
don't cancel each other. With or without a matrix, a third release that
queues for the group cancels the pending one: re-run the failed jobs of
the cancelled release (its digest is unchanged, so that is safe).
Independently of the group, the action checks the version's tag again right
before tagging.

Tags with a prefix set `tag-prefix` (e.g., foca-plugins:
`tag-prefix: foca-plugin-tes-data-crypt4gh-v` and `latest: "false"`); the
image tag is the version without the prefix.

## Inputs

- `image` (required): the fully qualified image name, without tag or
  digest, e.g., `docker.io/elixircloud/tesk-api` (a registry host with a
  `.` or a port, or `localhost`, then lower-case path components).
- `digest` (required): the digest to release, `sha256:` and 64 lower-case
  hex digits.
- `tag`: the Git tag of the release; default is the tag of the workflow
  run (`github.ref_name`).
- `tag-prefix`: the part of the tag before the version; default `v`. Empty
  for tags without a prefix (e.g., `1.2.0`).
- `latest`: `auto` (default) to tag `latest` for the highest stable release
  (see [Latest](#latest)), `false` never to.
- `token`: the token for the GitHub API, to read the releases and tags of
  the repository for `latest`; default is the job's `GITHUB_TOKEN`, which
  needs `contents: read`.

## Outputs

Set only if the image was released:

- `version`: the version, which is the image tag: the Git tag without
  `tag-prefix` (e.g., `1.2.0`).
- `latest`: `true` if the image was tagged `latest`, else `false`.
- `tags`: the image references that were tagged, space-separated (e.g.,
  `docker.io/elixircloud/tesk-api:1.2.0 docker.io/elixircloud/tesk-api:latest`).

## Tests

The action's script, [`release.py`](release.py), uses the Python standard
library, `gh` and `docker` only, and the version rules of check-release and
publish-release from their scripts (loaded from the actions next to it, so
that the rules can't drift apart). CI tests it on three levels:

- the script's unit tests in
  [`tests/release-image/`](../../tests/release-image/) (`unittest`, against
  stand-ins for `gh` and `docker`): settings, the version check, the
  `latest` rule (also against publish-release's `is_latest`) and the tags;
- the script against a local registry with two images and this
  repository's real releases: a new highest version (`latest`), a re-run,
  another digest of a published version, a lower version and
  `latest: false`, each with the tags it should leave;
- the action itself, once, with a version that points to another digest:
  it fails at its first step and leaves the tags as they were.

Attesting and signing aren't run in CI (they need `id-token: write`, and
would publish attestations and transparency log entries of test images);
the first release of a repository with the action, or a dry run in a fork,
covers them.
