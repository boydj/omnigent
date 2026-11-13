#!/usr/bin/env bash
# Publish sandbox/ledger as its own private GitHub repo, for agents to work on.
#
#   ./sandbox/create-repo.sh [owner/name]          create it (default: <you>/ledger-sandbox)
#   ./sandbox/create-repo.sh [owner/name] --reset  put main back to the original
#                                                  code (force-push) between eval runs
#
# Needs the GitHub CLI signed in (gh auth login). The agents' guardrails only
# allow writes to repos listed under write_repos in agents/*/config.yaml;
# boydj/ledger-sandbox is already there.
set -euo pipefail

SRC="$(cd "$(dirname "$0")/ledger" && pwd)"
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

command -v gh >/dev/null 2>&1 || die "GitHub CLI (gh) not found"
gh auth status >/dev/null 2>&1 || die "gh is not signed in: gh auth login"

REPO=""
RESET=0
for arg in "$@"; do
  case "$arg" in
    --reset) RESET=1 ;;
    -*) die "unknown option $arg" ;;
    *) REPO="$arg" ;;
  esac
done
[ -n "$REPO" ] || REPO="$(gh api user --jq .login)/ledger-sandbox"

tmp="$(mktemp -d)"
trap 'rm -rf -- "$tmp"' EXIT
# Copy the template without local build/test leftovers.
(cd "$SRC" && tar --exclude=.venv --exclude=.pytest_cache --exclude=__pycache__ -cf - .) | (cd "$tmp" && tar -xf -)
cd "$tmp"
git init -q -b main
git add -A
git -c user.name="${GIT_AUTHOR_NAME:-$(git config user.name || echo ledger)}" \
    -c user.email="${GIT_AUTHOR_EMAIL:-$(git config user.email || echo ledger@example.invalid)}" \
    commit -q -m "Initial import of ledger 0.3.0"

if gh repo view "$REPO" >/dev/null 2>&1; then
  [ "$RESET" = 1 ] || die "$REPO already exists. Use --reset to restore main to the original code."
  printf 'This force-pushes the original code to %s main, discarding its history.\n' "$REPO"
  printf 'Open PRs and other branches are kept. Type the repo name to confirm: '
  read -r answer
  [ "$answer" = "$REPO" ] || die "not confirmed"
  git remote add origin "https://github.com/$REPO.git"
  git push -q --force origin main
  echo "Reset $REPO main to the original code."
else
  [ "$RESET" = 0 ] || die "$REPO does not exist yet; run without --reset first"
  gh repo create "$REPO" --private --source . --remote origin --push \
    --description "Sandbox app for evaluating AI coding agents (see boydj/harness)"
  echo "Created https://github.com/$REPO"
fi

case "$REPO" in
  boydj/ledger-sandbox) ;;
  *) echo "Note: add $REPO under write_repos in agents/dev/config.yaml and agents/dev-codex/config.yaml, then reinstall the agents." ;;
esac
