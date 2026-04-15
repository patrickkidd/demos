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

    # Base64 encode HTML and JS to bypass wpautop
    html_b64 = b64encode(html_only.encode()).decode()
    all_js = f'document.getElementById("demos-root").innerHTML=atob("{html_b64}");\n'
    for s in app_scripts:
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
    combined_b64 = b64encode(all_js.encode()).decode()

    parts = [f"<style>{minified_css}</style>"]
    parts.append(
        '<div class="demos" data-theme="dark" id="demos-root"'
        ' style="width:100vw;margin-left:calc(-50vw + 50%);padding:32px 24px;">'
        f'<script>eval(atob("{combined_b64}"))</script>'
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


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]
