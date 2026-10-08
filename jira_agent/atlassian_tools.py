"""Jira + Bitbucket Cloud tools exposed to the agent as an in-process MCP server."""
import json
import os
from typing import Any

import httpx
from claude_agent_sdk import create_sdk_mcp_server, tool

MAX_CHARS = 30_000  # keep tool results from flooding the context window


def _jira() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=os.environ["JIRA_BASE_URL"].rstrip("/"),
        auth=(os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"]),
        timeout=30,
    )


def _bb() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url="https://api.bitbucket.org/2.0",
        auth=(os.environ["BITBUCKET_EMAIL"], os.environ["BITBUCKET_API_TOKEN"]),
        timeout=60,
        follow_redirects=True,
    )


def _text(s: str, is_error: bool = False) -> dict[str, Any]:
    if len(s) > MAX_CHARS:
        s = s[:MAX_CHARS] + f"\n...[truncated, {len(s) - MAX_CHARS} chars omitted]"
    return {"content": [{"type": "text", "text": s}], "is_error": is_error}


async def _get(client: httpx.AsyncClient, path: str, **params) -> httpx.Response:
    async with client as c:
        r = await c.get(path, params=params)
        r.raise_for_status()
        return r


@tool("jira_get_issue", "Fetch a Jira issue: summary, description, acceptance criteria, labels, comments.", {"key": str})
async def jira_get_issue(args):
    try:
        async with _jira() as c:
            r = await c.get(f"/rest/api/2/issue/{args['key']}", params={"expand": "renderedFields"})
            r.raise_for_status()
        d = r.json()
        f = d["fields"]
        out = {
            "key": d["key"],
            "type": f["issuetype"]["name"],
            "summary": f["summary"],
            "description": f.get("description"),
            "labels": f.get("labels", []),
            "components": [x["name"] for x in f.get("components", [])],
            "status": f["status"]["name"],
            "comments": [
                {"author": x["author"]["displayName"], "body": x["body"]}
                for x in f.get("comment", {}).get("comments", [])
            ],
        }
        return _text(json.dumps(out, indent=2))
    except Exception as e:
        return _text(f"jira_get_issue failed: {e}", True)


@tool("jira_add_comment", "Add a comment to a Jira issue (e.g. the PR link).", {"key": str, "body": str})
async def jira_add_comment(args):
    try:
        async with _jira() as c:
            r = await c.post(f"/rest/api/2/issue/{args['key']}/comment", json={"body": args["body"]})
            r.raise_for_status()
        return _text("comment added")
    except Exception as e:
        return _text(f"jira_add_comment failed: {e}", True)


@tool(
    "bitbucket_list_merged_prs",
    "List the most recently merged PRs of a repo (id, title, author, branch names, description, reviewers).",
    {"repo": str, "limit": int},
)
async def bitbucket_list_merged_prs(args):
    try:
        r = await _get(
            _bb(), f"/repositories/{args['repo']}/pullrequests",
            state="MERGED", sort="-updated_on", pagelen=min(args.get("limit", 20), 50),
        )
        prs = [
            {
                "id": p["id"], "title": p["title"], "author": p["author"]["display_name"],
                "source_branch": p["source"]["branch"]["name"],
                "destination_branch": p["destination"]["branch"]["name"],
                "description": p.get("description", ""),
                "comment_count": p.get("comment_count"),
            }
            for p in r.json()["values"]
        ]
        return _text(json.dumps(prs, indent=2))
    except Exception as e:
        return _text(f"bitbucket_list_merged_prs failed: {e}", True)


@tool("bitbucket_get_pr_diff", "Get the unified diff of a PR.", {"repo": str, "pr_id": int})
async def bitbucket_get_pr_diff(args):
    try:
        r = await _get(_bb(), f"/repositories/{args['repo']}/pullrequests/{args['pr_id']}/diff")
        return _text(r.text)
    except Exception as e:
        return _text(f"bitbucket_get_pr_diff failed: {e}", True)


@tool("bitbucket_get_pr_comments", "Get review comments on a PR (reveals reviewer expectations).", {"repo": str, "pr_id": int})
async def bitbucket_get_pr_comments(args):
    try:
        r = await _get(_bb(), f"/repositories/{args['repo']}/pullrequests/{args['pr_id']}/comments", pagelen=50)
        comments = [
            {"user": c["user"]["display_name"], "text": c["content"]["raw"], "file": (c.get("inline") or {}).get("path")}
            for c in r.json()["values"] if not c.get("deleted")
        ]
        return _text(json.dumps(comments, indent=2))
    except Exception as e:
        return _text(f"bitbucket_get_pr_comments failed: {e}", True)


@tool(
    "bitbucket_create_pr",
    "Open a pull request. The source branch must already be pushed.",
    {"repo": str, "title": str, "description": str, "source_branch": str, "destination_branch": str},
)
async def bitbucket_create_pr(args):
    try:
        body = {
            "title": args["title"],
            "description": args["description"],
            "source": {"branch": {"name": args["source_branch"]}},
            "destination": {"branch": {"name": args["destination_branch"]}},
        }
        async with _bb() as c:
            r = await c.post(f"/repositories/{args['repo']}/pullrequests", json=body)
            r.raise_for_status()
        return _text(r.json()["links"]["html"]["href"])
    except Exception as e:
        return _text(f"bitbucket_create_pr failed: {e}", True)


READ_TOOLS = [jira_get_issue, bitbucket_list_merged_prs, bitbucket_get_pr_diff, bitbucket_get_pr_comments]
WRITE_TOOLS = [jira_add_comment, bitbucket_create_pr]


def build_server(dry_run: bool):
    tools = READ_TOOLS if dry_run else READ_TOOLS + WRITE_TOOLS
    return create_sdk_mcp_server("atlassian", tools=tools), [f"mcp__atlassian__{t.name}" for t in tools]
