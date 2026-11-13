#!/usr/bin/env bash
# Recreate this harness on a machine (macOS or Linux). Safe to re-run.
#
#   ./bootstrap.sh               install/upgrade everything to versions.lock
#   ./bootstrap.sh --no-agent    skip registering the agent with Omnigent
#
# What it does:
#   1. checks prerequisites (uv, git, node/npm, tmux; bwrap on Linux; claude)
#   2. installs omnigent and mcp-atlassian at pinned versions (uv tool), and
#      the Codex CLI at its pinned version (npm -g)
#   3. downloads github-mcp-server at the pinned version, verifies SHA-256
#   4. links bin/* (harness-secret, mcp-github, mcp-jira) into ~/.local/bin
#   5. creates ~/.config/harness/harness.env from the example (never overwrites)
#   6. turns Omnigent telemetry off in ~/.omnigent/config.yaml
#   7. installs agents/dev and agents/dev-codex into Omnigent's session picker
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="${HARNESS_BIN_DIR:-$HOME/.local/bin}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/harness"
REGISTER_AGENT=1
[ "${1:-}" = "--no-agent" ] && REGISTER_AGENT=0

# shellcheck source=versions.lock
. "$REPO_DIR/versions.lock"

say()  { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33mwarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

OS="$(uname -s)"     # Darwin | Linux
ARCH="$(uname -m)"   # arm64 | aarch64 | x86_64
case "$ARCH" in aarch64) ARCH=arm64 ;; esac
case "$OS" in Darwin|Linux) ;; *) die "unsupported OS: $OS (use macOS, Linux or WSL)" ;; esac

# --- 1. prerequisites ---------------------------------------------------------
say "Checking prerequisites"
# (Plain strings, not arrays: macOS ships bash 3.2, where an empty array
# under `set -u` aborts the script.)
missing=""
for tool in uv git node npm tmux curl tar; do have "$tool" || missing="$missing $tool"; done
if [ "$OS" = Linux ] && ! have bwrap; then missing="$missing bubblewrap(bwrap)"; fi
if [ -n "$missing" ]; then
  if [ "$OS" = Darwin ]; then
    die "missing:$missing. Install with: brew bundle --file=$REPO_DIR/Brewfile"
  else
    die "missing:$missing. e.g. apt install tmux bubblewrap git curl; uv: https://docs.astral.sh/uv/"
  fi
fi
node_major="$(node -p 'process.versions.node.split(".")[0]')"
[ "$node_major" -ge 22 ] || die "Node.js 22+ required (found $(node --version))"
have claude || warn "Claude Code CLI not found. Install it and sign in (claude), or the dev agent cannot start."
have gh || warn "GitHub CLI (gh) not found. Optional, but agents often use it for PRs."

case ":$PATH:" in *":$BIN_DIR:"*) ;; *) warn "$BIN_DIR is not on PATH; add it to your shell profile." ;; esac
mkdir -p "$BIN_DIR"

# --- 2. Python tools at pinned versions --------------------------------------
install_uv_tool() {  # name version
  local current
  current="$(uv tool list 2>/dev/null | awk -v n="$1" '$1==n {print $2}' | sed 's/^v//')"
  if [ "$current" = "$2" ]; then
    say "$1 $2 already installed"
  else
    say "Installing $1 $2 (was: ${current:-none})"
    uv tool install --force --python 3.12 "$1==$2"
  fi
}
install_uv_tool omnigent "$OMNIGENT_VERSION"
install_uv_tool mcp-atlassian "$MCP_ATLASSIAN_VERSION"

codex_installed="$(codex --version 2>/dev/null | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)"
if [ "$codex_installed" = "$CODEX_VERSION" ]; then
  say "Codex CLI $CODEX_VERSION already installed"
else
  say "Installing Codex CLI $CODEX_VERSION (was: ${codex_installed:-none})"
  if ! npm install -g "@openai/codex@$CODEX_VERSION"; then
    warn "npm could not install globally (prefix: $(npm config get prefix)). Either fix npm's"
    warn "prefix (npm config set prefix ~/.local) and re-run, or install it yourself:"
    warn "  npm install -g @openai/codex@$CODEX_VERSION"
  fi
fi

# --- 3. github-mcp-server binary ---------------------------------------------
gh_mcp_installed="$("$BIN_DIR/github-mcp-server" --version 2>/dev/null | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)"
if [ "$gh_mcp_installed" = "$GITHUB_MCP_VERSION" ]; then
  say "github-mcp-server $GITHUB_MCP_VERSION already installed"
else
  asset="github-mcp-server_${OS}_${ARCH}.tar.gz"
  sum_var="GITHUB_MCP_SHA256_${OS}_${ARCH}"
  expected="${!sum_var:-}"
  [ -n "$expected" ] || die "no pinned checksum for $OS/$ARCH in versions.lock"
  say "Installing github-mcp-server $GITHUB_MCP_VERSION ($OS/$ARCH)"
  tmp="$(mktemp -d)"
  trap 'rm -rf -- "$tmp"' EXIT
  curl -fsSL -o "$tmp/$asset" \
    "https://github.com/github/github-mcp-server/releases/download/v${GITHUB_MCP_VERSION}/${asset}"
  if have sha256sum; then actual="$(sha256sum "$tmp/$asset" | awk '{print $1}')"
  else actual="$(shasum -a 256 "$tmp/$asset" | awk '{print $1}')"; fi
  [ "$actual" = "$expected" ] || die "checksum mismatch for $asset: got $actual, expected $expected"
  tar -xzf "$tmp/$asset" -C "$tmp" github-mcp-server
  install -m 0755 "$tmp/github-mcp-server" "$BIN_DIR/github-mcp-server"
fi

# --- 4. wrapper scripts ------------------------------------------------------
say "Linking wrapper scripts into $BIN_DIR"
for f in "$REPO_DIR"/bin/*; do
  chmod +x "$f"
  ln -sfn "$f" "$BIN_DIR/$(basename "$f")"
done

# --- 5. local settings -------------------------------------------------------
mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/harness.env" ]; then
  cp "$REPO_DIR/config/harness.env.example" "$CONFIG_DIR/harness.env"
  say "Created $CONFIG_DIR/harness.env: edit JIRA_URL and JIRA_USERNAME"
else
  say "Keeping existing $CONFIG_DIR/harness.env"
fi

# --- 6. Omnigent telemetry off -----------------------------------------------
omni_cfg="${OMNIGENT_CONFIG_HOME:-$HOME/.omnigent}/config.yaml"
mkdir -p "$(dirname "$omni_cfg")"
if ! grep -Eq '^telemetry:' "$omni_cfg" 2>/dev/null; then
  printf '\n# Added by harness bootstrap.sh\ntelemetry: false\n' >> "$omni_cfg"
  say "Disabled Omnigent telemetry in $omni_cfg"
fi

# --- 7. register the agent ---------------------------------------------------
if [ "$REGISTER_AGENT" = 1 ]; then
  "$REPO_DIR/scripts/sync-shared.sh" --check \
    || die "agents/ is out of sync with shared/. Run ./scripts/sync-shared.sh first."
  for agent in "$REPO_DIR"/agents/*/; do
    agent="${agent%/}"
    say "Installing agent $(basename "$agent") into Omnigent (starts the local server if needed)"
    if ! omnigent agent add "$agent"; then
      warn "omnigent agent add failed. Run it later: omnigent agent add $agent"
    fi
  done
fi

cat <<EOF

Done. Next steps (first time on this machine):
  1. Edit $CONFIG_DIR/harness.env (Jira site URL and email).
  2. harness-secret set GITHUB_PERSONAL_ACCESS_TOKEN
  3. harness-secret set JIRA_API_TOKEN
  4. Sign in to both subscriptions:  claude auth login  and  codex login
     then pick defaults with:        omnigent setup
  5. $REPO_DIR/scripts/doctor.sh
EOF
