#!/usr/bin/env bash
# Checks that an image doesn't contain pip. Input in the environment:
# SCAN_PACKAGES, the path of Trivy's JSON report of the image with all
# packages listed (`--list-all-pkgs`). Fails if the report lists pip as a
# Python, conda or OS package (see "pip in images" in README.md for what
# counts), and if the report can't be read; lists the packages found in the
# log and, if available, the step summary
set -euo pipefail

report="${SCAN_PACKAGES:-}"

if [[ -z "${report}" || ! -f "${report}" ]] \
  || ! jq -e 'type == "object" and has("ArtifactName")' "${report}" \
    >/dev/null 2>&1; then
  echo "::error title=Scan image::No package list of the image to check for pip"
  exit 1
fi

# One line per package; control characters (from the image's metadata) are
# removed, so that a field can't start a new log line
found="$(jq -r '
  [.Results[]?
    | . as $result
    | .Packages[]?
    | ((.Name // "") | tostring | ascii_downcase) as $name
    | select(
        ($result.Class == "lang-pkgs"
          and ($result.Type | IN("python-pkg", "conda-pkg"))
          and $name == "pip")
        or ($result.Class == "os-pkgs"
          and ($name | test("^((platform-)?(py|python)[0-9.]*-)?pip$"))))
    | "\(.Name) \(.Version // "?") (\(.FilePath // $result.Target // "?"))"
    | gsub("[[:cntrl:]]"; "")]
  | unique[]' "${report}")"

if [[ -n "${found}" ]]; then
  # Strip characters that could start a workflow command, and escape `%` as
  # the runner expects in a command's message
  found="${found//::/}"
  message="${found//%/%25}"
  echo "::error title=Scan image::The image contains pip: ${message//$'\n'/, }"
  if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
    {
      echo "### The image contains pip"
      echo
      # As code, so that the image's metadata isn't rendered as Markdown
      while IFS= read -r line; do
        echo "- \`${line//\`/}\`"
      done <<< "${found}"
      echo
      echo "Remove pip from the image (e.g., install packages with uv), or"
      echo "set the input \`fail-on-pip\` of the scan action to \`false\`."
    } >> "${GITHUB_STEP_SUMMARY}"
  fi
  exit 1
fi
echo "No pip in the image"
