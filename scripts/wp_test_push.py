"""Push a test draft page to WordPress to preview theme integration.

Grabs a real sample page from the local FastAPI server, extracts styles +
HTML + scripts, base64-encodes the HTML to bypass wpautop corruption, and
POSTs as a draft page using the elementor_header_footer template.

Usage: uv run --with httpx scripts/wp_test_push.py
"""

import re
import json
import httpx
from pathlib import Path
from base64 import b64encode

ENV_FILE = Path("/Users/patrick/demos/.env")
LOCAL_URL = "http://localhost:8000"
STORY_ID = "a0829f0c"
SAMPLE_ID = "20260414T204055"


def load_env():
    env = {}
    for line in ENV_FILE.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def fetch_local_page():
    url = f"{LOCAL_URL}/story/{STORY_ID}/samples/{SAMPLE_ID}"
    resp = httpx.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def extract_content(html):
    # Extract all <style> blocks and minify
    styles = re.findall(r"<style[^>]*>(.*?)</style>", html, re.DOTALL)
    minified_css = " ".join(
        line.strip() for css in styles for line in css.splitlines() if line.strip()
    )

    # Extract the .demos wrapper contents
    demos_match = re.search(
        r'<div class="demos"[^>]*>(.*?)</div>\s*</body>',
        html,
        re.DOTALL,
    )
    if not demos_match:
        raise ValueError("Could not find .demos wrapper")
    inner = demos_match.group(1)

    # Strip <nav> (WP theme provides navigation), keep <main> for content width
    inner = re.sub(r"<nav>.*?</nav>", "", inner, flags=re.DOTALL)
    # Strip admin-only elements
    inner = re.sub(
        r'<div class="section"[^>]*>\s*<details>\s*<summary[^>]*>Danger zone</summary>.*?</details>\s*</div>',
        "", inner, flags=re.DOTALL,
    )
    inner = re.sub(r'<form[^>]*action="[^"]*/(resume|analyze|delete)".*?</form>', "", inner, flags=re.DOTALL)
    inner = re.sub(r'<form[^>]*action="[^"]*/(sample|settings|backfill)".*?</form>', "", inner, flags=re.DOTALL)

    # Separate inline scripts from HTML structure
    script_blocks = re.findall(r"<script>(.*?)</script>", inner, re.DOTALL)
    html_only = re.sub(r"<script>.*?</script>", "", inner, flags=re.DOTALL).strip()

    # Also grab scripts from outside .demos (the main app JS)
    all_scripts = re.findall(r"<script>(.*?)</script>", html, re.DOTALL)
    # Filter out admin-only scripts (status polling, log polling)
    app_scripts = [
        s for s in all_scripts
        if "/api/status" not in s and "/api/stories" not in s
    ]

    # Strip admin-only sections
    html_only = re.sub(
        r'<div class="section"[^>]*style="margin-top:48px;">\s*<details>.*?</details>\s*</div>',
        "",
        html_only,
        flags=re.DOTALL,
    )

    # Base64 encode the HTML to bypass wpautop entirely
    html_b64 = b64encode(html_only.encode()).decode()

    # Build a single self-executing script that:
    # 1. Injects the HTML into the container
    # 2. Runs all app JS (timeline, scroll, data rendering)
    # Everything lives inside .demos so wpautop can't wrap scripts in <p>
    all_js_combined = f'document.getElementById("demos-root").innerHTML=atob("{html_b64}");\n'
    for s in app_scripts:
        all_js_combined += s + "\n"
    combined_b64 = b64encode(all_js_combined.encode()).decode()

    parts = [f"<style>{minified_css}</style>"]
    # Single div with one inline script — nothing outside for wpautop to wrap
    parts.append(
        '<div class="demos" data-theme="dark" id="demos-root"'
        ' style="width:100vw;margin-left:calc(-50vw + 50%);padding:32px 24px;">'
        f'<script>eval(atob("{combined_b64}"))</script>'
        '</div>'
    )

    return "\n".join(parts)


def push_draft(content, wp_url, wp_user, wp_password):
    auth = b64encode(f"{wp_user}:{wp_password}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}

    me_resp = httpx.get(
        f"{wp_url}/wp-json/wp/v2/users/me", headers=headers, timeout=15
    )
    if me_resp.status_code != 200:
        print(f"Auth failed: {me_resp.status_code}")
        print(me_resp.text[:500])
        return None
    print(f"Authenticated as: {me_resp.json().get('name')}")

    page_data = {
        "title": "Demos Test — US-Iran Relations Sample",
        "content": content,
        "status": "draft",
        "slug": "demos-test-page",
        "template": "elementor_header_footer",
        "meta": {"_elementor_edit_mode": ""},
    }

    resp = httpx.post(
        f"{wp_url}/wp-json/wp/v2/pages",
        json=page_data,
        headers=headers,
        timeout=30,
    )

    if resp.status_code == 201:
        page = resp.json()
        page_id = page["id"]
        print(f"Draft created: ID {page_id}")
        print(f"WP Admin: {wp_url}/wp-admin/post.php?post={page_id}&action=edit")
        return page_id

    print(f"Failed: {resp.status_code}")
    print(resp.text[:500])
    return None


def verify_rendered(page_id, wp_url, wp_user, wp_password):
    """Fetch the rendered content and check for corruption."""
    auth = b64encode(f"{wp_user}:{wp_password}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}"}
    resp = httpx.get(
        f"{wp_url}/wp-json/wp/v2/pages/{page_id}",
        headers=headers,
        timeout=15,
    )
    content = resp.json()["content"]["rendered"]

    # Check CSS is clean
    style_match = re.search(r"<style>(.*?)</style>", content, re.DOTALL)
    css_clean = style_match and "<p>" not in style_match.group(1)

    # Check demos-root exists
    has_root = 'id="demos-root"' in content

    # Check injector script exists and has base64 data
    has_injector = "atob(" in content

    # Check no <p> inside .demos-root (should be empty in raw, filled by JS)
    root_match = re.search(r'id="demos-root"[^>]*>(.*?)</div>', content, re.DOTALL)
    root_clean = root_match and "<p>" not in root_match.group(1)

    # Count app scripts
    script_count = len(re.findall(r"<script>", content))

    print(f"\nVerification:")
    print(f"  CSS clean: {css_clean}")
    print(f"  Root element exists: {has_root}")
    print(f"  Injector script exists: {has_injector}")
    print(f"  Root not corrupted: {root_clean}")
    print(f"  Script tags: {script_count}")

    all_ok = css_clean and has_root and has_injector and root_clean
    print(f"  Overall: {'PASS' if all_ok else 'FAIL'}")
    return all_ok


if __name__ == "__main__":
    env = load_env()
    wp_password = env.get("WORDPRESS_PASSWORD")
    if not wp_password:
        print("WORDPRESS_PASSWORD not found in .env")
        exit(1)

    wp_url = env.get("WORDPRESS_URL", "https://alaskafamilysystems.com")
    wp_user = env.get("WORDPRESS_USER", "patrick@vedanamedia.com")

    print("Fetching sample page from local server...")
    html = fetch_local_page()
    print(f"Got {len(html)} bytes")

    print("Extracting content (base64 encoded HTML, light theme)...")
    content = extract_content(html)
    print(f"Content: {len(content)} bytes")

    print(f"\nPushing draft to {wp_url}...")
    page_id = push_draft(content, wp_url, wp_user, wp_password)

    if page_id:
        verify_rendered(page_id, wp_url, wp_user, wp_password)
