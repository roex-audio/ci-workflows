# RoEx/.github — Org-wide AI Code Review

Automated AI code review that runs on every pull request across the RoEx GitHub organisation. Uses `glm-5.2:cloud` on Ollama Cloud to post inline comments and a summary on each PR.

## How it works

1. A PR is opened/updated in any RoEx repo
2. The org ruleset triggers `.github/workflows/ai-review.yml`
3. The workflow diffs the PR, sends it to Ollama Cloud, and posts the review

No per-repo configuration is needed.

## Repository structure

```
.github/
  workflows/
    ai-review.yml   # Reusable workflow (workflow_call)
  scripts/
    review.py       # Review logic — calls Ollama Cloud, posts to GitHub
```

## Setup (one-time, org admin)

### 1. Set the org secret

Go to **Organisation Settings → Secrets and variables → Actions → New organisation secret**:

- Name: `OLLAMA_API_KEY`
- Value: your Ollama Cloud API key
- Access: All repositories (or selected repos)

### 2. Create the org ruleset

Go to **Organisation Settings → Rules → Rulesets → New ruleset**:

1. **Name:** AI Code Review
2. **Enforcement:** Active
3. **Target:** All repositories (or select specific ones)
4. **Rules → Require workflows:**
   - Workflow: `RoEx/.github/.github/workflows/ai-review.yml@main`

Save the ruleset. Every PR in targeted repos will now trigger the AI review.

### 3. Excluding repos (optional)

In the ruleset target configuration, switch from "All repositories" to "Include by pattern" or use the exclude list to skip specific repos (e.g. forks, archived repos).

## Requirements

- **GitHub Team or Enterprise plan** — required workflow rulesets are not available on the free organisation tier.
- If on the free tier, alternatives:
  - Upgrade to Team ($4/user/month)
  - Build a GitHub App that listens to `pull_request` webhooks org-wide and runs the same review logic from a small server

## Configuration

The script uses these environment variables (set automatically by the workflow):

| Variable | Source | Purpose |
|----------|--------|---------|
| `OLLAMA_API_KEY` | Org secret | Authenticates with Ollama Cloud |
| `GITHUB_TOKEN` | `github.token` | Posts review comments on the PR |
| `PR_NUMBER` | Workflow context | Target pull request number |
| `REPO` | Workflow context | `owner/repo` identifier |

## Model

- **Model:** `glm-5.2:cloud`
- **Endpoint:** `https://ollama.com/v1/chat/completions`
- **Auth:** Bearer token (OpenAI-compatible API)

To change the model, edit `MODEL` in `.github/scripts/review.py`.
