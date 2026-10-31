#!/usr/bin/env bash
# Tests of `.github/scripts/release.sh`: builds a scratch repository with
# commits and tags, checks release tags, drafts and checks release notes
# and renders release bodies (with a fake
# `gh` for the GitHub API). Run from the repository root:
# `bash tests/release/test.sh`
set -euo pipefail

script="${PWD}/.github/scripts/release.sh"
failures=0
work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT

export GIT_AUTHOR_NAME=test GIT_AUTHOR_EMAIL=test@example.org
export GIT_COMMITTER_NAME=test GIT_COMMITTER_EMAIL=test@example.org
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
# The scratch repository has no remote
export RELEASE_BRANCH=main

repo="${work}/repo"
git init -q -b main "${repo}"
cd "${repo}"

# commit <file> <message>: changes <file> and commits it
commit() {
  mkdir -p "$(dirname "$1")"
  echo "${RANDOM}" >> "$1"
  git add "$1"
  git commit -q -m "$2"
  git rev-parse HEAD
}

# expect_check <tag> <commit> <expected output, or "error">
expect_check() {
  local got
  got="$(bash "${script}" check "$1" "$2" 2> /dev/null)" || got="error"
  if [[ "${got}" != "$3" ]]; then
    echo "NOT OK: check $1 $2: expected ${3@Q}, got ${got@Q}"
    failures=$((failures + 1))
  else
    echo "ok: check $1: ${3}"
  fi
}

# expect_in <name> <expected substring> <text>: <text> contains the
# substring
expect_in() {
  if [[ "$3" != *"$2"* ]]; then
    echo "NOT OK: $1: expected ${2@Q} in:"
    echo "$3"
    failures=$((failures + 1))
  else
    echo "ok: $1"
  fi
}

# expect_not_in <name> <substring> <text>: <text> doesn't contain it
expect_not_in() {
  if [[ "$3" == *"$2"* ]]; then
    echo "NOT OK: $1: unexpected ${2@Q} in:"
    echo "$3"
    failures=$((failures + 1))
  else
    echo "ok: $1"
  fi
}

# The cases build on each other: each adds commits and tags to the same
# history, so add new cases at the end of their section

# The first release is v1.0.0, whatever the commits
commit README.md "docs: add README" > /dev/null
commit .github/workflows/ci.yml "ci: set up CI (#2)" > /dev/null
# An action's README alone doesn't count as a change of the actions
readme="$(commit actions/gate/README.md "docs: describe the gate (#3)")"
expect_check v1.0.0 "${readme}" "previous="
first="$(commit actions/gate/check.sh "ci: add the gate action (#5)")"
expect_check v1.0.0 "${first}" "previous="
expect_check v0.1.0 "${first}" "error"
expect_check v1.0.1 "${first}" "error"
git tag v1.0.0 "${first}"
# The tag of the commit itself doesn't count as the previous release (a
# re-run of the workflow)
expect_check v1.0.0 "${first}" "previous="

# Patch, minor and major steps; at least the step that the commits need
fix="$(commit actions/gate/check.sh "fix(gate): handle null (#7)")"
expect_check v1.0.1 "${fix}" "previous=v1.0.0"
expect_check v1.1.0 "${fix}" "previous=v1.0.0"
expect_check v2.0.0 "${fix}" "previous=v1.0.0"
expect_check v1.0.2 "${fix}" "error"
expect_check v1.2.0 "${fix}" "error"
expect_check v3.0.0 "${fix}" "error"
feat="$(commit actions/pr-title/action.yml "feat: add the pr-title action (#9)")"
expect_check v1.0.1 "${feat}" "error"
expect_check v1.1.0 "${feat}" "previous=v1.0.0"
# Commits outside the actions don't count for the step
outside="$(commit tests/x.sh "feat!: change the tests (#10)")"
expect_check v1.1.0 "${outside}" "previous=v1.0.0"
git tag v1.1.0 "${outside}"
bang="$(commit actions/gate/action.yml "refactor(gate)!: rename an input (#12)")"
expect_check v1.1.1 "${bang}" "error"
expect_check v1.2.0 "${bang}" "error"
expect_check v2.0.0 "${bang}" "previous=v1.1.0"
footer="$(commit actions/gate/check.sh "$(printf 'fix: tighten the gate (#14)\n\nBREAKING CHANGE: skips fail')")"
expect_check v1.2.0 "${footer}" "error"
expect_check v2.0.0 "${footer}" "previous=v1.1.0"
# `feat` in a word or a body doesn't count; a `BREAKING CHANGE` mention
# that isn't a footer line doesn't either
featish="$(commit actions/gate/check.sh "$(printf 'chore: feature flags (#15)\n\nfeat: no\nnot a BREAKING CHANGE: no')")"
git tag v2.0.0 "${footer}"
expect_check v2.0.1 "${featish}" "previous=v2.0.0"

# Tags other than vX.Y.Z don't count, neither as previous release nor as
# the tag to check
git tag v9 "${featish}"
git tag v10.0.0-rc1 "${featish}"
# The dots are literal; no leading zeros
git tag v3x0x0 "${featish}"
git tag v2.08.0 "${featish}"
expect_check v2.0.1 "${featish}" "previous=v2.0.0"
for bad in v2.0 v2.0.1-rc1 2.0.1 v02.0.1 v2.0.01 v2x0x1; do
  expect_check "${bad}" "${featish}" "error"
done
# Only release tags on ancestors count: a stray tag elsewhere (e.g. on a
# side branch) doesn't count as the previous release
git switch -q -c side "${first}"
side="$(commit actions/gate/check.sh "fix: on a side branch (#16)")"
git tag v9.9.9 "${side}"
git switch -q main
expect_check v2.0.1 "${featish}" "previous=v2.0.0"
expect_check v2.0.1 "not-a-commit" "error"
expect_check v2.0.1 "" "error"
# No change to the actions since the last release: allowed, with a warning
git tag v2.0.1 "${featish}"
git switch -q -c docs-only "${featish}"
nothing="$(commit README.md "docs: polish the README (#22)")"
git switch -q main
expect_check v2.0.2 "${nothing}" "previous=v2.0.1"
expect_in "warning without changes to the actions" "No commit since v2.0.1 changed the actions" \
  "$(bash "${script}" check v2.0.2 "${nothing}" 2>&1 > /dev/null)"
# A commit that is released already can't be released again
expect_check v2.0.2 "${featish}" "error"
git tag -d v2.0.1 > /dev/null
# No release from a commit before the latest release (v2.0.0)
expect_check v1.1.1 "${feat}" "error"
expect_check v3.0.0 "${bang}" "error"
if bash "${script}" check v2.0.1 > /dev/null 2>&1; then
  echo "NOT OK: check needs two arguments"
  failures=$((failures + 1))
else
  echo "ok: check needs two arguments"
fi

# Release notes, with a fake `gh` that answers like the GitHub API: PR 12
# closes issues 11 and 4 (and one in another repository), PR 7 closes issue
# 6, number 15 is no pull request, PR 99 fails; the others close none
mkdir "${work}/bin"
cat > "${work}/bin/gh" << 'EOF'
#!/usr/bin/env bash
issue() { printf '{"number": %s, "repository": {"nameWithOwner": "%s"}}' "$1" "$2"; }
pr() { printf '{"data": {"repository": {"pullRequest": {"closingIssuesReferences": {"nodes": [%s]}}}}}\n' "$1"; }
if [[ "$1 $2" == "api graphql" ]]; then
  case "$*" in
    *"number=12 "*) pr "$(issue 11 org/repo), $(issue 3 org/other), $(issue 4 org/repo)" ;;
    *"number=7 "*) pr "$(issue 6 org/repo)" ;;
    *"number=15 "*)
      echo '{"data": {"repository": {"pullRequest": null}}, "errors": [{"type": "NOT_FOUND"}]}'
      exit 1 ;;
    *"number=99 "*) echo '{"message": "Bad credentials"}'; exit 1 ;;
    *"number=98 "*) echo '{"data": null, "errors": [{"type": "RATE_LIMITED"}]}' ;;
    *) pr "" ;;
  esac
elif [[ "$2" == */releases/generate-notes ]]; then
  printf '%s\n' "## What's Changed" "* fix: a by @u in https://x/pull/7" "" \
    "## New Contributors" "* @u made their first contribution" "" \
    "**Full Changelog**: https://x/compare/v1.1.0...v2.0.0"
  echo "args: $*" >> "${GH_ARGS_LOG}"
else
  echo "unexpected gh call: $*" >&2
  exit 1
fi
EOF
chmod +x "${work}/bin/gh"
export GH_ARGS_LOG="${work}/gh-args"

# render <subcommand> <arguments>: runs `release.sh` with the fake `gh`
render() {
  : > "${GH_ARGS_LOG}"
  PATH="${work}/bin:${PATH}" GH_REPO=org/repo bash "${script}" "$@"
}

# render_notes <tag> <previous> <commit>: a draft of the curated notes
render_notes() {
  render draft "$@"
}

commit actions/gate/action.yml "build(deps): Bump actions/x from 1 to 2 (#17)" > /dev/null
commit actions/gate/action.yml "build(deps): Bump actions/y from 1 to 2" > /dev/null
commit actions/gate/check.sh "fix(security): quote job IDs (#18)" > /dev/null
commit actions/gate/README.md "docs(gate): explain skips (#19)" > /dev/null
# Breaking, but not for callers: changes no action
commit .github/workflows/ci.yml "ci!: require the new gate (#20)" > /dev/null
plain="$(commit actions/gate/check.sh "Merge something without a type")"
notes="$(render_notes v2.0.1 v2.0.0 "${plain}")" || notes="error"
expect_in "intro" "Release v2.0.1 of the shared actions of ELIXIR Cloud & AAI, with changes to \`gate\`. Callers pin" "${notes}"
expect_not_in "no breaking changes in a patch release" "reaking" "${notes}"
expect_in "fix with scope security" $'## Security\n\n- Quote job IDs (#18).' "${notes}"
expect_in "docs" $'## Documentation\n\n- Explain skips (#19).' "${notes}"
expect_in "maintenance (no PR for #15, deps last)" $'## Maintenance\n\n- Feature flags (#15).\n- Require the new gate (#20).\n- Merge something without a type.\n- Dependency updates (#17).' "${notes}"
expect_in "draft: title and TODO" $'# v2.0.1\n\nTODO: review this draft, then delete this line.\n\nRelease v2.0.1' "${notes}"
expect_not_in "draft: no generated notes" "## Commits" "${notes}"

# Breaking changes of the actions: section, intro; issues of the same
# repository, sorted, before the PR number
notes="$(render_notes v2.0.0 v1.1.0 "${footer}")" || notes="error"
expect_in "breaking intro" "It contains breaking changes" "${notes}"
expect_in "breaking section" $'## Breaking changes\n\n- Rename an input (#4, #11, #12).\n- Tighten the gate (#14).' "${notes}"

# A `!` outside the actions is no breaking change for callers
notes="$(render_notes v1.1.0 v1.0.0 "${outside}")" || notes="error"
expect_not_in "breaking outside the actions" "reaking" "${notes}"
expect_in "sections in order" $'## Features\n\n- Add the pr-title action (#9).\n- Change the tests (#10).\n\n## Fixes\n\n- Handle null (#6, #7).' "${notes}"
expect_in "two actions" "with changes to \`gate\` and \`pr-title\`." "${notes}"

# A breaking dependency update of an action is a breaking change; a
# dependency update without a PR number still gets a bullet
breaking_deps="$(commit actions/gate/action.yml "build(deps)!: Bump actions/z from 1 to 2 (#21)")"
notes="$(render_notes v3.0.0 v2.0.0 "${breaking_deps}")" || notes="error"
expect_in "breaking dependency update" $'## Breaking changes\n\n- Bump actions/z from 1 to 2 (#21).' "${notes}"
git switch -q -c deps-only "${featish}"
commit actions/gate/action.yml "build(deps): Bump actions/y from 1 to 2" > /dev/null
notes="$(render_notes v2.0.1 v2.0.0 HEAD)" || notes="error"
expect_in "dependency update without PR" $'## Maintenance\n\n- Feature flags (#15).\n- Dependency updates.' "${notes}"
git switch -q main

# The first release lists all actions
notes="$(render_notes v1.0.0 "" "${first}")" || notes="error"
expect_in "first intro" "The first release of the shared actions of ELIXIR Cloud & AAI: \`gate\`. Callers" "${notes}"
expect_in "first: maintenance" $'## Maintenance\n\n- Set up CI (#2).\n- Add the gate action (#5).' "${notes}"

# Failures: API errors of the issue lookup (failed call; errors in a
# successful response), no GH_REPO
for number in 99 98; do
  commit actions/gate/check.sh "fix: something (#${number})" > /dev/null
  if errors="$(render_notes v3.0.1 HEAD^ HEAD 2>&1 > /dev/null)"; then
    echo "NOT OK: notes should fail on an API error (#${number})"
    failures=$((failures + 1))
  else
    expect_in "notes fail on an API error (#${number})" \
      "Could not look up the issues closed by #${number}" "${errors}"
  fi
done
if GH_REPO="" bash "${script}" draft v1.0.0 "" "${first}" > /dev/null 2>&1; then
  echo "NOT OK: draft without GH_REPO should fail"
  failures=$((failures + 1))
else
  echo "ok: draft needs GH_REPO"
fi

# Curated notes: a draft passes the check
curated="${work}/v2.0.1.md"
render draft v2.0.1 v2.0.0 "${plain}" > "${curated}"
if bash "${script}" lint v2.0.1 "${curated}" 2> /dev/null; then
  echo "NOT OK: lint should fail on an unreviewed draft"
  failures=$((failures + 1))
fi
sed -i '/^TODO: review/,+1d' "${curated}"
if bash "${script}" lint v2.0.1 "${curated}"; then
  echo "ok: lint: a reviewed draft"
else
  echo "NOT OK: lint should pass a reviewed draft"
  failures=$((failures + 1))
fi

# expect_lint_error <name> <expected message> <tag> <notes>: `lint` fails
# on <notes> with the message
expect_lint_error() {
  local errors
  printf '%s\n' "$4" > "${work}/bad.md"
  if errors="$(bash "${script}" lint "$3" "${work}/bad.md" 2>&1)"; then
    echo "NOT OK: lint should fail: $1"
    failures=$((failures + 1))
  else
    expect_in "lint fails: $1" "$2" "${errors}"
  fi
}
if errors="$(bash "${script}" lint v2.0.1 "${work}/bad.md" 2>&1)"; then
  echo "NOT OK: lint should fail on a missing file"
  failures=$((failures + 1))
else
  expect_in "lint fails: missing file" "is missing" "${errors}"
fi
expect_lint_error "TODO" "contains TODO" v2.0.1 $'# v2.0.1\n\nTODO: intro'
expect_lint_error "wrong title" "must start with the title" v2.0.1 $'# v2.0.0\n\nIntro.'
expect_lint_error "no title" "must start with the title" v2.0.1 $'Intro.'
expect_lint_error "no intro" "intro paragraph must come before" v2.0.1 $'# v2.0.1\n\n## Fixes\n\n- A fix (#1).'
expect_lint_error "empty" "has no intro paragraph" v2.0.1 $'# v2.0.1\n'
expect_lint_error "unknown section" "unknown section '## Commits'" v2.0.1 $'# v2.0.1\n\nIntro.\n\n## Commits\n\n- x'
expect_lint_error "out of order" "out of order" v2.0.1 $'# v2.0.1\n\nIntro.\n\n## Fixes\n\n- x\n\n## Features\n\n- y'
expect_lint_error "empty section" "empty section before '## Maintenance'" v2.0.1 $'# v2.0.1\n\nIntro.\n\n## Fixes\n\n## Maintenance\n\n- x'
expect_lint_error "empty last section" "last section is empty" v2.0.1 $'# v2.0.1\n\nIntro.\n\n## Fixes\n'
printf '%s\n' '# v2.0.1' '' 'Intro.' '' '## Fixes' '' '- x:' '' '  ```sh' '  # a comment' '  ```' > "${work}/fenced.md"
if bash "${script}" lint v2.0.1 "${work}/fenced.md"; then
  echo "ok: lint: comments in code blocks"
else
  echo "NOT OK: lint should skip code blocks"
  failures=$((failures + 1))
fi
expect_lint_error "subheading" "only sections" v2.0.1 $'# v2.0.1\n\nIntro.\n\n### Details'

# The release body: the curated notes without their title, then the
# generated notes under `## Commits`
body="$(render notes v2.0.1 v2.0.0 "${plain}" "${curated}")" || body="error"
expect_in "body: intro first" "Release v2.0.1 of the shared actions" "$(head -n 1 <<< "${body}")"
expect_not_in "body: no title" $'# v2.0.1\n' "${body}"
expect_in "body: sections" $'## Security\n\n- Quote job IDs (#18).' "${body}"
expect_in "body: commits" $'.\n\n## Commits\n\n* fix: a by @u in https://x/pull/7\n\n## New Contributors\n* @u made their first contribution\n\n**Full Changelog**: https://x/compare/v1.1.0...v2.0.0' "${body}"
expect_not_in "body: no What's Changed" "What's Changed" "${body}"
expect_in "generated notes: tag, commit and previous tag" \
  "tag_name=v2.0.1 -f target_commitish=${plain} -f previous_tag_name=v2.0.0" \
  "$(cat "${GH_ARGS_LOG}")"
printf '# v1.0.0\n\nThe first release.\n' > "${work}/v1.0.0.md"
body="$(render notes v1.0.0 "" "${first}" "${work}/v1.0.0.md")" || body="error"
expect_in "first release: body" $'The first release.\n\n## Commits' "${body}"
expect_not_in "first release: no previous tag" "previous_tag_name" "$(cat "${GH_ARGS_LOG}")"
if render notes v2.0.1 v2.0.0 "${plain}" "${work}/bad.md" > /dev/null 2>&1; then
  echo "NOT OK: notes should fail on bad curated notes"
  failures=$((failures + 1))
else
  echo "ok: notes check the curated notes"
fi

if ((failures > 0)); then
  echo "${failures} test(s) failed"
  exit 1
fi
echo "All tests passed"
