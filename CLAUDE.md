# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Infrastructure-as-code for an AI dev setup: [Omnigent](https://omnigent.ai) agents (`dev` = Claude implements / Codex reviews; `dev-codex` = the mirror image) with local GitHub and Jira MCP servers. There is no application build here except the `sandbox/ledger` test project. Most files are bash, YAML agent specs, and stdlib-only Python helpers. See README.md for user-facing setup.

## Commands

```bash
./bootstrap.sh                    # idempotent install at versions.lock pins; also (re)installs agents into Omnigent
./scripts/doctor.sh [--names]     # end-to-end PASS/FAIL checks (versions, auth, secrets, MCP handshakes, agent validity)
./scripts/sync-shared.sh          # copy shared/ -> agents/*/ (run after editing anything in shared/)
./scripts/sync-shared.sh --check  # exit 1 if copies are stale
omnigent agent add agents/<name>  # reinstall one agent after editing its config.yaml

# Validate agent specs with Omnigent's own parser (must use Omnigent's interpreter):
"$(dirname "$(readlink -f "$(command -v omnigent)")")/python" scripts/validate-agents.py

# Sandbox ledger app (Python 3.12, uv)
cd sandbox/ledger && uv run pytest -q
cd sandbox/ledger && uv run pytest tests/test_report.py::test_totals_by_category -q
```

## Architecture and invariants

- **`shared/` is the source of truth; `agents/*/instructions.md` and `agents/*/tools/mcp/*.yaml` are generated copies.** Never edit the copies — edit `shared/`, then run `sync-shared.sh`. They must be real files, not symlinks: Omnigent only reads an `instructions:` file inside the agent's own dir, and a symlink is silently treated as the literal string `"instructions.md"`. (Some comments in `agents/*/config.yaml` still say "symlink"; they are copies.)
- **Guardrails must be identical** in `agents/dev/config.yaml` and `agents/dev-codex/config.yaml`; `validate-agents.py` fails otherwise. Adding a writable repo means editing `write_repos` in both. Policies must live under `guardrails.policies` — a top-level `policies:` key is silently ignored by Omnigent.
- **No `${VAR}` or tokens in agent YAML.** `omnigent run`/`agent add` expand `${VAR}` into the bundle stored in Omnigent's DB. Instead, MCP YAML runs `/bin/sh -c 'exec "$HOME/.local/bin/mcp-<name>"'`, and the `bin/mcp-*` wrappers load `~/.config/harness/harness.env` and fetch tokens via `bin/harness-secret` (Keychain / libsecret / 0600 files / `<NAME>_COMMAND`) at launch.
- **MCP servers run with a minimal env and possibly bare system PATH** (only HOME, PATH, USER, LOGNAME, SHELL, TERM). Wrappers must not assume `~/.local/bin` is on PATH, and stdout is the MCP transport — log to stderr only. `doctor.sh` reproduces this via `env -i` + `scripts/check-omnigent-mcp.py`.
- **`versions.lock`** is sourced by both `bootstrap.sh` and `doctor.sh`; it holds all pinned versions and the github-mcp-server SHA-256 checksums. Claude Code is not pinned (only `CLAUDE_MIN_VERSION`).
- Shell scripts target macOS bash 3.2 as well as Linux (e.g. avoid empty arrays under `set -u`).
- `scripts/mcp-probe.py` is a stdlib-only MCP client; `validate-agents.py` and `check-omnigent-mcp.py` import `omnigent` and need Omnigent's Python.

## sandbox/

`sandbox/ledger` is a deliberately buggy Python CLI used to evaluate the agents, paired with a Jira backlog (`jira-seed.yaml`, loaded by `uv run sandbox/seed-jira.py --project LEDG [--dry-run]`) and published via `sandbox/create-repo.sh`. The bugs are intentional and map to Jira tickets — don't fix them unless asked; changes to the code should stay consistent with the tickets' reproduction steps.
