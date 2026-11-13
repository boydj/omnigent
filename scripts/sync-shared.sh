#!/usr/bin/env bash
# Copy shared/ into each agent directory. Edit files in shared/, then run this.
#
#   ./scripts/sync-shared.sh           copy (prints what changed)
#   ./scripts/sync-shared.sh --check   exit 1 if any copy differs (doctor.sh uses this)
#
# Why copies, not symlinks: Omnigent only reads an `instructions:` file that
# resolves inside the agent's own directory. A symlink pointing into shared/
# is treated as literal text instead, so the agent's prompt would silently
# become the string "instructions.md".
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CHECK=0
[ "${1:-}" = "--check" ] && CHECK=1

# source (under shared/)        destination (under agents/)
MAP="
mcp/github.yaml        dev/tools/mcp/github.yaml
mcp/jira.yaml          dev/tools/mcp/jira.yaml
prompts/engineer.md    dev/instructions.md
prompts/reviewer.md    dev/agents/reviewer/instructions.md
mcp/github.yaml        dev-codex/tools/mcp/github.yaml
mcp/jira.yaml          dev-codex/tools/mcp/jira.yaml
prompts/engineer.md    dev-codex/instructions.md
prompts/reviewer.md    dev-codex/agents/reviewer/instructions.md
"

stale=0
while read -r src dst; do
  [ -n "$src" ] || continue
  from="$REPO_DIR/shared/$src"
  to="$REPO_DIR/agents/$dst"
  if [ -f "$to" ] && [ ! -L "$to" ] && cmp -s "$from" "$to"; then
    continue
  fi
  if [ "$CHECK" = 1 ]; then
    echo "out of date: agents/$dst (from shared/$src)"
    stale=1
  else
    mkdir -p "$(dirname "$to")"
    rm -f "$to"
    cp "$from" "$to"
    echo "updated agents/$dst"
  fi
done <<EOF
$MAP
EOF

if [ "$CHECK" = 1 ] && [ "$stale" = 1 ]; then
  echo "Run ./scripts/sync-shared.sh, then reinstall: omnigent agent add agents/<name>" >&2
  exit 1
fi
