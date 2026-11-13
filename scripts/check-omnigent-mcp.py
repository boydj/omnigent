"""Start an agent's MCP servers exactly the way Omnigent's runner does, and list their tools.

Uses Omnigent's own spec parser and stdio MCP client, so the servers get the
same minimal environment (HOME, PATH, USER, LOGNAME, SHELL, TERM) they get in
a real session. doctor.sh runs this under `env -i` with a bare system PATH,
which is what the desktop app or a launchd/systemd service gives Omnigent.

Run with Omnigent's interpreter:
    "$(dirname "$(readlink -f "$(command -v omnigent)")")/python" \\
        scripts/check-omnigent-mcp.py agents/dev

Prints one `RESULT <server> ok <n>` or `RESULT <server> FAIL <reason>` line
per server; exits 1 if any failed.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from omnigent.spec.parser import parse
from omnigent.tools.mcp import McpServerConnection


async def check(agent_dir: Path) -> int:
    spec = parse(agent_dir, expand_env=True)
    failed = 0
    for server in spec.mcp_servers:
        connection = McpServerConnection(server, cwd=Path.cwd())
        try:
            tools = await asyncio.wait_for(connection.connect(), timeout=90)
            print(f"RESULT {server.name} ok {len(tools)}", flush=True)
        except BaseException as exc:  # noqa: BLE001 - report every failure
            failed += 1
            reason = " ".join(f"{type(exc).__name__}: {exc}".split())[:300]
            print(f"RESULT {server.name} FAIL {reason}", flush=True)
        finally:
            try:
                await connection.close()
            except BaseException:  # noqa: BLE001
                pass
    return 1 if failed else 0


def main() -> int:
    logging.disable(logging.CRITICAL)
    agent_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "agents/dev")
    return asyncio.run(check(agent_dir))


if __name__ == "__main__":
    sys.exit(main())
