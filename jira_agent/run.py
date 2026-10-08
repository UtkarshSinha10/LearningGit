#!/usr/bin/env python3
"""Usage: python run.py PROJ-123 workspace/repo-slug [--branch main] [--dry-run]"""
import argparse
import asyncio
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, ToolUseBlock, query

from atlassian_tools import build_server

HERE = Path(__file__).parent


def clone(repo: str, dest: str, branch: str) -> None:
    env = {**os.environ, "GIT_ASKPASS": str(HERE / "askpass.py"), "GIT_TERMINAL_PROMPT": "0"}
    subprocess.run(
        ["git", "clone", "--branch", branch, f"https://bitbucket.org/{repo}.git", dest],
        check=True, env=env,
    )
    for k, v in (("user.name", "jira-agent"), ("user.email", os.environ["BITBUCKET_EMAIL"])):
        subprocess.run(["git", "-C", dest, "config", k, v], check=True)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ticket")
    ap.add_argument("repo", help="workspace/repo-slug")
    ap.add_argument("--branch", default="main", help="default branch to base work on")
    ap.add_argument("--dry-run", action="store_true", help="implement locally; don't push/open PR/comment")
    ap.add_argument("--model", default=None)
    a = ap.parse_args()

    workdir = tempfile.mkdtemp(prefix="jira-agent-")
    clone(a.repo, workdir, a.branch)
    server, mcp_tools = build_server(a.dry_run)

    opts = ClaudeAgentOptions(
        system_prompt=(HERE / "prompt.md").read_text(),
        cwd=workdir,
        mcp_servers={"atlassian": server},
        allowed_tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash", *mcp_tools],
        permission_mode="acceptEdits",
        env={"GIT_ASKPASS": str(HERE / "askpass.py"), "GIT_TERMINAL_PROMPT": "0"},
        model=a.model,
        max_turns=150,
    )
    task = (
        f"Implement Jira ticket {a.ticket} in Bitbucket repo {a.repo} (default branch `{a.branch}`, "
        f"checked out in the current directory)."
        + (" DRY RUN: do everything except pushing and opening the PR; show the final diff instead." if a.dry_run else "")
    )

    async for msg in query(prompt=task, options=opts):
        if isinstance(msg, AssistantMessage):
            for b in msg.content:
                if isinstance(b, TextBlock):
                    print(b.text)
                elif isinstance(b, ToolUseBlock):
                    print(f"  [tool] {b.name}", file=sys.stderr)
        elif isinstance(msg, ResultMessage):
            print(f"\n== done ({msg.num_turns} turns, ${msg.total_cost_usd or 0:.2f}) ==", file=sys.stderr)
            return 1 if msg.is_error else 0
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
