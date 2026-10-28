#!/usr/bin/env bash
# Release steps of `.github/workflows/release.yml`; see RELEASING.md. Run
# from the root of a full clone (all commits and tags):
#
#   release.sh plan <commit>
#     Prints `tag=<vX.Y.Z>` and `previous=<last tag or empty>` if <commit>
#     needs a release, nothing otherwise. A release is needed if a commit
#     since the last release tag changed a file under `actions/` other than
#     Markdown; the bump follows the Conventional Commit messages of these
#     commits: `!` or a `BREAKING CHANGE:` footer gives a major, `feat` a
#     minor, anything else a patch release. The first release is v1.0.0.
#     Prints nothing if <commit> is already part of the last release.
#
#   release.sh notes <tag> <previous tag or ""> <commit>
#     Prints the release notes of <tag> in the organisation's format. Calls
#     `gh` for the issues that each pull request closes and for GitHub's
#     generated notes; needs GH_REPO (`<owner>/<repo>`) and a token.
set -euo pipefail

# The pathspec of the files that callers run: the actions, without docs
release_paths=(actions ':(exclude,glob)actions/**/*.md')

die() {
  echo "::error title=Release::$*" >&2
  exit 1
}

# The highest `vX.Y.Z` tag, or nothing. No early exit in the pipeline, so
# that `git tag` never gets SIGPIPE
last_tag() {
  git tag --list 'v*' --sort=-v:refname \
    | awk '/^v[0-9]+\.[0-9]+\.[0-9]+$/ && !found { print; found = 1 }'
}

# The range of commits from <previous tag> (exclusive) to <commit>
commit_range() {
  local previous="$1" commit="$2"
  if [[ -n "${previous}" ]]; then
    echo "${previous}..${commit}"
  else
    echo "${commit}"
  fi
}

# 3 for a breaking change, 2 for a feature, 1 for anything else
bump_level() {
  local message="$1" subject
  subject="${message%%$'\n'*}"
  if [[ "${subject}" =~ ^[A-Za-z]+(\([^\)]*\))?!: ]] \
    || grep -qE '^BREAKING[ -]CHANGE:' <<< "${message}"; then
    echo 3
  elif [[ "${subject}" =~ ^feat(\([^\)]*\))?: ]]; then
    echo 2
  else
    echo 1
  fi
}

plan() {
  local commit previous level=0 message major minor patch
  [[ $# -eq 1 ]] || die "Usage: release.sh plan <commit>"
  commit="$(git rev-parse --verify --quiet "$1^{commit}")" \
    || die "Not a commit: $1"
  previous="$(last_tag)"
  if [[ -n "${previous}" ]]; then
    # Already released, e.g. a run for an older push that waited in the
    # queue while a newer push was released
    if git merge-base --is-ancestor "${commit}" "${previous}"; then
      return 0
    fi
    git merge-base --is-ancestor "${previous}" "${commit}" \
      || die "The last release ${previous} is not an ancestor of ${commit}"
  fi
  while IFS= read -r -d '' message; do
    local this
    this="$(bump_level "${message}")"
    if ((this > level)); then
      level="${this}"
    fi
  done < <(git log -z --format=%B "$(commit_range "${previous}" "${commit}")" \
    -- "${release_paths[@]}")
  ((level > 0)) || return 0
  if [[ -z "${previous}" ]]; then
    echo "tag=v1.0.0"
  else
    IFS=. read -r major minor patch <<< "${previous#v}"
    case "${level}" in
      3) echo "tag=v$((major + 1)).0.0" ;;
      2) echo "tag=v${major}.$((minor + 1)).0" ;;
      *) echo "tag=v${major}.${minor}.$((patch + 1))" ;;
    esac
  fi
  echo "previous=${previous}"
}

# The numbers of the issues in this repository that pull request <number>
# closes, space-separated
closed_issues() {
  # shellcheck disable=SC2016  # GraphQL variables, not shell expansions
  gh api graphql -F number="$1" -F owner="${GH_REPO%%/*}" \
    -F name="${GH_REPO#*/}" -f query='
      query($owner: String!, $name: String!, $number: Int!) {
        repository(owner: $owner, name: $name) {
          pullRequest(number: $number) {
            closingIssuesReferences(first: 20) {
              nodes { number repository { nameWithOwner } }
            }
          }
        }
      }' --jq '[.data.repository.pullRequest.closingIssuesReferences.nodes[]
        | select(.repository.nameWithOwner == env.GH_REPO)
        | .number] | sort | map(tostring) | join(" ")'
}

# Drops leading and trailing blank lines
trim_blank_lines() {
  awk '{ lines[NR] = $0 }
    NF && !first { first = NR }
    NF { last = NR }
    END { for (i = first; first && i <= last; i++) print lines[i] }'
}

# Joins the arguments as `#1, #2`
refs() {
  local out="" n
  for n in "$@"; do
    out+="${out:+, }#${n}"
  done
  echo "${out}"
}

# Prints `- <items>` sections in the organisation's order
print_sections() {
  local -n _sections="$1"
  local heading
  for heading in "Breaking changes" Features Security Fixes Documentation \
    Maintenance; do
    if [[ -n "${_sections[${heading}]:-}" ]]; then
      printf '\n## %s\n\n%s' "${heading}" "${_sections[${heading}]}"
    fi
  done
}

notes() {
  local tag previous commit range sha message subject type scope desc
  local pr heading generated count_major=0 count_feat=0 count_fix=0
  local -A sections=()
  local -a deps=() changed=()
  [[ $# -eq 3 ]] || die "Usage: release.sh notes <tag> <previous> <commit>"
  tag="$1" previous="$2" commit="$3"
  [[ -n "${GH_REPO:-}" ]] || die "GH_REPO is not set"
  range="$(commit_range "${previous}" "${commit}")"

  while IFS= read -r sha; do
    message="$(git log -1 --format=%B "${sha}")"
    subject="${message%%$'\n'*}"
    pr="" type="" scope=""
    if [[ "${subject}" =~ \ \(#([0-9]+)\)$ ]]; then
      pr="${BASH_REMATCH[1]}"
      subject="${subject% (#*}"
    fi
    desc="${subject}"
    if [[ "${subject}" =~ ^([A-Za-z]+)(\(([^\)]*)\))?!?:\ +(.*)$ ]]; then
      type="${BASH_REMATCH[1],,}" scope="${BASH_REMATCH[3]}"
      desc="${BASH_REMATCH[4]}"
    fi
    local -a numbers=()
    if [[ -n "${pr}" ]]; then
      read -r -a numbers <<< "$(closed_issues "${pr}")"
      numbers+=("${pr}")
    fi
    if [[ "${type}" == build && "${scope}" == deps ]]; then
      deps+=("${numbers[@]}")
      continue
    fi
    case "$(bump_level "${message}"):${type}:${scope}" in
      3:*) heading="Breaking changes" count_major=$((count_major + 1)) ;;
      *:*:security) heading=Security ;;
      *:feat:*) heading=Features count_feat=$((count_feat + 1)) ;;
      *:fix:*) heading=Fixes count_fix=$((count_fix + 1)) ;;
      *:docs:*) heading=Documentation ;;
      *) heading=Maintenance ;;
    esac
    desc="${desc^}"
    if ((${#numbers[@]} > 0)); then
      desc+=" ($(refs "${numbers[@]}"))"
    fi
    sections[${heading}]+="- ${desc}."$'\n'
  done < <(git rev-list --reverse "${range}")
  if ((${#deps[@]} > 0)); then
    sections[Maintenance]+="- Dependency updates ($(refs "${deps[@]}"))."$'\n'
  fi

  # The actions whose files (other than docs) changed
  mapfile -t changed < <(git diff --name-only \
    "${previous:-$(git hash-object -t tree /dev/null)}" "${commit}" \
    -- "${release_paths[@]}" | awk -F/ '{ print $2 }' | sort -u)

  # Intro
  local names=""
  if ((${#changed[@]} > 0)); then
    # shellcheck disable=SC2016  # Markdown code spans, not expansions
    names="$(printf '`%s`, ' "${changed[@]}")"
    names="${names%, }"
  fi
  if [[ -z "${previous}" ]]; then
    printf 'The first release of the shared actions of ELIXIR Cloud & AAI'
    [[ -z "${names}" ]] || printf ': %s' "${names}"
  else
    printf 'Release %s of the shared actions of ELIXIR Cloud & AAI' "${tag}"
    [[ -z "${names}" ]] || printf ', with changes to %s' "${names}"
  fi
  # shellcheck disable=SC2016  # Markdown code spans, not expansions
  printf '. Callers pin `elixir-cloud-aai/.github/actions/<name>@<commit> # %s`; Dependabot proposes the update.' \
    "${tag}"
  if ((count_major > 0)); then
    printf ' It contains breaking changes: see below for what callers have to change.'
  fi
  printf '\n'

  print_sections sections

  # GitHub's generated notes: the list of pull requests (without its
  # heading) under `## Commits`, the `**Full Changelog**` line last
  local -a args=(-f tag_name="${tag}" -f target_commitish="${commit}")
  [[ -n "${previous}" ]] && args+=(-f previous_tag_name="${previous}")
  generated="$(gh api "repos/${GH_REPO}/releases/generate-notes" \
    "${args[@]}" --jq .body)"
  local commits changelog
  commits="$(grep -v -e "^## What's Changed" -e '^\*\*Full Changelog\*\*' \
    <<< "${generated}" | trim_blank_lines || true)"
  changelog="$(grep '^\*\*Full Changelog\*\*' <<< "${generated}" || true)"
  if [[ -n "${commits}" ]]; then
    printf '\n## Commits\n\n%s\n' "${commits}"
  fi
  if [[ -n "${changelog}" ]]; then
    printf '\n%s\n' "${changelog}"
  fi
}

case "${1:-}" in
  plan) shift; plan "$@" ;;
  notes) shift; notes "$@" ;;
  *) die "Usage: release.sh plan <commit> | notes <tag> <previous> <commit>" ;;
esac
