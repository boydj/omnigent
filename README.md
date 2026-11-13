# harness

My AI-assisted development setup, as code: [Omnigent](https://omnigent.ai)
driving Claude Code, with **GitHub** and **Jira Cloud** MCP servers running
locally. Clone this repo, run one script, add two tokens, and the same setup
exists on any macOS or Linux machine. It's built for testing at home first
and evaluating at work after.

## What you get

- **Omnigent 0.21.0**, the open-source meta-harness from omnigent-ai. Its
  sessions follow you across terminal, browser, phone and the macOS app. It
  lets you swap Claude Code, Codex and other harnesses, and it has policies
  (guardrails) and Automations.
- **A custom agent, `dev`** ([agents/dev/](agents/dev/config.yaml)): Claude
  Code (native TUI) with both MCP servers attached, a ticket-to-PR workflow
  prompt, and guardrails. It appears in Omnigent's new-session agent picker.
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
agents/dev/                 the Omnigent agent: config.yaml + tools/mcp/{github,jira}.yaml
scripts/doctor.sh           verifies versions, secrets, MCP handshakes and live API auth
scripts/mcp-probe.py        stdlib-only MCP client used by doctor.sh
```

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

**5. Choose the model credential** Omnigent uses (Claude subscription, API
key, or gateway):

```bash
omnigent setup
```

**6. Verify:**

```bash
./scripts/doctor.sh
```

Every line should say PASS. `--names` also lists each server's tools.

## Use it

- **Browser / desktop app:** `omnigent start`, open the printed URL (default
  `http://localhost:6767`), choose **New Chat**, pick your machine, a repo
  folder as the workspace, and the **dev** agent.
- **Terminal:** from inside a repo,

  ```bash
  omnigent run ~/path/to/harness/agents/dev
  ```

  The session opens in the terminal and the browser at the same time.

Then ask it things like *"Pick up PROJ-123"*, *"What's in the current sprint
on board X?"*, or *"Open a PR for this branch and link it on PROJ-123"*.

### Replacing Vibe Kanban

Omnigent has no kanban board of its own. In this setup **the Jira board is
the kanban**, and Omnigent provides the agent orchestration around it:

| Vibe Kanban | Here |
|---|---|
| Cards on a board | Jira issues on your Jira board (`jira_agile` tools read boards and sprints) |
| Start an agent on a card | Tell `dev` "pick up PROJ-123". It reads the issue, branches `PROJ-123-...`, implements, and opens a PR |
| Parallel agents in worktrees | Several Omnigent sessions side by side. The bundled **Polly** orchestrator (`omnigent run examples/polly/` from a clone of the Omnigent repo) splits work across agents in separate git worktrees with cross-vendor review |
| Review the diff | The PR on GitHub. Omnigent can also share a live session with a teammate |
| Cards trigger work automatically | Omnigent **Automations** → *Jira tickets* template: start a session for each new ticket matching a JQL-style filter, or on "assignee changed to me". It is set up in the web UI (see below) |

## How it fits together

```
Omnigent session (web UI / terminal / phone)
  └─ dev agent  (agents/dev/config.yaml, harness: claude-native)
       ├─ Claude Code TUI (sandboxed: bwrap on Linux, seatbelt on macOS)
       └─ Omnigent runner spawns MCP servers from tools/mcp/*.yaml
            ├─ mcp-github → harness-secret → github-mcp-server stdio
            └─ mcp-jira   → harness-secret → mcp-atlassian (Jira only)
```

### Design decisions

- **No `${TOKEN}` in YAML.** `omnigent run <dir>` and `omnigent agent add
  <dir>` resolve `${VAR}` from your shell *into* the agent bundle they
  upload, and the server stores that bundle. A token referenced from YAML
  would end up in `~/.omnigent`. The wrappers fetch the token at launch
  instead, so the YAML and Omnigent's database never see it.
- **MCP servers belong to the Omnigent agent, not a `.mcp.json`.** Omnigent's
  runner starts them and relays their tools into the harness, so they work
  with any harness (`--harness codex-native`, etc.). They also run outside
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
- **Edit the agent:** change `agents/dev/`, then reinstall it with
  `omnigent agent add agents/dev` (an unchanged reinstall is a no-op).
  Running native sessions keep their old configuration until relaunched.
- **Allow writes to another repo:** add it under `write_repos` in
  `agents/dev/config.yaml` and reinstall.
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
