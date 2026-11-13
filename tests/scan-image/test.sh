#!/usr/bin/env bash
# Tests of `actions/scan-image/check-pip.sh`: runs it on Trivy reports (JSON,
# all packages listed) and compares the exit status, and the reported
# packages, with the expected ones. Run from the repository root:
# `bash tests/scan-image/test.sh`
set -euo pipefail

check="actions/scan-image/check-pip.sh"
failures=0
tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT

# report <results JSON>: a Trivy report with these results, as a file
report() {
  local file
  file="$(mktemp -p "${tmp}")"
  printf '{"SchemaVersion": 2, "ArtifactName": "my-app:ci", "Results": %s}\n' \
    "$1" > "${file}"
  echo "${file}"
}

# expect <pass|fail> <description> <report file> [expected output]
expect() {
  local want="$1" description="$2" file="$3" message="${4-}"
  local got output
  if output="$(SCAN_PACKAGES="${file}" GITHUB_STEP_SUMMARY="" \
    bash "${check}" 2>&1)"; then
    got=pass
  else
    got=fail
  fi
  if [[ "${got}" != "${want}" ]]; then
    echo "NOT OK: expected ${want}, got ${got}: ${description}"
    failures=$((failures + 1))
  elif [[ -n "${message}" && "${output}" != *"${message}"* ]]; then
    echo "NOT OK: expected output ${message@Q}, got ${output@Q}"
    failures=$((failures + 1))
  else
    echo "ok: ${want}: ${description}"
  fi
}

python_pkgs() {
  printf '{"Target": "Python", "Class": "lang-pkgs", "Type": "python-pkg", "Packages": %s}' "$1"
}
os_pkgs() {
  printf '{"Target": "my-app:ci (debian 13.1)", "Class": "os-pkgs", "Type": "debian", "Packages": %s}' "$1"
}
site="usr/local/lib/python3.13/site-packages"

expect pass "no results (e.g., an image from scratch)" \
  "$(printf '{"SchemaVersion": 2, "ArtifactName": "my-app:ci"}' > "${tmp}/empty"; echo "${tmp}/empty")"
expect pass "empty results" "$(report '[]')"
expect pass "other packages" "$(report "[$(python_pkgs \
  '[{"Name": "uv", "Version": "0.9.0"}, {"Name": "pipdeptree", "Version": "2.0"}]'), $(os_pkgs \
  '[{"Name": "python3", "Version": "3.13"}, {"Name": "python3-pip-whl", "Version": "25.1"}]')]")"
expect fail "pip as a Python package" "$(report "[$(python_pkgs \
  "[{\"Name\": \"uv\"}, {\"Name\": \"pip\", \"Version\": \"26.0\", \"FilePath\": \"${site}/pip-26.0.dist-info/METADATA\"}]")]")" \
  "The image contains pip: pip 26.0 (${site}/pip-26.0.dist-info/METADATA)"
expect fail "pip as a Python package, other case" "$(report "[$(python_pkgs \
  '[{"Name": "Pip", "Version": "26.0"}]')]")" "Pip 26.0 (Python)"
# Packages of other ecosystems named pip aren't Python's pip
expect pass "a package named pip of another ecosystem" "$(report \
  '[{"Target": "package-lock.json", "Class": "lang-pkgs", "Type": "npm", "Packages": [{"Name": "pip"}]}]')"
expect fail "python3-pip as an OS package" "$(report "[$(os_pkgs \
  '[{"Name": "python3-pip", "Version": "25.1"}]')]")" \
  "python3-pip 25.1 (my-app:ci (debian 13.1))"
expect fail "py3-pip as an OS package" "$(report "[$(os_pkgs \
  '[{"Name": "py3-pip", "Version": "25.1.1-r0"}]')]")" "py3-pip 25.1.1-r0"
expect fail "python3.12-pip as an OS package" "$(report "[$(os_pkgs \
  '[{"Name": "python3.12-pip", "Version": "23.2"}]')]")" "python3.12-pip 23.2"
expect fail "pip in several places, each listed once" "$(report "[$(python_pkgs \
  "[{\"Name\": \"pip\", \"Version\": \"26.0\", \"FilePath\": \"a/METADATA\"}, {\"Name\": \"pip\", \"Version\": \"24.0\", \"FilePath\": \"b/METADATA\"}]"), $(os_pkgs \
  '[{"Name": "python3-pip", "Version": "25.1"}]')]")" \
  "pip 24.0 (b/METADATA), pip 26.0 (a/METADATA), python3-pip 25.1"
# Package names can't inject workflow commands
expect fail "a package name with a workflow command" "$(report "[$(python_pkgs \
  '[{"Name": "pip", "Version": "::warning::x"}]')]")" "pip warningx"
# Missing or unreadable reports fail, rather than pass unchecked
expect fail "no report" "" "No package list"
expect fail "a missing report" "${tmp}/missing" "No package list"
expect fail "a report that isn't JSON" \
  "$(printf 'not JSON\n' > "${tmp}/bad"; echo "${tmp}/bad")" "No package list"
expect fail "a report that isn't Trivy's" \
  "$(printf '[]\n' > "${tmp}/array"; echo "${tmp}/array")" "No package list"

# The step summary lists the packages found
summary="${tmp}/summary"
if SCAN_PACKAGES="$(report "[$(os_pkgs '[{"Name": "py3-pip", "Version": "25.1"}]')]")" \
  GITHUB_STEP_SUMMARY="${summary}" bash "${check}" >/dev/null 2>&1; then
  echo "NOT OK: expected fail with a step summary"
  failures=$((failures + 1))
elif ! grep -q -- "- py3-pip 25.1" "${summary}"; then
  echo "NOT OK: step summary lacks the package: $(cat "${summary}")"
  failures=$((failures + 1))
else
  echo "ok: step summary"
fi

if ((failures > 0)); then
  echo "${failures} test(s) failed"
  exit 1
fi
echo "All tests passed"
