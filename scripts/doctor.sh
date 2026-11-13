#!/usr/bin/env bash
# Check that this machine matches versions.lock and that both MCP servers
# start, authenticate and list their tools through the same wrappers
# Omnigent uses. Prints PASS/FAIL per check; exits non-zero on any FAIL.
#
#   ./scripts/doctor.sh           run all checks
#   ./scripts/doctor.sh --names   also list every tool each server exposes
set -uo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/harness"
# shellcheck source=SCRIPTDIR/../versions.lock
. "$REPO_DIR/versions.lock"
# A plain string, not an array: macOS bash 3.2 aborts on an empty array
# under `set -u`.
NAMES=""
if [ "${1:-}" = "--names" ]; then NAMES="--names"; fi

fails=0
pass() { printf '  \033[32mPASS\033[0m %s\n' "$*"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$*"; fails=$((fails + 1)); }
info() { printf '  \033[2m%s\033[0m\n' "$*"; }
check_version() {  # label expected actual
  if [ "$2" = "$3" ]; then pass "$1 $3"; else fail "$1: expected $2, found ${3:-nothing} (run ./bootstrap.sh)"; fi
}

echo "Versions"
check_version omnigent "$OMNIGENT_VERSION" \
  "$(omnigent --version 2>/dev/null | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
check_version mcp-atlassian "$MCP_ATLASSIAN_VERSION" \
  "$(uv tool list 2>/dev/null | awk '$1=="mcp-atlassian" {print $2}' | sed 's/^v//')"
check_version github-mcp-server "$GITHUB_MCP_VERSION" \
  "$(github-mcp-server --version 2>/dev/null | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
for tool in harness-secret mcp-github mcp-jira; do
  if command -v "$tool" >/dev/null 2>&1; then pass "$tool on PATH"; else fail "$tool not on PATH"; fi
done
check_version codex "$CODEX_VERSION" \
  "$(codex --version 2>/dev/null | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
claude_version="$(claude --version 2>/dev/null | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
if [ -z "$claude_version" ]; then
  fail "Claude Code CLI (claude) not found"
elif [ "$(printf '%s\n%s\n' "$CLAUDE_MIN_VERSION" "$claude_version" | sort -V | head -1)" = "$CLAUDE_MIN_VERSION" ]; then
  pass "claude $claude_version (>= $CLAUDE_MIN_VERSION)"
else
  fail "claude $claude_version is older than $CLAUDE_MIN_VERSION: run claude update"
fi

echo "Subscriptions"
if claude auth status >/dev/null 2>&1; then pass "Claude Code signed in"
else fail "Claude Code not signed in: claude auth login"; fi
if codex login status >/dev/null 2>&1; then pass "Codex signed in ($(codex login status 2>&1 | head -1))"
else fail "Codex not signed in: codex login"; fi

echo "Settings and secrets (backend: $(harness-secret backend 2>/dev/null || echo '?'))"
if [ -f "$CONFIG_DIR/harness.env" ]; then pass "$CONFIG_DIR/harness.env exists"
else fail "$CONFIG_DIR/harness.env missing (run ./bootstrap.sh)"; fi
for name in GITHUB_PERSONAL_ACCESS_TOKEN JIRA_API_TOKEN; do
  if harness-secret get "$name" >/dev/null 2>&1; then pass "$name is set"
  else fail "$name missing: harness-secret set $name"; fi
done

echo "MCP servers (handshake + tools/list through the wrappers)"
for server in github jira; do
  # shellcheck disable=SC2086  # $NAMES is intentionally unquoted (empty or one flag)
  if out="$(python3 "$REPO_DIR/scripts/mcp-probe.py" $NAMES -- "mcp-$server" 2>&1)"; then
    pass "$server: ${out%%$'\n'*}"
    if [ -n "$NAMES" ]; then printf '%s\n' "$out" | tail -n +2; fi
  else
    fail "$server"
    printf '%s\n' "$out" | sed 's/^/       /'
  fi
done

echo "MCP servers as Omnigent starts them (minimal env, bare system PATH)"
# The runner gives stdio MCP servers only HOME, PATH, USER, LOGNAME, SHELL and
# TERM, and when the desktop app or a service started Omnigent, PATH lacks
# ~/.local/bin. Reproduce the worst case with Omnigent's own MCP client.
omni_python="$(dirname "$(readlink -f "$(command -v omnigent)")")/python"
omni_out="$(cd "$REPO_DIR" && env -i HOME="$HOME" USER="${USER:-$(id -un)}" LOGNAME="${LOGNAME:-$(id -un)}" \
  SHELL="${SHELL:-/bin/sh}" TERM=dumb PATH=/usr/bin:/bin:/usr/sbin:/sbin \
  "$omni_python" scripts/check-omnigent-mcp.py agents/dev 2>&1)"
if ! printf '%s\n' "$omni_out" | grep -q '^RESULT '; then
  fail "could not run the Omnigent MCP check"
  printf '%s\n' "$omni_out" | tail -5 | sed 's/^/       /'
fi
while read -r _ name state rest; do
  if [ "$state" = ok ]; then pass "$name: started by Omnigent's client, $rest tools"
  else fail "$name: Omnigent could not start it: $rest"; fi
done <<EOF
$(printf '%s\n' "$omni_out" | grep '^RESULT ')
EOF

echo "Live API checks (does the token actually work?)"
if token="$(harness-secret get GITHUB_PERSONAL_ACCESS_TOKEN 2>/dev/null)"; then
  login="$(curl -fsS -H "Authorization: Bearer $token" https://api.github.com/user 2>/dev/null \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["login"])' 2>/dev/null)"
  if [ -n "$login" ]; then pass "GitHub token works (user: $login)"; else fail "GitHub token rejected by api.github.com"; fi
fi
if [ -f "$CONFIG_DIR/harness.env" ] && token="$(harness-secret get JIRA_API_TOKEN 2>/dev/null)"; then
  # shellcheck disable=SC1091
  ( set -a; . "$CONFIG_DIR/harness.env"; set +a
    who="$(curl -fsS -u "$JIRA_USERNAME:$token" "$JIRA_URL/rest/api/3/myself" 2>/dev/null \
      | python3 -c 'import json,sys; print(json.load(sys.stdin)["displayName"])' 2>/dev/null)"
    if [ -n "$who" ]; then printf '  \033[32mPASS\033[0m Jira token works (%s)\n' "$who"
    else printf '  \033[31mFAIL\033[0m Jira rejected %s at %s\n' "$JIRA_USERNAME" "$JIRA_URL"; exit 1; fi
  ) || fails=$((fails + 1))
fi

echo "Agents"
if sync_out="$("$REPO_DIR/scripts/sync-shared.sh" --check 2>&1)"; then pass "agents/ copies match shared/"
else fail "agents/ out of sync with shared/: ./scripts/sync-shared.sh"; printf '%s\n' "$sync_out" | sed 's/^/       /'; fi
omni_python="$(dirname "$(readlink -f "$(command -v omnigent)")")/python"
if val_out="$("$omni_python" "$REPO_DIR/scripts/validate-agents.py" 2>&1)"; then pass "agent specs valid (Omnigent parser)"
else fail "agent specs invalid"; fi
printf '%s\n' "$val_out" | sed 's/^/   /'
agent_list="$(omnigent agent list 2>/dev/null)"
for agent_dir in "$REPO_DIR"/agents/*/; do
  agent="$(basename "$agent_dir")"
  if printf '%s\n' "$agent_list" | grep -Eq "(^|[[:space:]])${agent}([[:space:]]|$)"; then pass "$agent installed in Omnigent"
  else fail "$agent not installed: omnigent agent add $REPO_DIR/agents/$agent"; info "(needs the local server; 'omnigent start' launches it)"; fi
done

echo
if [ "$fails" -eq 0 ]; then echo "All checks passed."; else echo "$fails check(s) failed."; fi
exit $((fails > 0))
