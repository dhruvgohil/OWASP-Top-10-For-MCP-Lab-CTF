"""Local, pure-Python store that MIMICS a git-backed project board.

There is deliberately **no `git` binary and no subprocess** anywhere in this module.
The whole "GitHub-like" environment is faked locally:

  * issues/<n>.md   -- one markdown file per issue (the working tree)
  * index.json      -- the board index + column layout (Backlog / In Progress / Done)
  * commits.json    -- an append-only "commit log" that imitates `git log`, with
                       short SHA-like ids derived via hashlib. `_commit()` is our
                       pure-Python stand-in for `git commit`.

This satisfies the lab's "completely local, no GitHub integration" requirement.

SAFETY NOTE: this module is intentionally SAFE -- it performs only file and JSON I/O.
The command-injection vulnerability that this lab teaches lives in `kanban_mcp.py`
(the `create_issue` "notification hook"), NOT here.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

# The three board columns, exactly like a simple GitHub Projects / Kanban board.
COLUMNS = ["Backlog", "In Progress", "Done"]

_NULL_ID = "0000000"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class BoardError(Exception):
    """Raised for benign, expected board errors (missing issue, bad column, ...)."""


class BoardStore:
    """A tiny local issue tracker with a git-like commit history."""

    def __init__(self, root: str):
        self.root = Path(root)
        self.issues_dir = self.root / "issues"
        self.index_path = self.root / "index.json"
        self.commits_path = self.root / "commits.json"
        self._ensure()

    # ------------------------------------------------------------------ setup
    def _ensure(self) -> None:
        self.issues_dir.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self._write_index({"next_number": 1, "issues": {}})
        if not self.commits_path.exists():
            self._write_commits([])

    def is_empty(self) -> bool:
        index = self._read_index()
        return index["next_number"] == 1 and not index["issues"]

    # ------------------------------------------------------- low-level JSON IO
    def _read_index(self) -> dict:
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _write_index(self, data: dict) -> None:
        self.index_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _read_commits(self) -> list:
        return json.loads(self.commits_path.read_text(encoding="utf-8"))

    def _write_commits(self, data: list) -> None:
        self.commits_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _issue_path(self, number: int) -> Path:
        return self.issues_dir / f"{number}.md"

    # ------------------------------------------------------------ git mimicry
    def _commit(self, message: str, issue_number: int | None = None,
                author: str = "taskforge-bot") -> dict:
        """Pure-Python stand-in for `git commit`.

        Appends an entry to commits.json with a short SHA-like id chained off the
        previous commit -- imitating git history without ever calling git.
        """
        commits = self._read_commits()
        parent = commits[-1]["id"] if commits else _NULL_ID
        ts = _now()
        digest = hashlib.sha1(f"{parent}\n{ts}\n{message}\n{issue_number}".encode())
        entry = {
            "id": digest.hexdigest()[:7],
            "parent": parent,
            "timestamp": ts,
            "author": author,
            "message": message,
            "issue": issue_number,
        }
        commits.append(entry)
        self._write_commits(commits)
        return entry

    def history(self, limit: int = 50) -> list:
        """Return the most recent commits, newest first (like `git log`)."""
        commits = self._read_commits()
        return list(reversed(commits[-limit:]))

    # ------------------------------------------------------------- issue files
    def _render_issue(self, issue: dict) -> str:
        labels = ", ".join(issue["labels"]) if issue["labels"] else "-"
        lines = [
            f"# #{issue['number']} {issue['title']}",
            "",
            f"- **State:** {issue['state']}",
            f"- **Column:** {issue['column']}",
            f"- **Labels:** {labels}",
            f"- **Created:** {issue['created_at']}",
            "",
            "## Description",
            "",
            issue["description"] or "_No description provided._",
            "",
            "## Comments",
            "",
        ]
        if issue["comments"]:
            for c in issue["comments"]:
                lines.append(f"- _{c['at']}_ **{c['author']}**: {c['body']}")
        else:
            lines.append("_No comments yet._")
        return "\n".join(lines) + "\n"

    def _write_issue_file(self, issue: dict) -> None:
        self._issue_path(issue["number"]).write_text(
            self._render_issue(issue), encoding="utf-8"
        )

    def _load_issue(self, number: int) -> dict:
        path = self.root / "data" / f"{number}.json"
        if not path.exists():
            raise BoardError(f"Issue #{number} does not exist.")
        return json.loads(path.read_text(encoding="utf-8"))

    def _store_issue(self, issue: dict) -> None:
        # Full issue records live as JSON (source of truth); the .md file is the
        # human-readable "working tree" rendering.
        (self.root / "data").mkdir(parents=True, exist_ok=True)
        (self.root / "data" / f"{issue['number']}.json").write_text(
            json.dumps(issue, indent=2), encoding="utf-8"
        )
        self._write_issue_file(issue)

    # ---------------------------------------------------------------- issue ops
    def add_issue(self, title: str, description: str = "", labels: str = "") -> dict:
        index = self._read_index()
        number = index["next_number"]
        index["next_number"] = number + 1

        labels_list = [l.strip() for l in labels.split(",") if l.strip()]
        issue = {
            "number": number,
            "title": title,
            "description": description,
            "labels": labels_list,
            "column": "Backlog",
            "state": "open",
            "comments": [],
            "created_at": _now(),
        }
        index["issues"][str(number)] = {
            "number": number,
            "title": title,
            "state": "open",
            "column": "Backlog",
        }
        self._write_index(index)
        self._store_issue(issue)
        self._commit(f"Add issue #{number}: {title}", issue_number=number)
        return issue

    def get(self, number: int) -> dict:
        return self._load_issue(int(number))

    def list(self, state: str = "open") -> list:
        index = self._read_index()
        out = []
        for meta in index["issues"].values():
            if state in ("all", None) or meta["state"] == state:
                out.append(meta)
        return sorted(out, key=lambda m: m["number"])

    def comment(self, number: int, body: str, author: str = "user") -> dict:
        issue = self._load_issue(int(number))
        issue["comments"].append({"author": author, "body": body, "at": _now()})
        self._store_issue(issue)
        self._commit(f"Comment on issue #{number}", issue_number=int(number))
        return issue

    def add_label(self, number: int, label: str) -> dict:
        issue = self._load_issue(int(number))
        label = label.strip()
        if label and label not in issue["labels"]:
            issue["labels"].append(label)
        self._sync_index(issue)
        self._store_issue(issue)
        self._commit(f"Label issue #{number}: {label}", issue_number=int(number))
        return issue

    def move(self, number: int, column: str) -> dict:
        if column not in COLUMNS:
            raise BoardError(
                f"Unknown column '{column}'. Valid columns: {', '.join(COLUMNS)}."
            )
        issue = self._load_issue(int(number))
        issue["column"] = column
        self._sync_index(issue)
        self._store_issue(issue)
        self._commit(f"Move issue #{number} to {column}", issue_number=int(number))
        return issue

    def close(self, number: int) -> dict:
        issue = self._load_issue(int(number))
        issue["state"] = "closed"
        issue["column"] = "Done"
        self._sync_index(issue)
        self._store_issue(issue)
        self._commit(f"Close issue #{number}", issue_number=int(number))
        return issue

    def _sync_index(self, issue: dict) -> None:
        index = self._read_index()
        index["issues"][str(issue["number"])] = {
            "number": issue["number"],
            "title": issue["title"],
            "state": issue["state"],
            "column": issue["column"],
        }
        self._write_index(index)
