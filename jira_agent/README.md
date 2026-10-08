# Jira → Bitbucket PR agent

Given a Jira ticket key and a Bitbucket repo, the agent:
1. reads the ticket,
2. studies ~10 recently merged PRs (diffs + review comments) and the repo to learn conventions,
3. implements the change on a new branch, runs lint/tests,
4. pushes, opens a PR in the team's format, and comments the PR link on the ticket.

Built on the Claude Agent SDK (Python). Jira/Bitbucket access is via custom tools in `atlassian_tools.py`;
code work uses the SDK's built-in Read/Edit/Grep/Bash in a fresh clone.

## Setup
```bash
pip install -r requirements.txt
cp .env.example .env   # fill in, then: set -a; source .env; set +a
python run.py PROJ-123 my-workspace/my-repo --branch main --dry-run   # try this first
python run.py PROJ-123 my-workspace/my-repo --branch main
```

## Safety notes
- Use a **dedicated bot account/token** scoped to one workspace; the token can push branches, so no admin rights.
- Enable Bitbucket branch protection on the default branch (required PR + review). The agent is told never to
  push there, but protection is the real guarantee. The agent can't merge; humans review.
- Run inside a container/CI runner: it executes shell commands (tests, linters) from the target repo.
- Bitbucket creds reach git via `GIT_ASKPASS`, not the remote URL, so they aren't visible in `git remote -v`
  (Bash can still read env vars; keep the token minimally scoped).
- Always start with `--dry-run` on a new repo and review the diff.

## Tuning
Edit `prompt.md` to encode team specifics (PR template, test commands). Each recurring reviewer complaint you
see on agent PRs is a line to add there. To trigger automatically, run `run.py` from a Jira webhook/CI job.
