import re
import json
import httpx
from pathlib import Path
from base64 import b64encode

DATA = Path("/instance")
ENV_PATH = DATA / "publish_config.json"
LOCAL_URL = "http://localhost:8000"


def _load_config() -> dict:
    if ENV_PATH.exists():
        return json.loads(ENV_PATH.read_text())
    raise FileNotFoundError(f"{ENV_PATH} not found. Create it with wp_url, wp_user, wp_password, parent_page_id.")


def _auth_headers(config: dict) -> dict:
    token = b64encode(f"{config['wp_user']}:{config['wp_password']}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


def test_connection() -> dict:
    config = _load_config()
    headers = _auth_headers(config)
    resp = httpx.get(f"{config['wp_url']}/wp-json/wp/v2/users/me",
                     headers=headers, timeout=15)
    if resp.status_code == 200:
        return {"ok": True, "user": resp.json().get("name")}
    return {"ok": False, "error": resp.text[:200]}


def _fetch_page(path: str) -> str:
    resp = httpx.get(f"{LOCAL_URL}{path}", timeout=30)
    resp.raise_for_status()
    return resp.text


def _extract_wp_content(html: str) -> str:
    # Extract all <style> blocks and minify
    styles = re.findall(r"<style[^>]*>(.*?)</style>", html, re.DOTALL)
    minified_css = " ".join(
        line.strip() for css in styles for line in css.splitlines() if line.strip()
    )

    # Extract .demos wrapper contents
    demos_match = re.search(
        r'<div class="demos"[^>]*>(.*?)</div>\s*</body>', html, re.DOTALL)
    if not demos_match:
        raise ValueError("Could not find .demos wrapper")
    inner = demos_match.group(1)

    # Strip nav (WP theme provides it)
    inner = re.sub(r"<nav>.*?</nav>", "", inner, flags=re.DOTALL)
    # Strip theme toggle script
    inner = re.sub(r"<script>\s*function toggleTheme.*?</script>", "", inner, flags=re.DOTALL)
    # Strip admin-only elements
    inner = re.sub(
        r'<div class="section"[^>]*>\s*<details>\s*<summary[^>]*>Danger zone</summary>.*?</details>\s*</div>',
        "", inner, flags=re.DOTALL)
    inner = re.sub(r'<form[^>]*action="[^"]*/(resume|analyze|delete)".*?</form>', "", inner, flags=re.DOTALL)
    inner = re.sub(r'<form[^>]*action="[^"]*/(sample|settings|backfill)".*?</form>', "", inner, flags=re.DOTALL)
    # Strip status badges and sample buttons
    inner = re.sub(r'<span class="badge badge-yellow" id="status-badge">.*?</span>', "", inner, flags=re.DOTALL)
    # Rewrite story backlinks to point to the WP landing page
    inner = re.sub(r'href="/story/[a-f0-9]+"', 'href="/research/news-reader/"', inner)

    # Separate scripts from HTML
    html_only = re.sub(r"<script>.*?</script>", "", inner, flags=re.DOTALL).strip()

    # Collect app scripts (exclude admin polling)
    all_scripts = re.findall(r"<script>(.*?)</script>", html, re.DOTALL)
    app_scripts = [
        s for s in all_scripts
        if "/api/status" not in s
        and "/api/stories" not in s
        and "toggleTheme" not in s
        and "localStorage" not in s
    ]

    # Strip admin-only HTML sections
    html_only = re.sub(
        r'<div class="section"[^>]*style="margin-top:48px;">\s*<details>.*?</details>\s*</div>',
        "", html_only, flags=re.DOTALL)

    # Rewrite local links to WP URLs
    html_only = _rewrite_local_links(html_only)

    # Base64 encode HTML and JS to bypass wpautop.
    # atob() only handles Latin-1, so use TextEncoder/Decoder for UTF-8 safety.
    html_b64 = b64encode(html_only.encode("utf-8")).decode()
    all_js = (
        f'document.getElementById("demos-root").innerHTML='
        f'new TextDecoder().decode(Uint8Array.from(atob("{html_b64}"),'
        f'c=>c.charCodeAt(0)));\n'
    )
    # Build a sample URL map for timeline dot navigation
    from scripts.publish_state import load_manifest
    manifest = load_manifest()
    stories_data = json.loads((DATA / "stories.json").read_text())
    url_map = {}
    for sid_key, story_data in manifest.get("stories", {}).items():
        s_meta = next((s for s in stories_data if s["id"] == sid_key), None)
        topic_slug = _slugify(s_meta["topic"]) if s_meta else "story"
        for sample_id in story_data.get("samples", {}):
            date_slug = sample_id[:8]
            url_map[sample_id] = f"/research/news-reader/demos-{topic_slug}-{date_slug}/"
    url_map_json = json.dumps(url_map)

    for s in app_scripts:
        # Replace dynamic timeline navigation with WP URL lookup
        s = s.replace(
            "window.location.href = '/story/' + dot.dataset.story + '/samples/' + dot.dataset.sample;",
            f"var _u = ({url_map_json})[dot.dataset.sample]; if (_u) window.location.href = _u;"
        )
        s = _rewrite_local_links(s)
        all_js += s + "\n"
    # Fix sticky nav to sit below AFS site header.
    # Elementor applies sticky dynamically, so we measure the actual header
    # bottom on scroll rather than checking computed styles at load time.
    all_js += """
(function() {
    var nav = document.querySelector('.demos .flow-nav');
    if (!nav) return;
    var demos = document.getElementById('demos-root');
    if (!demos) return;
    // Switch from sticky to fixed positioning for WP embed
    var main = demos.querySelector('main');
    nav.style.position = 'fixed';
    nav.style.margin = '0';
    function matchWidth() {
        if (main) {
            var r = main.getBoundingClientRect();
            nav.style.left = r.left + 'px';
            nav.style.width = r.width + 'px';
        } else {
            nav.style.left = '0';
            nav.style.right = '0';
        }
    }
    matchWidth();
    window.addEventListener('resize', matchWidth);
    // Find the Elementor sticky header (blue nav bar)
    function getHeaderBottom() {
        var els = document.querySelectorAll('[data-settings*="sticky"], [class*="elementor-sticky"]');
        var maxB = 0;
        els.forEach(function(el) {
            var r = el.getBoundingClientRect();
            if (r.bottom > 0 && r.bottom < 300) maxB = Math.max(maxB, r.bottom);
        });
        return maxB || 0;
    }
    var origScroll = window.addEventListener ? window.onscroll : null;
    window.addEventListener('scroll', function() {
        nav.style.top = getHeaderBottom() + 'px';
    });
    // Initial position
    setTimeout(function() { nav.style.top = getHeaderBottom() + 'px'; }, 500);
})();
"""
    combined_b64 = b64encode(all_js.encode("utf-8")).decode()

    parts = [f"<style>{minified_css}</style>"]
    parts.append(
        '<div class="demos" data-theme="dark" id="demos-root"'
        ' style="width:100vw;margin-left:calc(-50vw + 50%);padding:32px 24px;">'
        f'<script>eval(new TextDecoder().decode(Uint8Array.from(atob("{combined_b64}"),'
        f'c=>c.charCodeAt(0))))</script>'
        '</div>'
    )
    return "\n".join(parts)


def _find_page_by_slug(slug: str, config: dict, headers: dict) -> int | None:
    resp = httpx.get(
        f"{config['wp_url']}/wp-json/wp/v2/pages",
        params={"slug": slug, "status": "publish,draft"},
        headers=headers, timeout=15)
    pages = resp.json()
    if pages and isinstance(pages, list):
        return pages[0]["id"]
    return None


def push_page(slug: str, title: str, content: str,
              parent_id: int = None, existing_wp_id: int = None) -> int:
    config = _load_config()
    headers = _auth_headers(config)

    page_data = {
        "title": title,
        "content": content,
        "status": "publish",
        "slug": slug,
        "template": "elementor_header_footer",
        "meta": {"_elementor_edit_mode": ""},
    }
    if parent_id:
        page_data["parent"] = parent_id

    # Update existing page or create new
    wp_id = existing_wp_id or _find_page_by_slug(slug, config, headers)
    if wp_id:
        resp = httpx.post(
            f"{config['wp_url']}/wp-json/wp/v2/pages/{wp_id}",
            json=page_data, headers=headers, timeout=120)
    else:
        resp = httpx.post(
            f"{config['wp_url']}/wp-json/wp/v2/pages",
            json=page_data, headers=headers, timeout=120)

    if resp.status_code in (200, 201):
        return resp.json()["id"]
    raise RuntimeError(f"WP push failed ({resp.status_code}): {resp.text[:300]}")


def delete_page(wp_page_id: int):
    config = _load_config()
    headers = _auth_headers(config)
    resp = httpx.delete(
        f"{config['wp_url']}/wp-json/wp/v2/pages/{wp_page_id}?force=true",
        headers=headers, timeout=15)
    if resp.status_code not in (200, 404):
        raise RuntimeError(f"WP delete failed ({resp.status_code}): {resp.text[:300]}")


def publish_sample(story_id: str, sample_id: str,
                   story_topic: str, existing_wp_id: int = None) -> tuple[int, str]:
    """Render a sample page, push to WP, return (wp_page_id, content_hash)."""
    from scripts.publish_state import content_hash, load_manifest

    html = _fetch_page(f"/story/{story_id}/samples/{sample_id}")
    wp_content = _extract_wp_content(html)
    h = content_hash(wp_content)

    config = _load_config()
    parent_id = config.get("parent_page_id")

    date_slug = sample_id[:8]
    slug = f"demos-{_slugify(story_topic)}-{date_slug}"
    title = f"{story_topic} — {date_slug[:4]}-{date_slug[4:6]}-{date_slug[6:8]}"

    wp_id = push_page(slug, title, wp_content, parent_id, existing_wp_id)
    return wp_id, h


def publish_story(story_id: str) -> dict:
    """Publish a story and all its analyzed samples. Returns sync results."""
    from scripts.publish_state import (
        load_manifest, save_manifest, content_hash, mark_sample_published)

    stories = json.loads((DATA / "stories.json").read_text())
    story = next((s for s in stories if s["id"] == story_id), None)
    if not story:
        raise ValueError(f"Story {story_id} not found")

    manifest = load_manifest()
    story_entry = manifest["stories"].get(story_id, {"samples": {}})
    config = _load_config()
    results = {"published": [], "skipped": [], "errors": []}

    # Find all analyzed samples
    samples_dir = DATA / "stories" / story_id / "samples"
    if not samples_dir.exists():
        return results
    sample_ids = sorted(d.name for d in samples_dir.iterdir() if d.is_dir())
    analyzed = [
        sid for sid in sample_ids
        if (samples_dir / sid / "phase4.json").exists()
        or (samples_dir / sid / "phase3.json").exists()
    ]

    for sid in analyzed:
        existing = story_entry.get("samples", {}).get(sid, {})
        existing_wp_id = existing.get("wp_page_id")
        try:
            wp_id, h = publish_sample(
                story_id, sid, story["topic"], existing_wp_id)
            mark_sample_published(story_id, sid, wp_id, h)
            if existing_wp_id:
                results["skipped" if existing.get("content_hash") == h else "published"].append(sid)
            else:
                results["published"].append(sid)
        except RuntimeError as e:
            results["errors"].append({"sample": sid, "error": str(e)})

    # Clean up samples that were deleted locally but still published
    for sid, info in list(story_entry.get("samples", {}).items()):
        if sid not in sample_ids and info.get("wp_page_id"):
            try:
                delete_page(info["wp_page_id"])
                from scripts.publish_state import mark_redacted
                mark_redacted(story_id, sid)
                results["published"].append(f"{sid} (redacted)")
            except RuntimeError as e:
                results["errors"].append({"sample": sid, "error": str(e)})

    # Update story-level manifest entry
    manifest = load_manifest()
    if story_id not in manifest["stories"]:
        manifest["stories"][story_id] = {"samples": {}}
    manifest["stories"][story_id]["published_at"] = (
        __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat())
    from scripts.publish_state import save_manifest
    save_manifest(manifest)

    # Re-push the index page so timeline dots and links are current
    try:
        publish_index()
    except Exception as e:
        results["errors"].append({"sample": "index", "error": str(e)})

    return results


def redact_story(story_id: str):
    """Delete all published pages for a story."""
    from scripts.publish_state import load_manifest, mark_redacted

    manifest = load_manifest()
    story = manifest["stories"].get(story_id)
    if not story:
        return
    for sid, info in story.get("samples", {}).items():
        if info.get("wp_page_id"):
            try:
                delete_page(info["wp_page_id"])
            except RuntimeError:
                pass
    if story.get("wp_page_id"):
        try:
            delete_page(story["wp_page_id"])
        except RuntimeError:
            pass
    mark_redacted(story_id)


def redact_sample(story_id: str, sample_id: str):
    """Delete a single published sample page."""
    from scripts.publish_state import load_manifest, mark_redacted

    manifest = load_manifest()
    story = manifest["stories"].get(story_id)
    if not story:
        return
    sample = story.get("samples", {}).get(sample_id)
    if sample and sample.get("wp_page_id"):
        delete_page(sample["wp_page_id"])
    mark_redacted(story_id, sample_id)


def _rewrite_local_links(html: str) -> str:
    """Rewrite local /story/ID/samples/SID links to published WP URLs."""
    from scripts.publish_state import load_manifest
    manifest = load_manifest()
    config = _load_config()

    def _replace_sample_link(m):
        story_id = m.group(1)
        sample_id = m.group(2)
        story = manifest["stories"].get(story_id, {})
        sample = story.get("samples", {}).get(sample_id, {})
        wp_id = sample.get("wp_page_id")
        if wp_id:
            # Use the WP permalink pattern
            topic = "news"
            stories = json.loads((DATA / "stories.json").read_text())
            s = next((s for s in stories if s["id"] == story_id), None)
            if s:
                topic = _slugify(s["topic"])
            date_slug = sample_id[:8]
            parent_slug = "research/news-reader"
            return f"/{parent_slug}/demos-{topic}-{date_slug}/"
        return m.group(0)

    # Rewrite sample links everywhere (href, onclick, JS strings)
    html = re.sub(
        r"/story/([a-f0-9]+)/samples/(\d{8}T\d{6})",
        _replace_sample_link, html)

    # Rewrite story detail links to point to latest published sample
    def _replace_story_link(m):
        story_id = m.group(1)
        attrs = m.group(2)
        text = m.group(3)
        story = manifest["stories"].get(story_id, {})
        samples = story.get("samples", {})
        if samples:
            latest_sid = sorted(samples.keys())[-1]
            stories_data = json.loads((DATA / "stories.json").read_text())
            s = next((s for s in stories_data if s["id"] == story_id), None)
            topic = _slugify(s["topic"]) if s else "story"
            date_slug = latest_sid[:8]
            return f'<a href="/research/news-reader/demos-{topic}-{date_slug}/"{attrs}>{text}</a>'
        return text  # No published samples, strip link

    html = re.sub(
        r'<a href="/story/([a-f0-9]+)"([^>]*)>(.*?)</a>',
        _replace_story_link, html)
    return html


def publish_index():
    """Push the Stories index page as content of the landing page (page 4111)."""
    config = _load_config()
    parent_id = config.get("parent_page_id")
    if not parent_id:
        raise ValueError("parent_page_id not set in publish_config.json")

    html = _fetch_page("/")
    wp_content = _extract_index_content(html)
    push_page("news-reader", "News Reader", wp_content, existing_wp_id=parent_id)


def _extract_index_content(html: str) -> str:
    """Extract the Stories index page for WP, stripping admin controls."""
    styles = re.findall(r"<style[^>]*>(.*?)</style>", html, re.DOTALL)
    minified_css = " ".join(
        line.strip() for css in styles for line in css.splitlines() if line.strip()
    )

    demos_match = re.search(
        r'<div class="demos"[^>]*>(.*?)</div>\s*</body>', html, re.DOTALL)
    if not demos_match:
        raise ValueError("Could not find .demos wrapper")
    inner = demos_match.group(1)

    # Strip nav, theme toggle
    inner = re.sub(r"<nav>.*?</nav>", "", inner, flags=re.DOTALL)
    inner = re.sub(r"<script>\s*function toggleTheme.*?</script>", "", inner, flags=re.DOTALL)
    # Strip admin controls: "Track a new story" entire card block
    inner = re.sub(r'<div class="card"[^>]*>\s*<h3[^>]*>Track a new story</h3>.+?</form>\s*</div>', "", inner, flags=re.DOTALL)
    inner = re.sub(r'<form[^>]*action="/sample-all"[^>]*>.*?</form>', "", inner, flags=re.DOTALL)
    inner = re.sub(r'<form[^>]*action="/stories/[^"]*sample"[^>]*>.*?</form>', "", inner, flags=re.DOTALL)
    # Strip status badges and polling
    inner = re.sub(r'<span class="badge badge-yellow"[^>]*>.*?</span>', "", inner, flags=re.DOTALL)

    # Separate scripts (only keep non-admin ones)
    all_scripts = re.findall(r"<script>(.*?)</script>", html, re.DOTALL)
    app_scripts = [
        s for s in all_scripts
        if "/api/status" not in s
        and "toggleTheme" not in s
        and "localStorage" not in s
        and "data-story-status" not in s
    ]

    html_only = re.sub(r"<script>.*?</script>", "", inner, flags=re.DOTALL).strip()

    # Rewrite local links to WP URLs
    html_only = _rewrite_local_links(html_only)

    html_b64 = b64encode(html_only.encode("utf-8")).decode()
    all_js = (
        f'document.getElementById("demos-root").innerHTML='
        f'new TextDecoder().decode(Uint8Array.from(atob("{html_b64}"),'
        f'c=>c.charCodeAt(0)));\n'
    )
    for s in app_scripts:
        all_js += s + "\n"
    combined_b64 = b64encode(all_js.encode("utf-8")).decode()

    parts = [f"<style>{minified_css}</style>"]
    parts.append(
        '<div class="demos" data-theme="dark" id="demos-root"'
        ' style="width:100vw;margin-left:calc(-50vw + 50%);padding:32px 24px;">'
        f'<script>eval(new TextDecoder().decode(Uint8Array.from(atob("{combined_b64}"),'
        f'c=>c.charCodeAt(0))))</script>'
        '</div>'
    )
    return "\n".join(parts)


def publish_methodology():
    """Push the Methodology page as a child of the landing page."""
    config = _load_config()
    parent_id = config.get("parent_page_id")

    html = _fetch_page("/methodology")
    wp_content = _extract_wp_content(html)

    push_page("methodology", "Methodology", wp_content, parent_id)


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]
