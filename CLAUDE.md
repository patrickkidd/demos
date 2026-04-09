# Demos — Project Instructions

## Auth Strategy
- This project uses the Claude Max plan via OAuth (claude.ai login), NOT API keys.
- Never switch to ANTHROPIC_API_KEY or any API-key-based auth without explicit
  user approval.
- Never change architectural strategy (auth method, deployment model, etc.)
  without asking first.

## Architecture
- Containerized FastAPI app with Claude Agent SDK
- Docker container runs as non-root user `app` (uid 1000), required for
  `--dangerously-skip-permissions`
- `claude auth login` prints an OAuth URL then polls Anthropic's servers
  waiting for the user to complete the browser-based flow. No localhost
  callback server, no stdin code entry. The CLI auto-detects completion.
  Auth credentials are stored in the bind-mounted `./instance/.claude/`.

## Container Safety Rule
- Before rebuilding or restarting the Docker container, always check whether
  a background task is running (`curl -s http://localhost:8000/api/status`).
- If a task is running, do NOT rebuild. Wait for it to finish or ask the user.
- After any container restart, verify data integrity: check that
  `instance/stories.json` is valid JSON, that story directories have the
  expected structure, and that no partial sample directories were left by
  a killed task.

## Methodology Maintenance Rule
- Any change to prompts, output schemas, analytical approach, centroid
  weighting, or visualization logic MUST include a corresponding update to
  `doc/methodology.md` to keep it aligned with the actual implementation.
- The methodology doc is rendered as a page in the web UI at `/methodology`.
  It is a user-facing document, not internal notes.
