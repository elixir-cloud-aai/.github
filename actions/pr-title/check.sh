#!/usr/bin/env bash
# Checks a pull request title against the organisation's convention:
# `<type>[(<scope>)][!]: <description>` (Conventional Commits) with an allowed
# type, at most PR_TITLE_MAX_LENGTH characters in total, a description that
# doesn't start with a capitalised word (`Add`; `API`, `OpenAPI`, `S3` are fine)
# and no trailing period or whitespace, on one line. Reads the title, the
# allowed types (separated by whitespace, newlines included) and the maximum
# length from the environment (PR_TITLE, PR_TITLE_TYPES,
# PR_TITLE_MAX_LENGTH), never from arguments or interpolated code. Reports
# every failed rule, as a GitHub Actions error annotation, and exits with 1
# if any rule failed. Lengths count Unicode code points
set -euo pipefail

# Count characters, not bytes
export LC_ALL=C.UTF-8

title="${PR_TITLE-}"
max_length="${PR_TITLE_MAX_LENGTH:-50}"
read -r -d '' -a types <<< "${PR_TITLE_TYPES-}" || true

# Up to 9999, so that Bash arithmetic neither overflows nor reads octal
if ! [[ "${max_length}" =~ ^[1-9][0-9]{0,3}$ ]]; then
  echo "::error title=PR title::Invalid maximum length (an integer from 1 to 9999 is required)"
  exit 1
fi
if ((${#types[@]} == 0)); then
  echo "::error title=PR title::No allowed types given"
  exit 1
fi
if [[ -z "${title}" ]]; then
  echo "::error title=PR title::The title is empty (the action checks pull_request events)"
  exit 1
fi

errors=()
length="${#title}"

# One line only; also keeps the title from starting a line of the log, where
# it could be read as a workflow command
if [[ "${title}" == *$'\n'* || "${title}" == *$'\r'* ]]; then
  errors+=("The title has more than one line")
  title="${title//[$'\n\r']/ }"
fi

if ((length > 10#${max_length})); then
  errors+=("Too long: ${length} characters, at most ${max_length} allowed")
fi

# Whitespace that [[:space:]] misses: no-break, figure, narrow no-break,
# zero-width and zero-width no-break spaces
invisible=$'\u00a0\u2007\u202f\u200b\ufeff'

# Type (lowercase letters, digits, hyphens), optional scope (no spaces or parentheses), optional `!`, then `: `
# and a description that starts with a visible character
format="^([a-z][a-z0-9-]*)(\\([^()[:space:]${invisible}]+\\))?(!)?: ([^[:space:]${invisible}].*)\$"
if [[ "${title}" =~ ${format} ]]; then
  type="${BASH_REMATCH[1]}"
  description="${BASH_REMATCH[4]}"
  allowed=false
  for t in "${types[@]}"; do
    if [[ "${type}" == "${t}" ]]; then
      allowed=true
      break
    fi
  done
  if [[ "${allowed}" != true ]]; then
    errors+=("Type '${type}' is not allowed; use one of: ${types[*]}")
  fi
  # A capitalised word (`Add`), not an acronym or name (`API`, `OpenAPI`,
  # `S3`, `C++`)
  if [[ "${description}" =~ ^[[:upper:]][[:lower:]]*([[:space:]${invisible},.:!?]|$) ]]; then
    errors+=("The description starts with a capitalised word; use lowercase")
  fi
else
  errors+=("Not in the format '<type>[(<scope>)][!]: <description>' (Conventional Commits)")
fi

if [[ "${title}" =~ [[:space:]${invisible}]$ ]]; then
  errors+=("The title ends with whitespace")
fi
# Also an ellipsis
if [[ "${title}" == *. || "${title}" == *$'\u2026' ]]; then
  errors+=("The title ends with a period")
fi

if ((${#errors[@]} > 0)); then
  for e in "${errors[@]}"; do
    echo "::error title=PR title::${e}"
  done
  echo "Title (${length} characters): ${title}"
  exit 1
fi
echo "PR title OK (${length} of at most ${max_length} characters): ${title}"
