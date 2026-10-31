#!/usr/bin/env bash
# Release steps of `.github/workflows/release.yml`; see RELEASING.md. Run
# from the root of a full clone (all commits and tags):
#
#   release.sh check <tag> <commit>
#     Fails unless <tag> is the next release version for <commit>: a
#     `vX.Y.Z` that follows the last release (the highest other `vX.Y.Z`
#     tag on <commit> or its ancestors) by one major, minor or patch step,
#     at least the step that the commits since need which changed a file
#     under `actions/` other than Markdown (`!` or a `BREAKING CHANGE:`
#     footer: major; `feat`: minor). The first release is v1.0.0. Warns if
#     no such commit exists. Prints `previous=<last release or empty>`.
#
#   release.sh draft <tag> <previous release or ""> <commit>
#     Prints a draft of the curated notes `docs/releases/<tag>.md` in the
#     organisation's format, from the commits since <previous>. Calls `gh`
#     for the issues that each pull request closes; needs GH_REPO
#     (`<owner>/<repo>`) and a token.
#
#   release.sh lint <tag> <file>
#     Fails unless <file> holds finished curated notes of <tag>.
#
#   release.sh notes <tag> <previous release or ""> <commit> <file>
#     Prints the body of the GitHub release: the curated notes <file> and
#     GitHub's generated notes (needs GH_REPO and a token).
set -euo pipefail

# The pathspec of the files that callers run: the actions, without docs
release_paths=(actions ':(exclude,glob)actions/**/*.md')
# Release tags: SemVer `vX.Y.Z`, without leading zeros
tag_pattern='^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'

die() {
  echo "::error title=Release::$*" >&2
  exit 1
}

# The range of commits from <previous release> (exclusive) to <commit>
commit_range() {
  if [[ -n "$1" ]]; then
    echo "$1..$2"
  else
    echo "$2"
  fi
}

# Parses the commit message <message> into the variables `type` (lowercase;
# empty if the subject is no Conventional Commit), `scope`, `description`
# (without the pull request number), `pr` (the number in a trailing
# `(#<number>)`, as in squash merges, or empty) and `breaking` (1 for `!` or
# a `BREAKING CHANGE:` footer, else 0)
parse_message() {
  local message="$1" subject
  subject="${message%%$'\n'*}"
  type="" scope="" pr="" breaking=0
  if [[ "${subject}" =~ \ \(#([0-9]+)\)$ ]]; then
    pr="${BASH_REMATCH[1]}"
    subject="${subject% (#*}"
  fi
  description="${subject}"
  if [[ "${subject}" =~ ^([A-Za-z]+)(\(([^\)]*)\))?(!?):\ +(.*)$ ]]; then
    type="${BASH_REMATCH[1],,}" scope="${BASH_REMATCH[3]}"
    description="${BASH_REMATCH[5]}"
    [[ -z "${BASH_REMATCH[4]}" ]] || breaking=1
  fi
  if grep -qE '^BREAKING[ -]CHANGE:' <<< "${message}"; then
    breaking=1
  fi
}

# The highest release tag on <commit> or its ancestors other than <tag>,
# or nothing
previous_release() {
  git tag --merged "$1" --list 'v*' --sort=-v:refname \
    | TAG_PATTERN="${tag_pattern}" TAG="$2" awk '$0 ~ ENVIRON["TAG_PATTERN"] && $0 != ENVIRON["TAG"] && !found { print; found = 1 }'
}

# The bump that the commits in <range> that changed the actions need: 3
# (major), 2 (minor), 1 (patch) or 0 (no change to the actions)
required_level() {
  local level=0 message type scope description pr breaking
  while IFS= read -r -d '' message; do
    parse_message "${message}"
    if ((breaking)); then
      level=3
    elif [[ "${type}" == feat ]] && ((level < 2)); then
      level=2
    elif ((level < 1)); then
      level=1
    fi
  done < <(git log -z --format=%B "$1" -- "${release_paths[@]}")
  echo "${level}"
}

check() {
  local tag commit previous level major minor patch
  local -a allowed=()
  [[ $# -eq 2 ]] || die "Usage: release.sh check <tag> <commit>"
  tag="$1"
  [[ "${tag}" =~ ${tag_pattern} ]] \
    || die "${tag} is no release version (vMAJOR.MINOR.PATCH, no leading zeros)"
  commit="$(git rev-parse --verify --quiet "$2^{commit}")" \
    || die "Not a commit: $2"
  previous="$(previous_release "${commit}" "${tag}")"
  level="$(required_level "$(commit_range "${previous}" "${commit}")")"
  if [[ -z "${previous}" ]]; then
    allowed=(v1.0.0)
  else
    IFS=. read -r major minor patch <<< "${previous#v}"
    allowed=("v$((10#${major} + 1)).0.0")
    ((level > 2)) || allowed+=("v${major}.$((10#${minor} + 1)).0")
    ((level > 1)) || allowed+=("v${major}.${minor}.$((10#${patch} + 1))")
  fi
  if [[ " ${allowed[*]} " != *" ${tag} "* ]]; then
    die "${tag} doesn't follow ${previous:-no release}: the commits since need one of ${allowed[*]} (see RELEASING.md)"
  fi
  if ((level == 0)); then
    echo "::warning title=Release::No commit since ${previous:-the start} changed the actions; callers get a Dependabot update without changes" >&2
  fi
  echo "previous=${previous}"
}

# The numbers of the issues in this repository that pull request <number>
# closes (at most 100), space-separated. Nothing if <number> is no pull request (e.g., an
# issue named in a commit pushed directly); fails on other API errors
closed_issues() {
  local response
  # shellcheck disable=SC2016  # GraphQL variables, not shell expansions
  if ! response="$(gh api graphql -F number="$1" -F owner="${GH_REPO%%/*}" \
    -F name="${GH_REPO#*/}" -f query='
      query($owner: String!, $name: String!, $number: Int!) {
        repository(owner: $owner, name: $name) {
          pullRequest(number: $number) {
            closingIssuesReferences(first: 100) {
              nodes { number repository { nameWithOwner } }
            }
          }
        }
      }')"; then
    if jq -e '.data.repository.pullRequest == null
        and any(.errors[]?; .type == "NOT_FOUND")' \
        > /dev/null 2>&1 <<< "${response}"; then
      return 0
    fi
    die "Could not look up the issues closed by #$1: ${response}"
  fi
  if ! jq -e '(.errors // []) == [] and .data.repository.pullRequest != null' \
      > /dev/null 2>&1 <<< "${response}"; then
    die "Could not look up the issues closed by #$1: ${response}"
  fi
  jq -r --arg repo "${GH_REPO}" '
    [.data.repository.pullRequest.closingIssuesReferences.nodes[]
      | select(.repository.nameWithOwner == $repo) | .number]
    | sort | map(tostring) | join(" ")' <<< "${response}"
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

# Joins the arguments as code spans: "`a`, `b` and `c`"
code_list() {
  local out="" i
  for ((i = 1; i <= $#; i++)); do
    if ((i > 1)); then
      if ((i == $#)); then out+=" and "; else out+=", "; fi
    fi
    out+="\`${!i}\`"
  done
  echo "${out}"
}

draft() {
  local tag previous commit range sha message heading issues
  local has_deps=0
  local type scope description pr breaking
  local -A sections=() relevant=()
  local -a deps=() changed=() numbers=()
  [[ $# -eq 3 ]] || die "Usage: release.sh draft <tag> <previous> <commit>"
  tag="$1" previous="$2" commit="$3"
  [[ -n "${GH_REPO:-}" ]] || die "GH_REPO is not set"
  range="$(commit_range "${previous}" "${commit}")"

  # Commits that changed the actions: only their breaking changes are
  # breaking for callers (as in `plan`)
  while IFS= read -r sha; do
    relevant[${sha}]=1
  done < <(git rev-list "${range}" -- "${release_paths[@]}")

  while IFS= read -r sha; do
    message="$(git log -1 --format=%B "${sha}")"
    parse_message "${message}"
    numbers=()
    if [[ -n "${pr}" ]]; then
      issues="$(closed_issues "${pr}")"
      read -r -a numbers <<< "${issues}"
      numbers+=("${pr}")
    fi
    if ((breaking)) && [[ -n "${relevant[${sha}]:-}" ]]; then
      heading="Breaking changes"
    elif [[ "${type}" == build && "${scope}" == deps ]]; then
      # Dependabot's updates share one bullet
      has_deps=1
      deps+=("${numbers[@]}")
      continue
    else
      case "${type}:${scope}" in
        *:security) heading=Security ;;
        feat:*) heading=Features ;;
        fix:*) heading=Fixes ;;
        docs:*) heading=Documentation ;;
        *) heading=Maintenance ;;
      esac
    fi
    description="${description^}"
    if ((${#numbers[@]} > 0)); then
      description+=" ($(refs "${numbers[@]}"))"
    fi
    sections[${heading}]+="- ${description}."$'\n'
  done < <(git rev-list --reverse "${range}")
  if ((${#deps[@]} > 0)); then
    sections[Maintenance]+="- Dependency updates ($(refs "${deps[@]}"))."$'\n'
  elif ((has_deps)); then
    sections[Maintenance]+="- Dependency updates."$'\n'
  fi

  # Intro: the actions whose files (other than docs) changed, and whether
  # the release is a major one
  printf '# %s\n\n' "${tag}"
  mapfile -t changed < <(git diff --name-only \
    "${previous:-$(git hash-object -t tree /dev/null)}" "${commit}" \
    -- "${release_paths[@]}" | awk -F/ '{ print $2 }' | sort -u)
  if [[ -z "${previous}" ]]; then
    printf 'The first release of the shared actions of ELIXIR Cloud & AAI'
    ((${#changed[@]} == 0)) || printf ': %s' "$(code_list "${changed[@]}")"
  else
    printf 'Release %s of the shared actions of ELIXIR Cloud & AAI' "${tag}"
    ((${#changed[@]} == 0)) \
      || printf ', with changes to %s' "$(code_list "${changed[@]}")"
  fi
  # shellcheck disable=SC2016  # Markdown code spans, not expansions
  printf '. Callers pin `elixir-cloud-aai/.github/actions/<name>@<commit> # %s`; Dependabot proposes the update.' \
    "${tag}"
  if [[ -n "${previous}" && "${tag%%.*}" != "${previous%%.*}" ]]; then
    printf ' It contains breaking changes: see below for what callers have to change.'
  fi
  printf '\n'

  for heading in "Breaking changes" Features Security Fixes Documentation \
    Maintenance; do
    if [[ -n "${sections[${heading}]:-}" ]]; then
      printf '\n## %s\n\n%s' "${heading}" "${sections[${heading}]}"
    fi
  done
}

# Checks the curated notes <file> of <tag>: a `# <tag>` title, an intro
# paragraph, then only the sections of the organisation's format, in order,
# and nothing unfinished (`TODO`)
lint() {
  local tag file line rank last=0 intro=0 title
  local -A ranks=(["Breaking changes"]=1 [Features]=2 [Security]=3
    [Fixes]=4 [Documentation]=5 [Maintenance]=6)
  [[ $# -eq 2 ]] || die "Usage: release.sh lint <tag> <file>"
  tag="$1" file="$2"
  [[ -f "${file}" ]] \
    || die "${file} is missing: add the release notes in a pull request first (see RELEASING.md)"
  ! grep -n TODO "${file}" >&2 \
    || die "${file} contains TODO: finish the notes, then tag a new release"
  title="$(head -n 1 "${file}")"
  [[ "${title}" == "# ${tag}" ]] \
    || die "${file} must start with the title '# ${tag}', not '${title}'"
  while IFS= read -r line; do
    if [[ "${line}" == "#"* ]]; then
      [[ "${line}" == "## "* ]] || die "${file}: only sections (##) after the title: ${line}"
      rank="${ranks[${line#\#\# }]:-}"
      [[ -n "${rank}" ]] \
        || die "${file}: unknown section '${line}' (sections: Breaking changes, Features, Security, Fixes, Documentation, Maintenance)"
      ((rank > last)) || die "${file}: section '${line}' is out of order"
      ((intro)) || die "${file}: the intro paragraph must come before the sections"
      last="${rank}"
    elif [[ -n "${line// /}" ]] && ((last == 0)); then
      intro=1
    fi
  done < <(tail -n +2 "${file}")
  ((intro)) || die "${file} has no intro paragraph"
}

# Prints the body of the GitHub release of <tag>: the curated notes <file>
# (checked by `lint`, without their title), then GitHub's generated notes
# since <previous release>: the list of pull requests (without its heading)
# under `## Commits`, the `**Full Changelog**` line last
notes() {
  local tag previous commit file generated commits changelog
  [[ $# -eq 4 ]] || die "Usage: release.sh notes <tag> <previous> <commit> <file>"
  tag="$1" previous="$2" commit="$3" file="$4"
  [[ -n "${GH_REPO:-}" ]] || die "GH_REPO is not set"
  lint "${tag}" "${file}"
  tail -n +2 "${file}" | trim_blank_lines
  local -a args=(-f tag_name="${tag}" -f target_commitish="${commit}")
  [[ -z "${previous}" ]] || args+=(-f previous_tag_name="${previous}")
  generated="$(gh api "repos/${GH_REPO}/releases/generate-notes" \
    "${args[@]}" --jq .body)"
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
  check) shift; check "$@" ;;
  draft) shift; draft "$@" ;;
  lint) shift; lint "$@" ;;
  notes) shift; notes "$@" ;;
  *) die "Usage: release.sh check <tag> <commit> | draft <tag> <previous> <commit> | lint <tag> <file> | notes <tag> <previous> <commit> <file>" ;;
esac
