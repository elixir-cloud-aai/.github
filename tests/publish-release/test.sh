#!/usr/bin/env bash
# Tests of the publish-release action's script (`publish.py`): the check of
# curated notes, the release body, versions, and the calls of `gh` (against
# a stand-in). Standard library only (unittest), like the script.
set -euo pipefail
cd "$(dirname "$0")/../.."
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover --start-directory tests/publish-release \
  --pattern 'test_*.py' --verbose
