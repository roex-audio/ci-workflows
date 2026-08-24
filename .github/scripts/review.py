"""
AI Code Review script.
Reads a unified diff, sends it to Ollama Cloud (glm-5.2:cloud) for review,
and posts inline + summary comments on the GitHub PR.
"""

import json
import os
import re
import sys

import requests

OLLAMA_API_URL = "https://ollama.com/v1/chat/completions"
MODEL = "glm-5.2:cloud"
MAX_DIFF_LINES = 4000

SYSTEM_PROMPT = """\
You are a senior software engineer performing a code review.
You will receive a unified diff from a pull request.

Respond ONLY with valid JSON matching this schema (no markdown fences):
{
  "summary": "A concise overall summary of the changes and any high-level concerns.",
  "comments": [
    {
      "path": "relative/file/path.ext",
      "line": <line number in the NEW file where the comment applies>,
      "severity": "critical|warning|suggestion|nitpick",
      "body": "Your review comment for this specific line."
    }
  ]
}

Rules:
- "comments" may be an empty array if there are no issues.
- Only comment on meaningful problems: bugs, security issues, performance, readability, or correctness.
- Do not comment on style-only issues unless they hurt readability significantly.
- "line" must be a line number that exists in the diff's added/modified lines (lines starting with +).
- Keep each comment body under 3 sentences.
"""


def read_diff(path="diff.patch"):
    with open(path, "r") as f:
        return f.read()


def parse_diff_files(diff_text):
    """Extract the set of files and their changed line ranges from a unified diff."""
    files = {}
    current_file = None
    new_line_num = 0

    for line in diff_text.splitlines():
        header = re.match(r"^diff --git a/.+ b/(.+)$", line)
        if header:
            current_file = header.group(1)
            files[current_file] = set()
            continue

        hunk = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
        if hunk:
            new_line_num = int(hunk.group(1))
            continue

        if current_file is None:
            continue

        if line.startswith("+") and not line.startswith("+++"):
            files[current_file].add(new_line_num)
            new_line_num += 1
        elif line.startswith("-") and not line.startswith("---"):
            pass  # deleted lines don't increment new file line counter
        else:
            new_line_num += 1

    return files


def truncate_diff(diff_text, max_lines=MAX_DIFF_LINES):
    lines = diff_text.splitlines()
    if len(lines) <= max_lines:
        return diff_text
    return "\n".join(lines[:max_lines]) + "\n\n[... diff truncated ...]"


def call_ollama(diff_text, api_key):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": diff_text},
        ],
        "temperature": 0.2,
    }

    resp = requests.post(OLLAMA_API_URL, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()

    data = resp.json()
    content = data["choices"][0]["message"]["content"]

    # Strip markdown code fences if the model wraps the JSON
    content = re.sub(r"^```(?:json)?\s*", "", content.strip())
    content = re.sub(r"\s*```$", "", content.strip())

    return json.loads(content)


def post_inline_review(comments, repo, pr_number, token, changed_lines):
    """Post a pull request review with inline comments."""
    if not comments:
        return

    gh_comments = []
    for c in comments:
        path = c.get("path", "")
        line = c.get("line")
        body = c.get("body", "")
        severity = c.get("severity", "suggestion")

        # Only post on lines that actually changed
        if path in changed_lines and line in changed_lines[path]:
            prefix = {"critical": "🔴", "warning": "🟡", "suggestion": "🔵", "nitpick": "⚪"}.get(severity, "🔵")
            gh_comments.append({
                "path": path,
                "line": line,
                "body": f"{prefix} **{severity.capitalize()}**: {body}",
            })

    if not gh_comments:
        return

    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/reviews"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {
        "event": "COMMENT",
        "comments": gh_comments,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    if resp.status_code == 422:
        # Some comments may reference invalid positions; retry without them
        print(f"Review submission got 422, response: {resp.text}", file=sys.stderr)
    else:
        resp.raise_for_status()


def post_summary_comment(summary, repo, pr_number, token):
    """Post a top-level summary comment on the PR."""
    if not summary:
        return

    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    body = f"## 🤖 AI Code Review\n\n{summary}"
    resp = requests.post(url, headers=headers, json={"body": body}, timeout=30)
    resp.raise_for_status()


def main():
    api_key = os.environ.get("OLLAMA_API_KEY")
    token = os.environ.get("GITHUB_TOKEN")
    pr_number = os.environ.get("PR_NUMBER")
    repo = os.environ.get("REPO")

    if not all([api_key, token, pr_number, repo]):
        print("Missing required environment variables.", file=sys.stderr)
        sys.exit(1)

    diff_text = read_diff()
    if not diff_text.strip():
        print("Empty diff, skipping review.")
        return

    changed_lines = parse_diff_files(diff_text)
    truncated_diff = truncate_diff(diff_text)

    print(f"Sending {len(truncated_diff.splitlines())} lines to {MODEL}...")
    review = call_ollama(truncated_diff, api_key)

    summary = review.get("summary", "")
    comments = review.get("comments", [])

    print(f"Received {len(comments)} inline comment(s).")

    if comments:
        post_inline_review(comments, repo, pr_number, token, changed_lines)

    if summary:
        post_summary_comment(summary, repo, pr_number, token)

    print("Review posted successfully.")


if __name__ == "__main__":
    main()
