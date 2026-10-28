#!/usr/bin/env bash
# Tests of `actions/pr-title/check.sh`: runs it on good and bad titles and
# compares the exit status with the expected one. Run from the repository
# root: `bash tests/pr-title/test.sh`
set -euo pipefail

check="actions/pr-title/check.sh"
types="build chore ci docs feat fix perf refactor revert style test"
failures=0

# expect <pass|fail> <title> [max length]
expect() {
  local want="$1" title="$2" max="${3:-50}" got
  if PR_TITLE="${title}" PR_TITLE_TYPES="${types}" PR_TITLE_MAX_LENGTH="${max}" \
    bash "${check}" > /dev/null 2>&1; then
    got=pass
  else
    got=fail
  fi
  if [[ "${got}" == "${want}" ]]; then
    echo "ok: ${want}: ${title@Q}"
  else
    echo "NOT OK: expected ${want}, got ${got}: ${title@Q}"
    failures=$((failures + 1))
  fi
}

# Good titles
expect pass "fix: handle empty input"
expect pass "feat(api): add pagination"
expect pass "feat(access-control)!: drop legacy roles"
expect pass "refactor!: rename the config keys"
expect pass "ci: set up CI for the .github repo"
expect pass "docs: explain the v1.2.3 release"
expect pass "chore: bump dependencies"
# Exactly 50 characters
expect pass "feat(scope): add a description of 34 characterssxy"
# Length counts characters, not bytes
expect pass "docs: add the café and naïve résumé examples here!"

# Too long: 51 characters; the scope counts too
expect fail "feat(scope): add a description of 34 characterssxyz"
expect fail "feat(access-control): add configured policies to the API"
# A custom limit
expect pass "fix: a b" 8
expect fail "fix: a bc" 8
# Wrong or missing type
expect fail "feature: add pagination"
expect fail "Fix: handle empty input"
expect fail "handle empty input"
# Missing colon or space
expect fail "fix handle empty input"
expect fail "fix:handle empty input"
expect fail "fix(api) add pagination"
expect fail "fix:  handle empty input"
# Broken scope
expect fail "fix(): handle empty input"
expect fail "fix(api: handle empty input"
expect fail "fix(a b): handle empty input"
# Misplaced `!`
expect fail "fix!(api): handle empty input"
# Trailing period
expect fail "fix: handle empty input."
# Description starts with an uppercase letter
expect fail "fix: Handle empty input"
# Empty description or title
expect fail "fix: "
expect fail ""
# Leading or trailing whitespace
expect fail " fix: handle empty input"
expect fail "fix: handle empty input "
# More than one line
expect fail $'fix: handle empty input\n::warning::injected'
# Shell metacharacters are data, not code
marker="$(mktemp -u)"
expect pass "fix: \$(touch ${marker}) \`touch ${marker}\`" 200
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
