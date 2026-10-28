#!/usr/bin/env bash
# Tests of `actions/pr-title/check.sh`: runs it on good and bad titles and
# compares the exit status, and for failures the reported rule, with the
# expected ones. Run from the repository root: `bash tests/pr-title/test.sh`
set -euo pipefail

check="actions/pr-title/check.sh"
default_types="build chore ci docs feat fix perf refactor revert style test"
failures=0

# expect <pass|fail> <title> [expected output] [max length] [types]
expect() {
  local want="$1" title="$2" message="${3-}" max="${4:-50}" types="${5-${default_types}}"
  local got output
  if output="$(PR_TITLE="${title}" PR_TITLE_TYPES="${types}" \
    PR_TITLE_MAX_LENGTH="${max}" bash "${check}" 2>&1)"; then
    got=pass
  else
    got=fail
  fi
  if [[ "${got}" != "${want}" ]]; then
    echo "NOT OK: expected ${want}, got ${got}: ${title@Q}"
    failures=$((failures + 1))
  elif [[ -n "${message}" && "${output}" != *"${message}"* ]]; then
    echo "NOT OK: expected output ${message@Q}, got ${output@Q}: ${title@Q}"
    failures=$((failures + 1))
  elif grep -qE '^::(warning|notice|debug|add-mask|stop-commands)' <<< "${output}"; then
    echo "NOT OK: the title injected a workflow command: ${title@Q}"
    failures=$((failures + 1))
  else
    echo "ok: ${want}: ${title@Q}"
  fi
}

# A title of exactly <n> characters: <prefix> padded with `x`
pad() {
  local prefix="$1" n="$2" padding
  padding="$(printf "%$((n - ${#prefix}))s" "")"
  printf '%s' "${prefix}${padding// /x}"
}

# Good titles
expect pass "fix: handle empty input"
expect pass "feat(api): add pagination"
expect pass "feat(access-control)!: drop legacy roles"
expect pass "refactor!: rename the config keys"
expect pass "ci: set up CI for the .github repo"
expect pass "docs: explain the v1.2.3 release"
# Acronyms and names may start the description
expect pass "docs: README typo"
expect pass "fix: API docs"
expect pass "fix!: OpenAPI auth removal"
expect pass "docs: MkDocs Material theme"
expect pass "fix: 404 on empty lists"

# Length: 50 characters pass, 51 fail; the scope counts too
expect pass "$(pad "feat(scope): add " 50)"
expect fail "$(pad "feat(scope): add " 51)" "Too long: 51 characters, at most 50 allowed"
expect fail "feat(access-control): add configured policies to the API" "Too long: 56"
# Length counts characters, not bytes (50 characters, 54 bytes)
expect pass "docs: add the café and naïve résumé examples here!"
# A custom limit
expect pass "fix: a b" "" 8
expect fail "fix: a bc" "Too long: 9 characters, at most 8 allowed" 8

# Types
expect fail "feature: add pagination" "Type 'feature' is not allowed"
expect fail "feat: add x" "use one of: fix" 50 "fix"
# Types on separate lines (a YAML block scalar)
expect pass "feat: add x" "" 50 $'fix\nfeat\n'
expect fail "Fix: handle empty input" "Not in the format"
expect fail "handle empty input" "Not in the format"

# Missing colon or space
expect fail "fix handle empty input" "Not in the format"
expect fail "fix:handle empty input" "Not in the format"
expect fail "fix(api) add pagination" "Not in the format"
expect fail "fix:  handle empty input" "Not in the format"
# Broken scope
expect fail "fix(): handle empty input" "Not in the format"
expect fail "fix(api: handle empty input" "Not in the format"
expect fail "fix(a b): handle empty input" "Not in the format"
# Misplaced `!`
expect fail "fix!(api): handle empty input" "Not in the format"

# Trailing period or ellipsis
expect fail "fix: handle empty input." "ends with a period"
expect fail "fix: handle empty input…" "ends with a period"
# Capitalised description
expect fail "fix: Handle empty input" "starts with a capitalised word"
expect fail "fix: Add" "starts with a capitalised word"
# Empty description or title
expect fail "fix: " "Not in the format"
expect fail "" "The title is empty"
# Leading or trailing whitespace
expect fail " fix: handle empty input" "Not in the format"
expect fail "fix: handle empty input " "ends with whitespace"
expect fail $'fix: handle empty input ' "ends with whitespace"

# Several rules at once are all reported (51 characters)
several="feature: Add a very long title that goes on and on."
expect fail "${several}" "Too long: 51"
expect fail "${several}" "Type 'feature' is not allowed"
expect fail "${several}" "starts with a capitalised word"
expect fail "${several}" "ends with a period"

# Invalid inputs
expect fail "fix: a" "Invalid maximum length: 'abc'" abc
expect fail "fix: a" "Invalid maximum length: '0'" 0
expect fail "fix: a" "No allowed types given" 50 " "

# More than one line, without injecting a workflow command
expect fail $'fix: handle empty input\n::warning::injected' "more than one line"
expect fail $'fix: handle empty input\r::warning::injected' "more than one line"
# Shell metacharacters are data, not code
marker="$(mktemp -u)"
expect pass "fix: \$(touch ${marker}) \`touch ${marker}\`" "" 200
if [[ -e "${marker}" ]]; then
  echo "NOT OK: the title was executed"
  rm -f "${marker}"
  failures=$((failures + 1))
fi

if ((failures > 0)); then
  echo "${failures} test(s) failed"
  exit 1
fi
echo "All tests passed"
