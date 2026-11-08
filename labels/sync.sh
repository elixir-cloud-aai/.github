#!/usr/bin/env bash
# Sync the organisation's labels (labels/labels.yml) to repositories.
#
# Creates missing labels and updates the colour and description of existing
# ones, for the `labels` and `temporary` lists of labels.yml. Labels a
# repository has beyond those are only reported, never deleted: decide on
# them by hand (rename them with `gh label edit` to keep their assignments).
#
# Usage: labels/sync.sh [--check] [--all] [--file <labels.yml>] [<repo>...]
#   --check  only report differences; exit 1 if there are any
#   --all    all repositories of the organisation that aren't archived or forks
#   <repo>   repository names in the organisation (default: the
#            `repositories` list of labels.yml)
# Needs: gh (logged in, with write access to the repositories), yq (v4), jq.
set -euo pipefail

ORG=${ORG:-elixir-cloud-aai}
FILE=$(dirname "$0")/labels.yml
CHECK=false
ALL=false
REPOS=()
while (($#)); do
  case $1 in
    --check) CHECK=true ;;
    --all) ALL=true ;;
    --file) FILE=$2; shift ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    -*) echo "unknown option: $1" >&2; exit 2 ;;
    *) REPOS+=("$1") ;;
  esac
  shift
done

# Wanted labels as "name<TAB>color<TAB>description", from both lists
mapfile -t WANTED < <(yq -o=json '(.labels // []) + (.temporary // [])' "$FILE" \
  | jq -r '.[] | [.name, (.color | ascii_downcase), (.description // "")] | @tsv')
if ((${#WANTED[@]} == 0)); then
  echo "no labels in $FILE" >&2
  exit 2
fi

if $ALL; then
  mapfile -t REPOS < <(gh repo list "$ORG" --limit 1000 --no-archived --source \
    --json name --jq '.[].name' | sort)
elif ((${#REPOS[@]} == 0)); then
  mapfile -t REPOS < <(yq '.repositories // [] | .[]' "$FILE")
fi
if ((${#REPOS[@]} == 0)); then
  echo "no repositories: name them, use --all or fill 'repositories' in $FILE" >&2
  exit 2
fi

differences=0
for repo in "${REPOS[@]}"; do
  current=$(gh label list --repo "$ORG/$repo" --limit 1000 --json name,color,description \
    --jq '.[] | [.name, (.color | ascii_downcase), (.description // "")] | @tsv')
  for wanted in "${WANTED[@]}"; do
    IFS=$'\t' read -r name color description <<<"$wanted"
    have=$(awk -F'\t' -v n="$name" '$1 == n' <<<"$current")
    if [[ "$have" == "$wanted" ]]; then
      continue
    fi
    differences=$((differences + 1))
    if [[ -z "$have" ]]; then
      echo "$repo: missing '$name'"
    else
      echo "$repo: differs '$name'"
    fi
    if ! $CHECK; then
      gh label create "$name" --repo "$ORG/$repo" --color "$color" \
        --description "$description" --force >/dev/null
    fi
  done
  # Labels beyond labels.yml: report only
  while IFS=$'\t' read -r name _; do
    [[ -z "$name" ]] && continue
    if ! printf '%s\n' "${WANTED[@]}" | cut -f1 | grep -Fx -- "$name" >/dev/null; then
      echo "$repo: unlisted '$name' (not changed)"
    fi
  done <<<"$current"
done

if $CHECK && ((differences > 0)); then
  echo "$differences difference(s); run without --check to fix them" >&2
  exit 1
fi
