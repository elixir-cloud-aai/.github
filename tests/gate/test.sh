#!/usr/bin/env bash
# Tests of `actions/gate/check.sh`: runs it on sets of job results and
# compares the exit status, and for failures the reported jobs, with the
# expected ones. Run from the repository root: `bash tests/gate/test.sh`
set -euo pipefail

check="actions/gate/check.sh"
failures=0

# expect <pass|fail> <needs JSON> [allowed skips] [expected output]
expect() {
  local want="$1" needs="$2" allowed="${3-}" message="${4-}"
  local got output
  if output="$(GATE_NEEDS="${needs}" GATE_ALLOW_SKIPPED="${allowed}" \
    GITHUB_STEP_SUMMARY="" bash "${check}" 2>&1)"; then
    got=pass
  else
    got=fail
  fi
  if [[ "${got}" != "${want}" ]]; then
    echo "NOT OK: expected ${want}, got ${got}: ${needs} (${allowed@Q})"
    failures=$((failures + 1))
  elif [[ -n "${message}" && "${output}" != *"${message}"* ]]; then
    echo "NOT OK: expected output ${message@Q}, got ${output@Q}"
    failures=$((failures + 1))
  else
    echo "ok: ${want}: ${needs} (${allowed@Q})"
  fi
}

ok='{"result":"success","outputs":{}}'
expect pass "{\"lint\":${ok},\"test\":${ok}}"
expect fail "{\"lint\":${ok},\"test\":{\"result\":\"failure\"}}" "" "test: failure"
expect fail "{\"lint\":{\"result\":\"cancelled\"},\"test\":${ok}}" "" "lint: cancelled"
expect pass "{\"lint\":${ok},\"push\":{\"result\":\"skipped\"}}" "push publish"
expect fail "{\"lint\":${ok},\"push\":{\"result\":\"skipped\"}}" "publish" "push: skipped"
expect fail "{\"lint\":${ok},\"push\":{\"result\":\"skipped\"}}" "" "push: skipped"
# An allowed skip doesn't excuse a failure of the same job
expect fail "{\"push\":{\"result\":\"failure\"}}" "push" "push: failure"
# Partial names don't match
expect fail "{\"push-image\":{\"result\":\"skipped\"}}" "push" "push-image: skipped"
expect fail "{}" "" "No job results"
expect fail "" "" "No job results"
expect fail "null" "" "No job results"
# Job IDs can't inject workflow commands
expect fail "{\"::warning::x\":{\"result\":\"failure\"}}" "" "warningx: failure"

if ((failures > 0)); then
  echo "${failures} test(s) failed"
  exit 1
fi
echo "All tests passed"
