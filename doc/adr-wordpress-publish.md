# ADR: WordPress Publishing Pipeline

**Status:** Accepted  
**Date:** 2026-04-15  
**Decision makers:** Patrick Stinson, Claude

## Context

The app runs locally in Docker and produces interactive news analysis pages
(sample pages with opinion spectrums, fact cross-referencing, outlet blind
spots). These need to be published read-only on the production WordPress site
at alaskafamilysystems.com, which uses Elementor Pro with a Hello Elementor
child theme.

Key constraints:
- The WordPress site is a production business site — zero tolerance for
  breakage or side effects on existing pages.
- Content includes inline CSS, JavaScript, and interactive DOM manipulation
  (tabs, scroll navigation, outlet picker, timeline dots).
- The user manages publishing from the local app's UI — no manual WP admin
  interaction required for routine push/redact operations.
- All state must persist in the bind-mounted `instance/` volume, surviving
  container rebuilds.

## Decision

Push rendered HTML to WordPress via the WP REST API, using base64 encoding to
bypass WordPress content filters, rendered inside the site's existing
Elementor theme chrome.

## Alternatives Considered

### 1. rsync to static subdirectory

Push self-contained HTML files to a `/demos/` subdirectory on the WP server
via rsync over SSH.

**Pros:** Full rendering control, no WordPress content filter interference,
byte-for-byte fidelity between local and published.

**Cons:** Requires SSH access from Docker container, published pages live
outside WordPress (no theme chrome, no GA integration without extra work,
visually disconnected from the AFS site). Would need a separate auth/transport
mechanism (SSH keys in the container).

**Why rejected:** The visual disconnect between a standalone dark-themed site
and the AFS brand was unacceptable. The user wanted pages to render inside the
AFS header/footer.

### 2. WordPress REST API with light theme

Push content via WP REST API, restyle the app's CSS for a light theme matching
the AFS site palette.

**Pros:** Content lives inside WordPress, inherits theme chrome.

**Cons:** WordPress's `wpautop` filter corrupts multi-line HTML, CSS, and
JavaScript by injecting `<p>` and `<br>` tags. Theme CSS collisions required
extensive scoping. The light theme never looked right — cards were invisible
against the warm white background, colors didn't match, and every fix created
a new visual regression.

**Why rejected:** After four iterations of light theme attempts, the dark
theme inside AFS chrome produced a better visual result with zero CSS
collision issues.

### 3. WordPress plugin with custom template

A small PHP plugin (~15 lines) that registers a page template and either
disables `wpautop` or outputs content via `echo $post->post_content` directly,
bypassing all WordPress content filters.

**Pros:** Clean solution to the wpautop problem. No base64 encoding needed.

**Cons:** Requires plugin installation on the production WP site. Any plugin
is an ongoing maintenance liability on a production site — WP updates could
break it, security audits flag it, and the user has to remember it exists.

**Why rejected:** The base64 encoding approach achieves the same result
(bypassing wpautop) without any server-side changes. Zero footprint on the
WordPress installation.

### 4. Elementor HTML widget via `_elementor_data`

Push content into Elementor's internal JSON format as an HTML widget.

**Pros:** Content renders through Elementor's layout engine.

**Cons:** The `_elementor_data` JSON format is internal, undocumented, and
changes between Elementor versions. Script tags inside the HTML widget are
stripped by Elementor's rendering pipeline. If anyone opens the page in
Elementor's editor, it overwrites the data.

**Why rejected:** Too fragile, strips JavaScript, undocumented API.

## Implementation

### Content Encoding Strategy

WordPress's `wpautop` filter converts blank lines to `<p>` tags and newlines
to `<br>` tags in `the_content()` output. This corrupts CSS, HTML structure,
and JavaScript. Three layers of mitigation were tried:

1. **CSS minification** — collapsing CSS to a single line prevents `<p>`
   injection inside `<style>` blocks. Works reliably.

2. **HTML blank line collapse** — removing blank lines from HTML. Partially
   effective but `wpautop` still wraps certain elements in `<p>` tags.

3. **Base64 encoding** (adopted) — the entire HTML content and all JavaScript
   is base64-encoded and decoded client-side. `wpautop` cannot corrupt content
   inside a base64 string. The decode uses `TextDecoder` for UTF-8 safety:
   ```js
   new TextDecoder().decode(Uint8Array.from(atob("..."), c=>c.charCodeAt(0)))
   ```
   Raw `atob()` only handles Latin-1 and mangles multi-byte UTF-8 characters
   (em-dashes, multiplication signs, smart quotes).

### DOM Structure on WordPress

The final content pushed to each WP page is:

```html
<style>/* minified CSS */</style>
<div class="demos" data-theme="dark" id="demos-root"
     style="width:100vw;margin-left:calc(-50vw + 50%);">
  <script>eval(new TextDecoder().decode(Uint8Array.from(
    atob("...combined base64 blob..."),
    c=>c.charCodeAt(0)
  )))</script>
</div>
```

The single `<script>` inside the `.demos` div prevents `wpautop` from
wrapping scripts in `<p>` tags (which created a visible white gap between the
AFS header and the dark content area).

The combined base64 blob contains:
1. HTML injection: `document.getElementById("demos-root").innerHTML = ...`
2. Timeline JS (scroll, dot positioning, date scale)
3. App JS (opinion cards, outlet picker, blind spots, scroll navigation)
4. Sticky nav positioning fix for Elementor header
5. URL map for timeline dot navigation

### CSS Isolation

All CSS rules are scoped under `.demos` (e.g. `.demos h1`, `.demos .card`).
This prevents collisions with Hello Elementor's reset.css and theme.css which
set global styles on `body`, `h1-h6`, `a`, `table`, `button`, etc.

The `.demos` div does NOT use `all: initial` (attempted and rejected — it
nuked too many inherited properties including `display`, `font`, and line
height, breaking the layout).

### Elementor Integration

- **Template:** `elementor_header_footer` — built into Hello Elementor.
  Renders the site header and footer with full-width content between them.
  No sidebar.
- **Meta:** `_elementor_edit_mode: ""` — tells Elementor this is NOT an
  Elementor-built page. WordPress renders the raw `post_content` through its
  standard template system.
- **Sticky nav:** The app's sticky section nav (`position: sticky; top: 0`)
  conflicts with Elementor's sticky site header (also `top: 0`). Fix:
  switch to `position: fixed` on published pages, measure the Elementor
  sticky header's bottom edge at runtime via
  `querySelectorAll('[data-settings*="sticky"]')`, and position the nav
  below it. Width matched to `<main>` element via `getBoundingClientRect()`
  on load and resize.
- **Full-width dark background:** `width: 100vw; margin-left: calc(-50vw + 50%)`
  breaks out of Elementor's 1200px content container so the dark background
  spans edge to edge. Content inside `<main>` is constrained to 780px via
  the existing CSS rule.

### Content Stripping for Public Consumption

Admin-only elements are stripped by regex in `_extract_wp_content()` and
`_extract_index_content()`:

| Element | Regex target |
|---|---|
| Danger zone (delete buttons) | `<details><summary>Danger zone</summary>...` |
| Resume/Analyze/Delete forms | `<form action=".../(resume\|analyze\|delete)"...` |
| Sample/Settings/Backfill forms | `<form action=".../(sample\|settings\|backfill)"...` |
| Status polling badges | `<span class="badge badge-yellow" id="status-badge">...` |
| Status polling JS | Scripts containing `/api/status` or `/api/stories` |
| Theme toggle | Scripts containing `toggleTheme` or `localStorage` |
| "Track a new story" card | Full card block containing `<h3>Track a new story</h3>` |
| "Sample all" button | `<form action="/sample-all">...` |

### Link Rewriting

Local URLs are rewritten to WordPress permalinks:

| Local pattern | WordPress URL |
|---|---|
| `/story/{id}/samples/{sid}` | `/research/news-reader/demos-{topic-slug}-{YYYYMMDD}/` |
| `/story/{id}` (backlink) | `/research/news-reader/` |
| Timeline dot JS: `'/story/' + dot.dataset.story + '/samples/' + dot.dataset.sample` | Injected URL map lookup: `_u = ({...})[dot.dataset.sample]` |

The timeline dot rewrite is the trickiest because the URL is built dynamically
in JavaScript via string concatenation. A static regex can't match variable
names, so a JSON URL map is injected into the JS at export time, keyed by
sample ID.

### Sync State

`instance/publish_manifest.json` tracks:

```json
{
  "stories": {
    "story_id": {
      "wp_page_id": 456,
      "content_hash": "sha256_prefix",
      "published_at": "ISO",
      "samples": {
        "sample_id": {
          "wp_page_id": 789,
          "content_hash": "sha256_prefix",
          "published_at": "ISO"
        }
      }
    }
  }
}
```

- `wp_page_id` enables idempotent updates (PUT to existing page) and
  targeted deletes.
- `content_hash` (SHA-256 prefix of rendered HTML) detects stale pages in
  the dashboard.
- The manifest is gitignored and lives in the bind-mounted `instance/` volume.

### WP Page Hierarchy

```
/research/                         (existing WP page, ID 1653)
  /research/news-reader/           (landing page, ID 4111, parent_page_id in config)
    /research/news-reader/methodology/
    /research/news-reader/demos-us-iran-relations-20260228/
    /research/news-reader/demos-us-iran-relations-20260307/
    ...
```

### Self-Request Deadlock

Publish routes fetch pages from the local FastAPI server (`localhost:8000`)
to get the rendered HTML. If these routes are `async`, the sync `httpx.get()`
call blocks the event loop, preventing the server from processing the internal
GET request — deadlock.

Fix: all publish/redact routes are `def` (sync), not `async def`. FastAPI
runs them in a threadpool, leaving the event loop free to handle the internal
request.

## Consequences

### Positive
- Zero footprint on WordPress — no plugins, no theme modifications, no
  database schema changes. The only artifacts are standard WP pages.
- Content renders inside the AFS theme chrome (header, footer, navigation)
  while maintaining complete CSS isolation.
- Idempotent sync — safe to click repeatedly. Updates existing pages, never
  creates duplicates.
- Local deletes auto-redact from WordPress.
- All state persists in the `instance/` volume.

### Negative
- Base64 encoding increases content size by ~33%. A 120KB page becomes
  ~160KB. Acceptable for the current scale but would matter at thousands
  of pages.
- `eval()` of decoded content is a security consideration. Acceptable because
  we control both the encoding and decoding, and the content is our own
  rendered HTML/JS. An attacker would need write access to the WP page (which
  means they already have WP admin access).
- Content is not indexable by search engines in the traditional sense — the
  HTML is injected client-side via JavaScript. Google's crawler handles JS
  rendering but other crawlers may not.
- If WordPress changes `wpautop` behavior or Elementor changes its sticky
  header implementation, the encoding/positioning workarounds may need
  updating.
- The regex-based content stripping is brittle — any template change that
  alters the HTML structure of admin elements may require updating the
  corresponding regex in `publish.py`.
