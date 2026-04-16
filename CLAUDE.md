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

## WordPress Publish Pipeline

### How It Works
Sample pages are pushed to `alaskafamilysystems.com` via the WP REST API.
Content is rendered by the same Jinja2 templates as the local app, with admin
controls stripped. HTML and JS are base64-encoded (with UTF-8-safe
TextDecoder) to bypass WordPress's `wpautop` filter which corrupts multi-line
HTML/CSS/JS. All content lives inside a single `<div class="demos">` element
to prevent wpautop from wrapping scripts in `<p>` tags.

### Key Files
- `scripts/publish.py` — WP REST API transport: push, update, delete pages.
  Contains `_extract_wp_content()` (sample pages) and
  `_extract_index_content()` (landing page) which strip admin controls,
  rewrite local links to WP URLs, and base64-encode everything.
- `scripts/publish_state.py` — Manifest at `instance/publish_manifest.json`.
  Tracks WP page IDs and content hashes per story/sample.
- `instance/publish_config.json` — WP credentials and parent page ID.
  Gitignored. Contains `wp_url`, `wp_user`, `wp_password`, `parent_page_id`.

### WP Page Structure
- Landing page: page ID 4111 (`/research/news-reader/`), content = Stories
  index with timeline dots linking to published samples.
- Sample pages: children of 4111, slug pattern
  `demos-{topic-slug}-{YYYYMMDD}`.
- Methodology: child of 4111, slug `methodology`.

### WP Template & Integration
- Template: `elementor_header_footer` — renders AFS header/footer, full-width
  content area, no sidebar.
- Meta: `_elementor_edit_mode: ""` — tells Elementor not to take over rendering.
- Dark theme content renders between AFS header and footer.
- Sticky flow-nav uses `position: fixed` with runtime detection of Elementor
  sticky header height.

### Sync Flow
- `POST /publish/story/{id}` — idempotent sync. Pushes all analyzed samples,
  redacts WP pages for locally-deleted samples, re-pushes the landing page.
- `POST /publish/story/{id}/samples/{sid}` — push single sample.
- `POST /redact/story/{id}` — delete all WP pages for a story.
- `POST /redact/story/{id}/samples/{sid}` — delete single WP page.
- Local delete routes auto-redact from WP if the content was published.
- All publish routes are sync (not async) to avoid event loop deadlock from
  self-requests to localhost:8000.

### Critical Implementation Details
- All HTML is base64-encoded and decoded via `new TextDecoder().decode(
  Uint8Array.from(atob(...), c=>c.charCodeAt(0)))` — raw `atob()` mangles
  UTF-8 multi-byte characters (em-dashes, smart quotes, etc).
- Admin controls stripped by regex in `_extract_wp_content` and
  `_extract_index_content`: forms, buttons, danger zones, status badges,
  polling scripts, theme toggle.
- Local `/story/ID/samples/SID` links rewritten to WP URLs
  `/research/news-reader/demos-{topic}-{date}/` by `_rewrite_local_links()`.
- Story detail backlinks (`← Topic`) rewritten to `/research/news-reader/`.

### Safety Rules
- NEVER publish to WP without user clicking Sync in the dashboard.
- NEVER create pages with `status: publish` during testing — use `draft`.
- Always delete test drafts after verifying.
- The publish_manifest.json and publish_config.json are gitignored and live
  in the bind-mounted `instance/` volume — they survive container rebuilds.

## Methodology Maintenance Rule
- Any change to prompts, output schemas, analytical approach, centroid
  weighting, or visualization logic MUST include a corresponding update to
  `doc/methodology.md` to keep it aligned with the actual implementation.
- The methodology doc is rendered as a page in the web UI at `/methodology`.
  It is a user-facing document, not internal notes.
