#!/usr/bin/env bash
# Create hagopjay/x3d.nVidia on GitHub from this folder and push main.
# Works in WSL, Linux and macOS. Safe to re-run.
#
#   bash tools/bootstrap.sh                    # private repo (default)
#   VISIBILITY=public bash tools/bootstrap.sh
#   DRY_RUN=1 bash tools/bootstrap.sh          # checks only, changes nothing
#
# Needs: git, gh (GitHub CLI) signed in as hagopjay (`gh auth login`).
set -euo pipefail
REPO="${REPO:-hagopjay/x3d.nVidia}"
VISIBILITY="${VISIBILITY:-private}"
DRY_RUN="${DRY_RUN:-0}"
cd "$(dirname "$0")/.."
here="$(pwd)"

say()  { printf '[bootstrap] %s\n' "$*"; }
die()  { printf '[bootstrap] STOP: %s\n' "$*" >&2; exit 1; }

# ---- preflight ---------------------------------------------------------------
command -v git >/dev/null || die "git not found. In WSL/Ubuntu: sudo apt update && sudo apt install -y git"
command -v gh  >/dev/null || die "GitHub CLI not found. In WSL/Ubuntu: sudo apt install -y gh  (or see https://cli.github.com)"
[ -d .git ] || die "no .git folder here ($here). Unzip the whole bootstrap zip; don't copy single files."

case "$here" in
  /mnt/*) say "note: you're on a Windows drive ($here). It works, but ~/ inside WSL is faster and avoids permission quirks." ;;
esac

# Git refuses repos owned by another user (common on /mnt/c). Trust this one folder only,
# for this run, in a way every child process inherits (gh runs git itself when it pushes).
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0="$here"
GIT=(git)

# Windows tools can flip file modes or line endings on unzip; that must not count as a change.
"${GIT[@]}" config core.fileMode false
"${GIT[@]}" config core.autocrlf false
if [ -n "$("${GIT[@]}" status --porcelain)" ]; then
  say "files differ from the commit (likely line endings from a Windows unzip); restoring them:"
  "${GIT[@]}" status --short | head -20
  [ "$DRY_RUN" = 1 ] || "${GIT[@]}" checkout -- .
fi
head_sha="$("${GIT[@]}" rev-parse HEAD)"
say "local main = ${head_sha:0:7} ($("${GIT[@]}" log -1 --format=%s))"

gh auth status >/dev/null 2>&1 || die "gh is not signed in. Run: gh auth login   (GitHub.com, HTTPS, sign in as hagopjay)"
who="$(gh api user -q .login 2>/dev/null || true)"
owner="${REPO%%/*}"
[ "$who" = "$owner" ] || say "warning: gh is signed in as '$who', not '$owner'. Creating under $owner needs that account or org rights."

# ---- already there? ----------------------------------------------------------
if gh repo view "$REPO" >/dev/null 2>&1; then
  remote_main="$(gh api "repos/$REPO/commits/main" -q .sha 2>/dev/null || true)"
  if [ "$remote_main" = "$head_sha" ]; then
    say "already in main: $REPO @ ${remote_main:0:7}"; exit 0
  fi
  if [ -n "$remote_main" ]; then
    "${GIT[@]}" fetch -q "https://github.com/$REPO" main 2>/dev/null || true
    if "${GIT[@]}" merge-base --is-ancestor "$head_sha" "$remote_main" 2>/dev/null; then
      say "already in main: $REPO @ ${remote_main:0:7} (contains ${head_sha:0:7})"; exit 0
    fi
    if "${GIT[@]}" merge-base --is-ancestor "$remote_main" "$head_sha" 2>/dev/null; then
      say "$REPO main is ${remote_main:0:7}, behind this zip: fast-forwarding to ${head_sha:0:7}"
      [ "$DRY_RUN" = 1 ] && { say "DRY_RUN: would push"; exit 0; }
      gh auth setup-git >/dev/null
      "${GIT[@]}" push "https://github.com/$REPO.git" "HEAD:main"
      say "done: https://github.com/$REPO @ ${head_sha:0:7}"; exit 0
    fi
  fi
  die "$REPO exists and its main (${remote_main:0:7}) has diverged from this zip. Not pushing; review by hand."
fi

# ---- create ------------------------------------------------------------------
if [ "$DRY_RUN" = 1 ]; then
  say "DRY_RUN: would create $REPO ($VISIBILITY) and push ${head_sha:0:7}. All checks passed."; exit 0
fi
gh auth setup-git >/dev/null   # lets git push with gh's login
"${GIT[@]}" remote remove origin 2>/dev/null || true
gh repo create "$REPO" "--$VISIBILITY" \
  --description "Where X3D meets NVIDIA: NIM, Omniverse/OpenUSD, Gaussian splats, CUDA, with receipts" \
  --source . --remote origin --push
say "created https://github.com/$REPO ($VISIBILITY) @ ${head_sha:0:7}"
say "next: install the Claude GitHub App on it so cloud sessions can clone it: https://github.com/apps/claude"
