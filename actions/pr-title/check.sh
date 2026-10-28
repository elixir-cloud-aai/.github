#!/usr/bin/env bash
# Checks a pull request title against the organisation's convention:
# `<type>[(<scope>)][!]: <description>` (Conventional Commits), at most
# PR_TITLE_MAX_LENGTH characters in total, a description that doesn't start
# with an uppercase letter and has no trailing period. Reads the title, the
# allowed types (separated by whitespace) and the maximum length from the
# environment (PR_TITLE, PR_TITLE_TYPES, PR_TITLE_MAX_LENGTH), never from
# arguments or interpolated code. Reports every failed rule, as a GitHub
# Actions error annotation, and exits with 1 if any rule failed
set -euo pipefail

# Count characters, not bytes
export LC_ALL=C.UTF-8

title="${PR_TITLE-}"
max_length="${PR_TITLE_MAX_LENGTH:-50}"
read -r -a types <<< "${PR_TITLE_TYPES-}"

if ! [[ "${max_length}" =~ ^[1-9][0-9]*$ ]]; then
  echo "::error title=PR title::Invalid maximum length: '${max_length}'"
  exit 1
fi
if ((${#types[@]} == 0)); then
  echo "::error title=PR title::No allowed types given"
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

if ((length > max_length)); then
  errors+=("Too long: ${length} characters, at most ${max_length} allowed")
fi

# Type, optional scope (no spaces or parentheses), optional `!`, then `: `
# and a description that starts with a non-space character
format='^([a-z]+)(\([^()[:space:]]+\))?(!)?: ([^[:space:]].*)$'
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
  if [[ "${description}" =~ ^[[:upper:]] ]]; then
    errors+=("The description starts with an uppercase letter")
  fi
  if [[ "${description}" =~ [[:space:]]$ ]]; then
    errors+=("The title ends with whitespace")
  fi
else
  errors+=("Not in the format '<type>[(<scope>)][!]: <description>' (Conventional Commits)")
fi

if [[ "${title}" == *. ]]; then
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
