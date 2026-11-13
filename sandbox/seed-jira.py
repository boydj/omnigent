#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml>=6"]
# ///
"""Create (or remove) the sandbox backlog from jira-seed.yaml in a Jira Cloud project.

    uv run sandbox/seed-jira.py --project LEDG              create what's missing
    uv run sandbox/seed-jira.py --project LEDG --dry-run    show the plan, no API calls
    uv run sandbox/seed-jira.py --project LEDG --delete     delete every seeded issue

Idempotent: each issue carries the labels `harness-seed` and `seed-<id>`, so a
re-run only creates what is missing (links and the sprint are re-checked).

Credentials come from the harness: JIRA_URL and JIRA_USERNAME from
~/.config/harness/harness.env, the token from `harness-secret get JIRA_API_TOKEN`.
Environment variables of the same names take precedence.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SEED_LABEL = "harness-seed"
TYPE_NAMES = {"story": "Story", "task": "Task", "bug": "Bug", "epic": "Epic"}


# ----------------------------------------------------------------- helpers
def die(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


def seed_label(seed_id: str) -> str:
    return f"seed-{seed_id.lower()}"


_INLINE = re.compile(r"`([^`]+)`|\*\*(.+?)\*\*|(?<!\w)_(.+?)_(?!\w)")


def _inline(text: str) -> list[dict]:
    """Text nodes for one line: `code`, **bold** and _italic_ become marks."""
    nodes: list[dict] = []
    pos = 0
    for match in _INLINE.finditer(text):
        if match.start() > pos:
            nodes.append({"type": "text", "text": text[pos : match.start()]})
        code, bold, italic = match.groups()
        mark = "code" if code is not None else "strong" if bold is not None else "em"
        nodes.append({"type": "text", "text": code or bold or italic, "marks": [{"type": mark}]})
        pos = match.end()
    if pos < len(text):
        nodes.append({"type": "text", "text": text[pos:]})
    return nodes


def _paragraph(text: str) -> dict:
    return {"type": "paragraph", "content": _inline(text)}


def markdown_to_adf(text: str) -> dict:
    """Convert the small Markdown subset used in jira-seed.yaml to Atlassian Document Format.

    Supports paragraphs (wrapped lines are joined), #-headings, "- " and "1. "
    lists (indented lines continue the item), ``` code blocks, --- rules, and
    inline `code`, **bold** and _italic_.
    """
    blocks: list[dict] = []
    paragraph: list[str] = []
    items: list[str] = []
    list_type = ""

    def flush() -> None:
        nonlocal list_type
        if paragraph:
            blocks.append(_paragraph(" ".join(paragraph)))
            paragraph.clear()
        if items:
            blocks.append({"type": list_type, "content": [
                {"type": "listItem", "content": [_paragraph(item)]} for item in items]})
            items.clear()
            list_type = ""

    lines = text.rstrip().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        bullet = re.match(r"^-\s+(.*)$", line)
        numbered = re.match(r"^\d+\.\s+(.*)$", line)
        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if stripped.startswith("```"):
            flush()
            code: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            block: dict = {"type": "codeBlock"}
            if code:
                block["content"] = [{"type": "text", "text": "\n".join(code)}]
            blocks.append(block)
        elif not stripped:
            flush()
        elif heading:
            flush()
            blocks.append({"type": "heading", "attrs": {"level": len(heading.group(1))},
                           "content": _inline(heading.group(2))})
        elif stripped == "---":
            flush()
            blocks.append({"type": "rule"})
        elif bullet or numbered:
            kind = "bulletList" if bullet else "orderedList"
            if paragraph or (items and list_type != kind):
                flush()
            list_type = kind
            items.append((bullet or numbered).group(1))
        elif items and line.startswith("  "):
            items[-1] += " " + stripped
        else:
            if items:
                flush()
            paragraph.append(stripped)
        i += 1
    flush()
    return {"type": "doc", "version": 1, "content": blocks}


def load_harness_settings() -> tuple[str, str, str]:
    env_file = Path(
        os.environ.get("HARNESS_ENV_FILE")
        or Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "harness" / "harness.env"
    )
    settings: dict[str, str] = {}
    if env_file.is_file():
        script = 'set -a; . "$1"; set +a; printf "%s\\n%s\\n" "${JIRA_URL:-}" "${JIRA_USERNAME:-}"'
        result = subprocess.run(
            ["bash", "-c", script, "_", str(env_file)], capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            url, user = (result.stdout.splitlines() + ["", ""])[:2]
            settings = {"JIRA_URL": url, "JIRA_USERNAME": user}
    url = os.environ.get("JIRA_URL") or settings.get("JIRA_URL", "")
    user = os.environ.get("JIRA_USERNAME") or settings.get("JIRA_USERNAME", "")
    if not url or "your-site" in url:
        die(f"set JIRA_URL in {env_file}")
    if not user or user == "you@example.com":
        die(f"set JIRA_USERNAME in {env_file}")
    token = os.environ.get("JIRA_API_TOKEN")
    if not token:
        try:
            token = subprocess.run(
                ["harness-secret", "get", "JIRA_API_TOKEN"], capture_output=True, text=True, check=True
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            die("no Jira token. Run: harness-secret set JIRA_API_TOKEN")
    return url.rstrip("/"), user, token


# ------------------------------------------------------------------ client
class JiraError(Exception):
    def __init__(self, status: int, method: str, path: str, body: str) -> None:
        self.status, self.body = status, body
        super().__init__(f"{method} {path} -> HTTP {status}: {body[:500]}")

    def field_errors(self) -> dict:
        try:
            return json.loads(self.body).get("errors", {}) or {}
        except (ValueError, AttributeError):
            return {}


class Jira:
    def __init__(self, url: str, user: str, token: str) -> None:
        self.url = url
        auth = base64.b64encode(f"{user}:{token}".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def call(self, method: str, path: str, body: object | None = None, params: dict | None = None):
        url = self.url + path + ("?" + urllib.parse.urlencode(params) if params else "")
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data, method=method, headers=self.headers)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read().decode()
                return json.loads(raw) if raw.strip() else None
        except urllib.error.HTTPError as exc:
            raise JiraError(exc.code, method, path, exc.read().decode(errors="replace")) from None

    def search(self, jql: str, fields: list[str]) -> list[dict]:
        issues: list[dict] = []
        token = None
        while True:
            body: dict = {"jql": jql, "fields": fields, "maxResults": 100}
            if token:
                body["nextPageToken"] = token
            page = self.call("POST", "/rest/api/3/search/jql", body)
            issues.extend(page.get("issues", []))
            token = page.get("nextPageToken")
            if not token:
                return issues


# ------------------------------------------------------------------ seeding
class Seeder:
    def __init__(self, jira: Jira | None, project: str, repo: str, seed: dict, dry_run: bool) -> None:
        self.jira, self.project, self.repo, self.seed, self.dry = jira, project, repo, seed, dry_run
        self.keys: dict[str, str] = {}  # seed id -> issue key
        self.created: set[str] = set()
        self.type_ids: dict[str, str] = {}
        self.drop_priority = False

    def text(self, markdown: str, seed_id: str | None = None) -> dict:
        markdown = markdown.replace("${REPO}", self.repo)
        if seed_id:
            markdown += f"\n\n_Seeded by harness sandbox/seed-jira.py (seed id {seed_id})._"
        return markdown_to_adf(markdown)

    def discover_types(self) -> None:
        project = self.jira.call("GET", f"/rest/api/3/project/{self.project}")
        print(f"Project {self.project}: {project.get('name')} ({project.get('style', 'classic')})")
        types = project.get("issueTypes", [])
        by_name = {t["name"].lower(): t for t in types}
        for kind, name in TYPE_NAMES.items():
            found = by_name.get(name.lower())
            if kind == "epic" and not found:
                found = next((t for t in types if t.get("hierarchyLevel") == 1), None)
            if kind in ("story", "bug") and not found:
                found = by_name.get("task")
                if found:
                    warn(f"project has no {name} issue type; using Task")
            if not found:
                die(f"project {self.project} has no {name} issue type")
            self.type_ids[kind] = found["id"]
        subtask = next((t for t in types if t.get("subtask")), None)
        if subtask:
            self.type_ids["subtask"] = subtask["id"]
        else:
            warn("project has no sub-task issue type; sub-tasks will be skipped")

    def find_existing(self) -> None:
        jql = f'project = "{self.project}" AND labels = "{SEED_LABEL}"'
        for issue in self.jira.search(jql, ["labels"]):
            for label in issue["fields"].get("labels", []):
                if label.startswith("seed-"):
                    self.keys[label.removeprefix("seed-").upper()] = issue["key"]
        if self.keys:
            print(f"Found {len(self.keys)} previously seeded issues; creating only what is missing.")

    def create_issue(self, seed_id: str, kind: str, summary: str, description: str,
                     labels: list[str], priority: str | None, parent: str | None) -> str:
        fields: dict = {
            "project": {"key": self.project},
            "issuetype": {"id": self.type_ids.get(kind, "?")},
            "summary": summary,
            "description": self.text(description or "", seed_id),
            "labels": [SEED_LABEL, seed_label(seed_id), *labels],
        }
        if priority and not self.drop_priority:
            fields["priority"] = {"name": priority}
        if parent:
            fields["parent"] = {"key": parent}
        if self.dry:
            key = f"{self.project}-<{seed_id}>"
            print(f"  would create {kind:<8} {key:<14} {summary}" + (f"  (parent {parent})" if parent else ""))
            return key
        for _attempt in range(3):
            try:
                key = self.jira.call("POST", "/rest/api/3/issue", {"fields": fields})["key"]
                break
            except JiraError as exc:
                errors = exc.field_errors()
                if "priority" in errors and "priority" in fields:
                    warn("priority can't be set in this project; continuing without priorities")
                    self.drop_priority = True
                    fields.pop("priority")
                elif "parent" in errors and kind != "subtask" and "parent" in fields:
                    warn(f"{seed_id}: couldn't set epic {parent} ({errors['parent']}); created without it")
                    fields.pop("parent")
                else:
                    raise
        else:
            raise RuntimeError(f"could not create {seed_id}")
        print(f"  created {kind:<8} {key:<10} {summary}")
        return key

    def run(self) -> None:
        if not self.dry:
            self.discover_types()
            self.find_existing()
        issues = self.seed["issues"]
        ordered = [i for i in issues if i["type"] == "epic"] + [i for i in issues if i["type"] != "epic"]
        print("Issues:")
        for item in ordered:
            sid = item["id"].upper()
            if sid not in self.keys:
                parent = self.keys.get(item["epic"].upper()) if item.get("epic") else None
                self.keys[sid] = self.create_issue(
                    sid, item["type"], item["summary"], item.get("description", ""),
                    item.get("labels", []), item.get("priority"), parent,
                )
                self.created.add(sid)
            for n, sub in enumerate(item.get("subtasks", []), start=1):
                sub_id = f"{sid}-{n}"
                if sub_id in self.keys or (not self.dry and "subtask" not in self.type_ids):
                    continue
                self.keys[sub_id] = self.create_issue(
                    sub_id, "subtask", sub["summary"], sub.get("description", ""),
                    item.get("labels", []), None, self.keys[sid],
                )
                self.created.add(sub_id)
        self.add_comments_and_status(ordered)
        self.add_links(issues)
        self.add_sprint()
        self.print_summary(ordered)

    def add_comments_and_status(self, issues: list[dict]) -> None:
        for item in issues:
            sid = item["id"].upper()
            if sid not in self.created:
                continue  # only decorate issues created in this run
            key = self.keys[sid]
            for comment in item.get("comments", []):
                if self.dry:
                    print(f"  would comment on {key}")
                else:
                    self.jira.call("POST", f"/rest/api/3/issue/{key}/comment", {"body": self.text(comment)})
            status = item.get("status")
            if status:
                self.transition(key, status)

    def transition(self, key: str, status: str) -> None:
        if self.dry:
            print(f"  would move {key} to {status}")
            return
        transitions = self.jira.call("GET", f"/rest/api/3/issue/{key}/transitions")["transitions"]
        match = next(
            (t for t in transitions
             if t["to"]["name"].lower() == status.lower() or t["name"].lower() == status.lower()),
            None,
        )
        if not match:
            names = ", ".join(t["to"]["name"] for t in transitions)
            warn(f"{key}: no transition to {status!r} (available: {names}); left as is")
            return
        self.jira.call("POST", f"/rest/api/3/issue/{key}/transitions", {"transition": {"id": match["id"]}})
        print(f"  moved {key} to {match['to']['name']}")

    def add_links(self, issues: list[dict]) -> None:
        for item in issues:
            for link in item.get("links", []):
                source, target = self.keys[item["id"].upper()], self.keys[link["to"].upper()]
                if self.dry:
                    print(f"  would link {source} {link['type'].lower()} {target}")
                    continue
                if self.linked(source, target, link["type"]):
                    continue
                self.create_link(source, target, link["type"])

    def linked(self, source: str, target: str, link_type: str) -> dict | None:
        """The link between source and target of this type, if any (either direction)."""
        links = self.jira.call("GET", f"/rest/api/3/issue/{source}", params={"fields": "issuelinks"})
        for link in links["fields"].get("issuelinks", []):
            if link["type"]["name"].lower() != link_type.lower():
                continue
            other = link.get("outwardIssue") or link.get("inwardIssue") or {}
            if other.get("key") == target:
                return link
        return None

    def create_link(self, source: str, target: str, link_type: str) -> None:
        # Intended reading: "<source> <outward verb> <target>", e.g. "B4 blocks S6".
        body = {"type": {"name": link_type}, "outwardIssue": {"key": target}, "inwardIssue": {"key": source}}
        self.jira.call("POST", "/rest/api/3/issueLink", body)
        link = self.linked(source, target, link_type)
        if link and link_type.lower() == "blocks" and "inwardIssue" in link:
            # Seen from source, the target is "inward": Jira reads it as
            # "source is blocked by target". Recreate the other way round.
            self.jira.call("DELETE", f"/rest/api/3/issueLink/{link['id']}")
            body["outwardIssue"], body["inwardIssue"] = body["inwardIssue"], body["outwardIssue"]
            self.jira.call("POST", "/rest/api/3/issueLink", body)
        print(f"  linked  {source} {link_type.lower()} {target}")

    def add_sprint(self) -> None:
        sprint = self.seed.get("sprint")
        if not sprint:
            return
        keys = [self.keys[i.upper()] for i in sprint["issues"]]
        if self.dry:
            print(f"  would add {len(keys)} issues to sprint {sprint['name']!r}")
            return
        boards = self.jira.call("GET", "/rest/agile/1.0/board", params={"projectKeyOrId": self.project})
        board = next((b for b in boards.get("values", []) if b.get("type") == "scrum"), None)
        if not board:
            warn("no Scrum board for this project (Kanban boards have no sprints); sprint skipped")
            return
        sprints = self.jira.call(
            "GET", f"/rest/agile/1.0/board/{board['id']}/sprint", params={"state": "future,active"}
        ).get("values", [])
        existing = next((s for s in sprints if s["name"] == sprint["name"]), None)
        if existing:
            sprint_id = existing["id"]
        else:
            sprint_id = self.jira.call(
                "POST", "/rest/agile/1.0/sprint",
                {"name": sprint["name"], "goal": sprint.get("goal", ""), "originBoardId": board["id"]},
            )["id"]
            print(f"  created sprint {sprint['name']!r} on board {board['name']!r}")
        self.jira.call("POST", f"/rest/agile/1.0/sprint/{sprint_id}/issue", {"issues": keys})
        print(f"  sprint {sprint['name']!r}: {', '.join(keys)}")

    def print_summary(self, issues: list[dict]) -> None:
        verb = "Would create" if self.dry else "Created"
        print(f"\n{verb} {len(self.created)} issues ({len(self.keys) - len(self.created)} already existed).")
        if not self.dry:
            print(f"Board: {self.jira.url}/jira/software/projects/{self.project}/boards")


def delete_seeded(jira: Jira, project: str, assume_yes: bool) -> None:
    jql = f'project = "{project}" AND labels = "{SEED_LABEL}"'
    issues = jira.search(jql, ["summary", "issuetype"])
    if not issues:
        print("Nothing to delete.")
        return
    print(f"This permanently deletes {len(issues)} issues labelled {SEED_LABEL} in {project}:")
    for issue in issues:
        print(f"  {issue['key']:<10} {issue['fields']['summary']}")
    if not assume_yes and input("Type the project key to confirm: ").strip() != project:
        die("not confirmed; nothing deleted")
    # Sub-tasks and stories first, epics last.
    issues.sort(key=lambda i: i["fields"]["issuetype"].get("hierarchyLevel", 0))
    for issue in issues:
        try:
            jira.call("DELETE", f"/rest/api/3/issue/{issue['key']}", params={"deleteSubtasks": "true"})
            print(f"  deleted {issue['key']}")
        except JiraError as exc:
            if exc.status == 404:
                continue  # already removed with its parent
            raise
    print("Sprints are left in place; delete them from the board if you want a clean slate.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", required=True, help="Jira project key, e.g. LEDG")
    parser.add_argument("--seed", default=str(HERE / "jira-seed.yaml"))
    parser.add_argument("--repo", help="GitHub owner/name the tickets refer to (default: from the seed file)")
    parser.add_argument("--dry-run", action="store_true", help="print the plan without calling Jira")
    parser.add_argument("--delete", action="store_true", help="delete all seeded issues in the project")
    parser.add_argument("--yes", action="store_true", help="with --delete: don't ask for confirmation")
    args = parser.parse_args()

    seed = yaml.safe_load(Path(args.seed).read_text(encoding="utf-8"))
    project = args.project.upper()
    if args.dry_run:
        Seeder(None, project, args.repo or seed["repo"], seed, dry_run=True).run()
        return 0
    jira = Jira(*load_harness_settings())
    try:
        if args.delete:
            delete_seeded(jira, project, args.yes)
        else:
            Seeder(jira, project, args.repo or seed["repo"], seed, dry_run=False).run()
    except JiraError as exc:
        if exc.status in (401, 403):
            die(f"{exc}\nCheck JIRA_USERNAME / JIRA_API_TOKEN, and that you can create issues in {project}.")
        if exc.status == 404 and "/project/" in str(exc):
            die(f"project {project} not found. Create it in Jira first (see sandbox/README.md).")
        die(str(exc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
