#!/usr/bin/env bash
# Push Verified CXAS Agent Repository to GitHub
# Runs scripts/pre_push_gate.sh first and aborts immediately if any gate fails.
#
# Usage:
#   ./scripts/push_to_github.sh [<github_remote_url>]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

if [[ $# -gt 1 ]]; then
  echo "Usage: ./scripts/push_to_github.sh [<github_remote_url>]"
  exit 1
fi

REMOTE_URL="${1:-}"

echo "Running mandatory pre-push verification gates before pushing to GitHub..."
"${SCRIPT_DIR}/pre_push_gate.sh"

if [[ -n "${REMOTE_URL}" ]]; then
  if git remote get-url origin >/dev/null 2>&1; then
    echo "Updating 'origin' remote URL to: ${REMOTE_URL}"
    git remote set-url origin "${REMOTE_URL}"
  else
    echo "Adding 'origin' remote: ${REMOTE_URL}"
    git remote add origin "${REMOTE_URL}"
  fi
fi

if ! git remote get-url origin >/dev/null 2>&1; then
  echo "ERROR: No 'origin' git remote configured."
  echo "Usage: ./scripts/push_to_github.sh <github_remote_url>"
  exit 1
fi

ORIGIN_URL="$(git remote get-url origin)"
echo ""
echo "Pushing verified branch 'main' to origin (${ORIGIN_URL})..."
git push -u origin main
echo "Successfully pushed 'main' to GitHub!"
