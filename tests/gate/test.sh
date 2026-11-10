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
# Cancelled jobs fail the gate, whatever cancelled them (see the README)
expect fail "{\"lint\":{\"result\":\"cancelled\"},\"test\":${ok}}" "" "lint: cancelled"
expect pass "{\"lint\":${ok},\"push\":{\"result\":\"skipped\"}}" "push publish"
# IDs on separate lines (e.g. a YAML block scalar)
expect pass "{\"push\":{\"result\":\"skipped\"},\"publish\":{\"result\":\"skipped\"}}" $'push\npublish\n'
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
# Malformed entries fail with the gate's own message
expect fail "{\"a\":\"x\"}" "a" "a: malformed"
expect fail "{\"a\":{}}" "" "a: null"

# The step summary lists the offending jobs
summary="$(mktemp)"
trap 'rm -f "${summary}"' EXIT
if GATE_NEEDS="{\"test\":{\"result\":\"failure\"}}" GATE_ALLOW_SKIPPED="" \
  GITHUB_STEP_SUMMARY="${summary}" bash "${check}" >/dev/null 2>&1; then
  echo "NOT OK: expected fail with a step summary"
  failures=$((failures + 1))
elif ! grep -qx -- "- test: failure" "${summary}"; then
  echo "NOT OK: step summary lacks the failed job: $(cat "${summary}")"
  failures=$((failures + 1))
else
  echo "ok: step summary"
fi

# The gate jobs of this repository's CI and of the README's example run
# `always()` (not `!cancelled()`), and only a new head commit of a pull
# request cancels runs in progress (see "Cancelled runs" in the README)
# gate_if <file>: the job-level `if:` of the job `passed`
gate_if() {
  awk '
    # The indent of the first non-blank character
    { indent = match($0, /[^ ]/) }
    /^ *passed:$/ { job = indent; next }
    !job || !/^ *[^ #]/ { next }
    indent <= job { exit }
    # The indent of the job keys, from the first one
    !key { key = indent }
    indent == key && /^ *if:/ { sub(/^ *if: */, ""); print; exit }
  ' "$1"
}
# The parser finds the job-level condition of `passed` only, not those of
# other jobs, comments or steps
fixture="$(mktemp)"
trap 'rm -f "${summary}" "${fixture}"' EXIT
printf 'jobs:\n  lint:\n    if: a\n  passed:\n    # if: b\n    needs: [lint]\n    if: c\n  next:\n    if: d\n' > "${fixture}"
if [[ "$(gate_if "${fixture}")" == c ]]; then
  echo "ok: gate condition parser"
else
  echo "NOT OK: gate condition parser: $(gate_if "${fixture}")"
  failures=$((failures + 1))
fi
printf 'jobs:\n  passed:\n    steps:\n      - if: s\n        run: x\n  next:\n    if: d\n' > "${fixture}"
if [[ -z "$(gate_if "${fixture}")" ]]; then
  echo "ok: gate condition parser, no job-level condition"
else
  echo "NOT OK: gate condition parser took a step's or job's condition: $(gate_if "${fixture}")"
  failures=$((failures + 1))
fi
# shellcheck disable=SC2016 # a GitHub expression, not a shell one
cancel_expected='${{ github.event_name == '\''pull_request'\'' && github.event.action == '\''synchronize'\'' }}'
for file in .github/workflows/ci.yml actions/gate/README.md; do
  condition="$(gate_if "${file}")"
  if [[ "${condition}" == "always()" ]]; then
    echo "ok: gate condition in ${file}"
  else
    echo "NOT OK: gate condition in ${file}: ${condition@Q}"
    failures=$((failures + 1))
  fi
done
cancel="$(sed -n 's/^ *cancel-in-progress: *//p' .github/workflows/ci.yml)"
# The README's example is the same, folded (`>-`) to fit the line length
cancel_readme="$(awk '
  /^ *cancel-in-progress: >-$/ { inside = 1; next }
  inside && /^ +[^ ]/ { sub(/^ +/, ""); out = out (out ? " " : "") $0; next }
  inside { exit }
  END { print out }
' actions/gate/README.md)"
for pair in "ci.yml:${cancel}" "README.md:${cancel_readme}"; do
  if [[ "${pair#*:}" == "${cancel_expected}" ]]; then
    echo "ok: cancel-in-progress in ${pair%%:*}"
  else
    echo "NOT OK: cancel-in-progress in ${pair%%:*}: ${pair#*:}"
    failures=$((failures + 1))
  fi
done

if ((failures > 0)); then
  echo "${failures} test(s) failed"
  exit 1
fi
echo "All tests passed"
