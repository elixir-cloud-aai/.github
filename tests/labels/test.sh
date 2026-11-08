#!/usr/bin/env bash
# Tests of the organisation's labels: labels/labels.yml is well-formed, and
# labels/sync.sh reports and fixes differences (against a stubbed `gh`).
set -euo pipefail
cd "$(dirname "$0")/../.."
FILE=labels/labels.yml
fail() { echo "FAIL: $*" >&2; exit 1; }

# labels.yml: unique names, colours as six hex digits, GitHub's limits
all=$(yq -o=json '(.labels // []) + (.temporary // [])' "$FILE")
[[ $(jq length <<<"$all") -gt 0 ]] || fail "no labels"
dupes=$(jq -r '[.[].name] | group_by(.) | map(select(length > 1) | .[0]) | .[]' <<<"$all")
[[ -z "$dupes" ]] || fail "duplicate names: $dupes"
bad=$(jq -r '.[] | select((.color | type) != "string" or (.color | test("^[0-9a-f]{6}$") | not)) | .name' <<<"$all")
[[ -z "$bad" ]] || fail "bad colours: $bad"
long=$(jq -r '.[] | select((.name | length) > 50 or ((.description // "") | length) > 100) | .name' <<<"$all")
[[ -z "$long" ]] || fail "too long: $long"
# Default labels follow "<key>: <value>"
odd=$(yq -o=json '.labels' "$FILE" | jq -r '.[] | select(.name | test("^[a-z][a-z ]*: \\S") | not) | .name')
[[ -z "$odd" ]] || fail "not '<key>: <value>': $odd"
echo "ok: labels.yml"

# sync.sh against a stub `gh` that serves one repository's labels and
# records label writes
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cat >"$tmp/labels.yml" <<'EOF'
labels:
  - name: 'type: bug'
    color: "0075ca"
    description: Something isn't working
  - name: 'type: docs'
    color: "0075ca"
    description: Docs
temporary:
  - name: 'ecp-wp4: M4.1'
    color: "1d76db"
    description: Milestone
EOF
mkdir "$tmp/bin"
cat >"$tmp/bin/gh" <<'EOF'
#!/usr/bin/env bash
# Stub: `label list` prints the repository's labels as `--jq` would;
# `label create` records its arguments
case "$1 $2" in
  "label list")
    printf '%s\t%s\t%s\n' "type: bug" "0075ca" "Something isn't working" \
      "type: docs" "ffffff" "Docs" "python" "2b67c6" "" ;;
  "label create") printf '%s\n' "$*" >>"$GH_LOG" ;;
  *) echo "unexpected: $*" >&2; exit 3 ;;
esac
EOF
chmod +x "$tmp/bin/gh"
export PATH="$tmp/bin:$PATH" GH_LOG="$tmp/gh.log"
: >"$GH_LOG"

# --check: reports, writes nothing, exits 1
set +e
out=$(labels/sync.sh --check --file "$tmp/labels.yml" repo 2>&1)
status=$?
set -e
[[ $status -eq 1 ]] || fail "--check exit status $status, expected 1"
grep -Fx "repo: differs 'type: docs'" <<<"$out" >/dev/null || fail "no 'differs' in: $out"
grep -Fx "repo: missing 'ecp-wp4: M4.1'" <<<"$out" >/dev/null || fail "no 'missing' in: $out"
grep -Fx "repo: unlisted 'python' (not changed)" <<<"$out" >/dev/null || fail "no 'unlisted' in: $out"
if grep -F "'type: bug'" <<<"$out" >/dev/null; then fail "reported an aligned label: $out"; fi
[[ ! -s "$GH_LOG" ]] || fail "--check wrote labels: $(cat "$GH_LOG")"
echo "ok: --check"

# sync: writes exactly the two differences
labels/sync.sh --file "$tmp/labels.yml" repo >/dev/null
[[ $(wc -l <"$GH_LOG") -eq 2 ]] || fail "expected 2 writes, got: $(cat "$GH_LOG")"
grep -F "label create type: docs --repo elixir-cloud-aai/repo --color 0075ca --description Docs --force" "$GH_LOG" >/dev/null \
  || fail "type: docs not fixed: $(cat "$GH_LOG")"
grep -F "label create ecp-wp4: M4.1 --repo elixir-cloud-aai/repo --color 1d76db" "$GH_LOG" >/dev/null \
  || fail "ecp-wp4: M4.1 not created: $(cat "$GH_LOG")"
echo "ok: sync"

# default repositories come from the file
printf 'repositories:\n  - one\n  - two\n' >>"$tmp/labels.yml"
out=$(labels/sync.sh --check --file "$tmp/labels.yml" 2>&1 || true)
grep -F "one: missing 'ecp-wp4: M4.1'" <<<"$out" >/dev/null || fail "repo 'one' not synced: $out"
grep -F "two: missing 'ecp-wp4: M4.1'" <<<"$out" >/dev/null || fail "repo 'two' not synced: $out"
echo "ok: repositories"

# --check also fails on unlisted labels alone
cat >"$tmp/aligned.yml" <<'EOF2'
labels:
  - name: 'type: bug'
    color: "0075ca"
    description: Something isn't working
  - name: 'type: docs'
    color: "ffffff"
    description: Docs
EOF2
if labels/sync.sh --check --file "$tmp/aligned.yml" repo >/dev/null 2>&1; then
  fail "--check passed with an unlisted label"
fi
echo "ok: unlisted"

# a failing producer stops the script
if labels/sync.sh --check --file "$tmp/missing.yml" repo >/dev/null 2>&1; then
  fail "a missing file didn't stop the script"
fi
echo "ok: errors"
