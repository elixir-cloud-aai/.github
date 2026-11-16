#!/usr/bin/env bash
# Tests of the release-image action's script (`release.py`): settings, the
# check of the version's image tag, the `latest` decision and the tagging
# (against stand-ins for `gh` and `docker`). Standard library only
# (unittest), like the script.
set -euo pipefail
cd "$(dirname "$0")/../.."
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover --start-directory tests/release-image \
  --pattern 'test_*.py' --verbose
