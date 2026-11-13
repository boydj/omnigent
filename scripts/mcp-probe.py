#!/usr/bin/env python3
"""Start a stdio MCP server, run the MCP handshake, and list its tools.

Usage: mcp-probe.py [--timeout SECONDS] [--names] -- COMMAND [ARGS...]

Exits 0 and prints the tool count when the server answers tools/list,
non-zero otherwise (with the server's stderr tail). Standard library only.
"""

from __future__ import annotations

import argparse
import json
import queue
import subprocess
import sys
import threading
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--names", action="store_true", help="print tool names")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    cmd = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not cmd:
        parser.error("missing server command")

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    lines: queue.Queue[str] = queue.Queue()
    stderr_tail: list[str] = []

    def pump_stdout() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.put(line)

    def pump_stderr() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            stderr_tail.append(line.rstrip())
            del stderr_tail[:-20]

    threading.Thread(target=pump_stdout, daemon=True).start()
    threading.Thread(target=pump_stderr, daemon=True).start()

    def send(msg: dict) -> None:
        assert proc.stdin is not None
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()

    deadline = time.monotonic() + args.timeout

    def wait_for(msg_id: int) -> dict:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"no response to request {msg_id}")
            if proc.poll() is not None and lines.empty():
                raise RuntimeError(f"server exited with code {proc.returncode}")
            try:
                line = lines.get(timeout=min(remaining, 0.5))
            except queue.Empty:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                raise RuntimeError(f"non-JSON on stdout (breaks MCP): {line.strip()[:200]}")
            if msg.get("id") == msg_id:
                if "error" in msg:
                    raise RuntimeError(f"error response: {msg['error']}")
                return msg["result"]

    try:
        send({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "harness-doctor", "version": "1"},
            },
        })
        init = wait_for(1)
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools: list[dict] = []
        cursor = None
        next_id = 2
        while True:
            params = {"cursor": cursor} if cursor else {}
            send({"jsonrpc": "2.0", "id": next_id, "method": "tools/list", "params": params})
            result = wait_for(next_id)
            tools.extend(result.get("tools", []))
            cursor = result.get("nextCursor")
            next_id += 1
            if not cursor:
                break
        server = init.get("serverInfo", {})
        print(f"{server.get('name', '?')} {server.get('version', '')}: {len(tools)} tools".strip())
        if args.names:
            for tool in sorted(t["name"] for t in tools):
                print(f"  {tool}")
        return 0 if tools else 1
    except Exception as exc:  # noqa: BLE001 - report any failure to the user
        print(f"FAILED: {exc}", file=sys.stderr)
        time.sleep(0.2)
        for line in stderr_tail:
            print(f"  | {line}", file=sys.stderr)
        return 1
    finally:
        try:
            proc.stdin.close()  # type: ignore[union-attr]
        except OSError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
