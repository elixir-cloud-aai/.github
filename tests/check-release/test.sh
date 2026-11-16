#!/usr/bin/env bash
# Tests of the check-release action's script (`check.py`): versions, the
# citation metadata, and the checks of the tag, the branch and CI (against a
# stand-in for `gh`). Standard library only (unittest), like the script.
set -euo pipefail
cd "$(dirname "$0")/../.."
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover --start-directory tests/check-release \
  --pattern 'test_*.py' --verbose
