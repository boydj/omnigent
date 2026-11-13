# harness

My AI-assisted development setup, as code: [Omnigent](https://omnigent.ai)
driving Claude Code and Codex (both on their subscriptions), with **GitHub**
and **Jira Cloud** MCP servers running locally. Clone this repo, run one script, add two tokens, and the same setup
exists on any macOS or Linux machine. It's built for testing at home first
and evaluating at work after.

## What you get

- **Omnigent 0.21.0**, the open-source meta-harness from omnigent-ai. Its
  sessions follow you across terminal, browser, phone and the macOS app. It
  lets you swap Claude Code, Codex and other harnesses, and it has policies
  (guardrails) and Automations.
- **Two agents** in Omnigent's new-session picker. Both have both MCP
  servers, the same ticket-to-PR workflow, and the same guardrails. Each has
  a **cross-vendor reviewer** sub-agent that checks the diff before a PR is
  opened:

  | Agent | Implements | Reviews |
  |---|---|---|
  | [`dev`](agents/dev/config.yaml) | Claude Code (Claude subscription) | Codex |
  | [`dev-codex`](agents/dev-codex/config.yaml) | Codex (ChatGPT/Codex subscription) | Claude Code |

  Running the same ticket on each is a direct way to compare the two.
- **Codex CLI 0.167.2**, pinned. Claude Code updates itself, so it is not
  pinned; `doctor.sh` checks the minimum version Omnigent needs.
- **GitHub MCP**: the official
  [github/github-mcp-server](https://github.com/github/github-mcp-server)
  v2.1.0, run as a local binary verified by checksum.
- **Jira MCP**: [sooperset/mcp-atlassian](https://github.com/sooperset/mcp-atlassian)
  0.24.3, local, with Jira tools only (no Confluence).
- **No secrets in files.** Tokens live in the OS keychain and are fetched
  only when a server starts.

```
versions.lock               pinned versions + SHA-256 checksums (the source of truth)
bootstrap.sh                idempotent installer: run on a new machine or after a version bump
Brewfile                    macOS prerequisites
config/harness.env.example  non-secret settings template, copied to ~/.config/harness/harness.env
bin/harness-secret          store/fetch tokens (Keychain / libsecret / 0600 files / any command)
bin/mcp-github              launches github-mcp-server with token + settings
bin/mcp-jira                launches mcp-atlassian (Jira only) with token + settings
shared/mcp/*.yaml           GitHub + Jira MCP definitions  ─┐ source of truth: edit here,
shared/prompts/*.md         engineer + reviewer prompts     ─┘ then run sync-shared.sh
agents/dev/                 Claude implements: config.yaml, agents/reviewer/ (Codex)
agents/dev-codex/           Codex implements:  config.yaml, agents/reviewer/ (Claude)
scripts/sync-shared.sh      copies shared/ into each agent dir (--check to verify)
scripts/validate-agents.py  parses every agent with Omnigent's own parser
scripts/doctor.sh           verifies versions, sign-ins, secrets, MCP handshakes, agents
scripts/mcp-probe.py        stdlib-only MCP client used by doctor.sh
```

The files under `agents/*/tools/mcp/` and `agents/*/instructions.md` are
copies, not symlinks. Omnigent only reads an `instructions:` file that lives
inside the agent's own directory. A symlink into `shared/` is silently
treated as the literal text "instructions.md".

## Set up a machine

**1. Prerequisites.** On macOS: `brew bundle --file=Brewfile`. On Linux:
`uv`, `git`, Node.js 22+, `tmux`, `curl` and `bubblewrap` (Omnigent's native
terminals are sandboxed with `bwrap` on Linux). Install
[Claude Code](https://docs.anthropic.com/en/docs/claude-code) and sign in
once with `claude`.

**2. Install everything at the pinned versions:**

```bash
./bootstrap.sh
```

**3. Fill in your settings.** Edit `~/.config/harness/harness.env`: set
`JIRA_URL` (e.g. `https://yoursite.atlassian.net`) and `JIRA_USERNAME` (your
Atlassian account email). The other values are documented in the file.

**4. Store the two tokens** (input is hidden):

```bash
harness-secret set GITHUB_PERSONAL_ACCESS_TOKEN
```

```bash
harness-secret set JIRA_API_TOKEN
```

- **GitHub**: create a
  [fine-grained personal access token](https://github.com/settings/personal-access-tokens/new).
  Set Repository access to *Only select repositories* (the repos you test
  on). Grant these permissions: *Contents*, *Pull requests* and *Issues*
  Read and write; *Actions*, *Commit statuses* and *Metadata* Read-only. At
  work, your org may require admin approval for fine-grained tokens.
- **Jira**: create a token at
  [id.atlassian.com → Security → API tokens](https://id.atlassian.com/manage-profile/security/api-tokens).
  Use plain *Create API token*. mcp-atlassian authenticates with email plus
  token against your site URL, and scoped tokens expect a different API
  gateway.

**5. Sign in to both subscriptions**, then let Omnigent pick them up as the
defaults for Claude and Codex:

```bash
claude auth login
```

```bash
codex login
```

```bash
omnigent setup
```

In `omnigent setup`, choose the **Subscription** credential for both Claude
and Codex. Defaults are per harness, so they coexist.

**6. Verify:**

```bash
./scripts/doctor.sh
```

Every line should say PASS. `--names` also lists each server's tools.

## Use it

- **Browser / desktop app:** `omnigent start`, open the printed URL (default
  `http://localhost:6767`), choose **New Chat**, pick your machine, a repo
  folder as the workspace, and the **dev** or **dev-codex** agent.
- **Terminal:** from inside a repo,

  ```bash
  omnigent run ~/path/to/harness/agents/dev
  ```

  (or `agents/dev-codex`). The session opens in the terminal and the browser
  at the same time.

Then ask it things like *"Pick up PROJ-123"*, *"What's in the current sprint
on board X?"*, or *"Open a PR for this branch and link it on PROJ-123"*.

**The review step.** Before opening a PR, the implementer saves a diff
snapshot to `omnigent-review/` in the repo. That folder is hidden from git
via `.git/info/exclude`, so it is never committed. The implementer sends the
path to its `reviewer` sub-agent, which appears as its own session in the
UI. It then fixes blocking issues and summarizes the review in the PR body.
You can also just ask: *"get a review of the current branch"*. The reviewer
is told never to edit. The Codex reviewer keeps Codex's sandbox and approval
prompts on (`yolo: false`; Omnigent otherwise bypasses both for headless
Codex sub-agents). The Claude reviewer runs in Claude's default permission
mode, so anything beyond reading asks you first. Neither reviewer can write
to GitHub (`write_repos: []`).

### Replacing Vibe Kanban

Omnigent has no kanban board of its own. In this setup **the Jira board is
the kanban**, and Omnigent provides the agent orchestration around it:

| Vibe Kanban | Here |
|---|---|
| Cards on a board | Jira issues on your Jira board (`jira_agile` tools read boards and sprints) |
| Start an agent on a card | Tell `dev` "pick up PROJ-123". It reads the issue, branches `PROJ-123-...`, implements, and opens a PR |
| Parallel agents in worktrees | Several Omnigent sessions side by side. The bundled **Polly** orchestrator (`omnigent run examples/polly/` from a clone of the Omnigent repo) splits work across agents in separate git worktrees with cross-vendor review |
| Review the diff | A cross-vendor AI review before the PR exists, then yours on GitHub. Omnigent can also share a live session with a teammate |
| Cards trigger work automatically | Omnigent **Automations** → *Jira tickets* template: start a session for each new ticket matching a JQL-style filter, or on "assignee changed to me". It is set up in the web UI (see below) |

## How it fits together

```
Omnigent session (web UI / terminal / phone)
  └─ dev agent  (harness: claude-native; dev-codex is the same with codex-native)
       ├─ Claude Code TUI (sandboxed: bwrap on Linux, seatbelt on macOS)
       ├─ Omnigent runner spawns MCP servers from tools/mcp/*.yaml
       │    ├─ mcp-github → harness-secret → github-mcp-server stdio
       │    └─ mcp-jira   → harness-secret → mcp-atlassian (Jira only)
       └─ reviewer sub-agent (harness: codex-native), via sys_session_send
```

### Design decisions

- **No `${TOKEN}` in YAML.** `omnigent run <dir>` and `omnigent agent add
  <dir>` resolve `${VAR}` from your shell *into* the agent bundle they
  upload, and the server stores that bundle. A token referenced from YAML
  would end up in `~/.omnigent`. The wrappers fetch the token at launch
  instead, so the YAML and Omnigent's database never see it.
- **MCP servers belong to the Omnigent agent, not a `.mcp.json`.** Omnigent's
  runner starts them and relays their tools into the harness, so Claude Code
  and Codex get the same servers from the same files. Native sessions *also*
  load servers from your own `~/.claude.json` and `~/.codex/config.toml`. Don't
  add GitHub or Jira there too, or each session sees them twice. They also run outside
  Claude's terminal sandbox, which on Linux binds only system directories
  and masks dotfiles. Docker or keychain access from inside that sandbox
  would be fragile.
- **Local binaries, pinned.** No Docker daemon is needed. Every version is
  in `versions.lock`, and the GitHub binary is checked against its release
  SHA-256.
- **Guardrails** (`guardrails.policies` in `config.yaml`): GitHub writes,
  through both MCP tools and `git`/`gh` shell commands, are allowed only on
  the repos listed under `write_repos`. Deletes, force pushes and tag pushes
  are denied, and spend is capped per session. The GitHub server also drops
  `merge_pull_request`, `delete_file`, `create_repository` and
  `fork_repository` (`GITHUB_EXCLUDE_TOOLS`).
- **Telemetry off.** `bootstrap.sh` writes `telemetry: false` to
  `~/.omnigent/config.yaml`.

## Change things

- **Bump a version:** edit `versions.lock` (for github-mcp-server, copy the
  new checksums from the release's `*_checksums.txt`), then run
  `./bootstrap.sh` and `./scripts/doctor.sh`.
- **Edit a prompt or MCP server:** edit it in `shared/`, run
  `./scripts/sync-shared.sh`, then reinstall the agents (`./bootstrap.sh`
  does all of them; an unchanged reinstall is a no-op). Running native
  sessions keep their old configuration until relaunched.
- **Edit an agent's config:** change `agents/<name>/config.yaml` and
  reinstall with `omnigent agent add agents/<name>`. `doctor.sh` runs
  `validate-agents.py`, which catches the two mistakes Omnigent accepts
  silently: a top-level `policies:` block, and an unreadable `instructions:`
  file.
- **Allow writes to another repo:** add it under `write_repos` in *both*
  `agents/dev/config.yaml` and `agents/dev-codex/config.yaml` (the validator
  fails if their guardrails differ), then reinstall.
- **Bump Codex:** change `CODEX_VERSION` in `versions.lock` and run
  `./bootstrap.sh`.
- **Tighten for work:** in `~/.config/harness/harness.env`, start with
  `GITHUB_READ_ONLY=1` and `JIRA_READ_ONLY=true`, and set
  `JIRA_PROJECTS_FILTER` to your team's project keys. Read-only cuts GitHub
  to 30 tools and Jira to 21. `jira_delete_issue` is otherwise exposed, since
  mcp-atlassian only offers an allowlist (`ENABLED_TOOLS`), not an exclude
  list.
- **Use a password manager instead of the keychain:** set
  `<NAME>_COMMAND` in `harness.env`, e.g.
  `JIRA_API_TOKEN_COMMAND="op read op://Work/Jira/credential"`, or
  `GITHUB_PERSONAL_ACCESS_TOKEN_COMMAND="gh auth token"` for a quick home test.
- **Automations** (Jira-triggered sessions) live in Omnigent's database and
  are created in the web UI under *Automations* or via
  `POST /v1/scheduled-tasks`. They are not in this repo yet. Record any you
  rely on here.

## Evaluating for work: things to check

- Does Atlassian admin policy allow personal API tokens for your site? The
  official [Atlassian Rovo MCP server](https://developer.atlassian.com/cloud/rovo-mcp/)
  (remote, OAuth, admin-controlled) may be what IT prefers over a local
  server. It can be added as a `transport: http` file in
  `agents/dev/tools/mcp/`.
- Does GitHub org policy allow fine-grained PATs or require approval? The
  remote GitHub MCP (`https://api.githubcopilot.com/mcp/`) with OAuth is the
  managed alternative.
- Omnigent is **alpha**. Check its multi-user auth (OIDC), where session
  data lives, and the [policy docs](https://github.com/omnigent-ai/omnigent/blob/main/docs/POLICIES.md)
  against your security requirements.
