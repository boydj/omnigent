"""Validate the agents in agents/ with Omnigent's own parser.

Run with Omnigent's interpreter (doctor.sh does this):
    "$(dirname "$(readlink -f "$(command -v omnigent)")")/python" scripts/validate-agents.py

Beyond "does it parse", this catches two mistakes Omnigent accepts silently:
  * a top-level `policies:` block in config.yaml (ignored; must be
    `guardrails.policies`), and
  * an `instructions:` file that can't be read (falls back to using the
    file NAME as the prompt).
It also checks that every agent's guardrails block is identical to dev's.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml
from omnigent.spec.parser import parse

REPO = Path(__file__).resolve().parent.parent
AGENTS = REPO / "agents"
EXPECTED_MCP = {"github", "jira"}

failures: list[str] = []


def check(cond: bool, message: str) -> None:
    if not cond:
        failures.append(message)


def check_spec(directory: Path, label: str, *, top_level: bool) -> None:
    before = len(failures)
    raw = yaml.safe_load((directory / "config.yaml").read_text(encoding="utf-8"))
    check("policies" not in raw, f"{label}: top-level `policies:` is ignored; use `guardrails.policies`")
    spec = parse(directory, expand_env=False)

    raw_instructions = raw.get("instructions")
    if isinstance(raw_instructions, str) and "\n" not in raw_instructions:
        check(
            spec.instructions != raw_instructions,
            f"{label}: instructions file {raw_instructions!r} was not read (missing, or a symlink "
            "leaving the agent dir); the prompt would be the literal file name",
        )
    check(bool(spec.instructions) and len(spec.instructions) > 200, f"{label}: instructions look empty")
    check(bool(spec.guardrails.policies), f"{label}: no guardrail policies parsed")

    if top_level:
        names = {m.name for m in spec.mcp_servers}
        check(names == EXPECTED_MCP, f"{label}: MCP servers {sorted(names)} != {sorted(EXPECTED_MCP)}")
        for name in spec.tools.agents:
            check((directory / "agents" / name / "config.yaml").is_file(), f"{label}: sub-agent {name!r} missing")
    if len(failures) == before:
        harness = spec.executor.config.get("harness")
        print(f"  ok  {label}: harness={harness}, mcp={[m.name for m in spec.mcp_servers]}, "
              f"policies={[p.name for p in spec.guardrails.policies]}")


def main() -> int:
    agent_dirs = sorted(p for p in AGENTS.iterdir() if (p / "config.yaml").is_file())
    for directory in agent_dirs:
        check_spec(directory, directory.name, top_level=True)
        for sub in sorted((directory / "agents").glob("*/config.yaml")):
            check_spec(sub.parent, f"{directory.name}/{sub.parent.name}", top_level=False)

    reference = yaml.safe_load((AGENTS / "dev" / "config.yaml").read_text())["guardrails"]
    for directory in agent_dirs:
        other = yaml.safe_load((directory / "config.yaml").read_text()).get("guardrails")
        check(other == reference, f"{directory.name}: guardrails differ from agents/dev/config.yaml")

    for failure in failures:
        print(f"  FAIL {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
