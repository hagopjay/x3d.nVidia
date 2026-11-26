#!/usr/bin/env bash
# Create hagopjay/x3d.nVidia on GitHub from this folder and push main.
# Run once, from the unzipped folder, with the GitHub CLI signed in as hagopjay:
#   bash tools/bootstrap.sh            # private (default)
#   VISIBILITY=public bash tools/bootstrap.sh
set -euo pipefail
REPO="${REPO:-hagopjay/x3d.nVidia}"
VISIBILITY="${VISIBILITY:-private}"
cd "$(dirname "$0")/.."

if gh repo view "$REPO" >/dev/null 2>&1; then
  remote_main=$(gh api "repos/$REPO/commits/main" -q .sha 2>/dev/null || true)
  if [ -n "$remote_main" ] && git merge-base --is-ancestor "$(git rev-parse HEAD)" "$remote_main" 2>/dev/null; then
    echo "already in main: $REPO @ ${remote_main:0:7}"; exit 0
  fi
  echo "$REPO already exists and does not contain this commit. Not pushing; review by hand." >&2
  exit 1
fi

gh repo create "$REPO" "--$VISIBILITY" \
  --description "Where X3D meets NVIDIA: NIM, Omniverse/OpenUSD, Gaussian splats, CUDA — with receipts" \
  --source . --remote origin --push
echo "created https://github.com/$REPO ($VISIBILITY) at $(git rev-parse --short HEAD)"
