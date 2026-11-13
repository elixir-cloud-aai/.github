#!/usr/bin/env bash
# Checks that an image doesn't contain pip. Input in the environment:
# SCAN_PACKAGES, the path of Trivy's JSON report of the image with all
# packages listed (`--list-all-pkgs`). Fails if the report lists pip as an
# installed Python package (a `pip-*.dist-info` anywhere in the image, or a
# conda package) or as an OS package (`python3-pip`, `py3-pip` and the like; not the wheel-only
# `python3-pip-whl`), and if the report can't be read; lists the packages
# found in the log and, if available, the step summary
set -euo pipefail

report="${SCAN_PACKAGES:-}"

if [[ -z "${report}" || ! -f "${report}" ]] \
  || ! jq -e 'type == "object" and has("ArtifactName")' "${report}" >/dev/null 2>&1; then
  echo "::error title=Scan image::No package list of the image to check for pip"
  exit 1
fi

found="$(jq -r '
  [.Results[]?
    | . as $result
    | .Packages[]?
    | select(
        (($result.Class == "lang-pkgs"
            and ($result.Type | IN("python-pkg", "conda-pkg")))
          and ((.Name // "") | ascii_downcase) == "pip")
        or ($result.Class == "os-pkgs"
          and ((.Name // "") | ascii_downcase
            | test("^(py[0-9]*|python[0-9.]*)-pip$"))))
    | "\(.Name) \(.Version // "?") (\(.FilePath // $result.Target // "?"))"]
  | unique[]' "${report}")"

if [[ -n "${found}" ]]; then
  # Strip characters that could start a workflow command
  found="${found//::/}"
  echo "::error title=Scan image::The image contains pip: ${found//$'\n'/, }"
  if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
    {
      echo "### The image contains pip"
      echo
      while IFS= read -r line; do
        echo "- ${line}"
      done <<< "${found}"
      echo
      echo "Remove pip from the image (e.g., install packages with uv), or"
      echo "set the input \`fail-on-pip\` of the scan action to \`false\`."
    } >> "${GITHUB_STEP_SUMMARY}"
  fi
  exit 1
fi
echo "No pip in the image"
