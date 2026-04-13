import json, asyncio, logging, re
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse
import httpx
from claude_agent_sdk import query, ClaudeAgentOptions
from scripts.retryquery import retry_query

DATA = Path("/instance")
log = logging.getLogger(__name__)

APP_DIR = Path(__file__).resolve().parent.parent / "app"

ANALYSIS_TOOLS = ["Read", "Write"]


def all_outlets() -> list[str]:
    data = json.loads((APP_DIR / "outlets.json").read_text())
    return [o["outlet"] for o in data] + ["White House"]


SEARCH_PROMPT = """You are a news URL finder.

TOPIC: {topic}

TARGET OUTLETS (find one article URL per outlet):
{outlet_list}

For each target outlet, search the web for one article on this topic
published {date_instruction}. For "White House", search whitehouse.gov
or state.gov.

If you cannot find an article for an outlet, skip it.

Do NOT fetch or read the articles. Only find URLs.

Respond with ONLY valid JSON matching this schema (no markdown fences):
{{
  "urls": [
    {{"outlet": "string", "url": "string"}}
  ]
}}"""


def _slug(url: str) -> str:
    parts = urlparse(url)
    path = parts.netloc + parts.path
    slug = re.sub(r'[^a-zA-Z0-9]', '-', path).strip('-')[:80]
    return slug or "article"


async def _fetch_articles(urls: list[dict], article_dir: Path,
                          on_log=None) -> tuple[list[dict], list[dict]]:
    """Returns (articles, failed_urls)."""
    articles = []
    failed = []
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for entry in urls:
            outlet = entry["outlet"]
            url = entry["url"]
            slug = _slug(url)
            filename = f"{slug}.txt"
            filepath = article_dir / filename

            if filepath.exists():
                text = filepath.read_text()
                if on_log:
                    on_log(f"[fetch] {outlet} (cached)")
            else:
                try:
                    resp = await client.get(url, headers={
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    })
                    resp.raise_for_status()
                    text = re.sub(r'<script[^>]*>.*?</script>', '', resp.text, flags=re.DOTALL)
                    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
                    text = re.sub(r'<[^>]+>', ' ', text)
                    text = re.sub(r'\s+', ' ', text).strip()
                    filepath.write_text(text)
                    if on_log:
                        on_log(f"[fetch] {outlet} ({len(text.split())} words)")
                except (httpx.HTTPError, httpx.TimeoutException) as e:
                    if on_log:
                        on_log(f"[fetch] {outlet} blocked, queuing for agent fallback")
                    failed.append(entry)
                    continue

            word_count = len(text.split())
            if word_count < 200:
                if on_log:
                    on_log(f"[fetch] {outlet} too short ({word_count} words), queuing for agent")
                filepath.unlink(missing_ok=True)
                failed.append(entry)
                continue

            articles.append({
                "url": url, "outlet": outlet,
                "file": filename, "word_count": word_count,
            })
    return articles, failed


FALLBACK_PROMPT = """Fetch the following article URLs and save each as a text file.
For each URL, fetch the full article text (not just the headline), strip ads
and navigation, and save the clean text.

{url_list}

OUTPUT DIR: {article_dir}

For each article, save to: {article_dir}/{{url_slug}}.txt
Use the URL slug as the filename (replace non-alphanumeric chars with hyphens).
Skip articles under 200 words after extraction."""


async def run_story(story: dict, on_message=None, sample_id: str = None,
                    on_progress=None, target_date: str = None):
    story_dir = DATA / "stories" / story["id"]
    ts = sample_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    sample_dir = story_dir / "samples" / ts
    phase1_dir = sample_dir / "phase1"
    article_dir = sample_dir / "articles"
    for d in (phase1_dir, article_dir):
        d.mkdir(parents=True, exist_ok=True)

    manifest_path = sample_dir / "manifest.json"

    if not manifest_path.exists():
        outlets = all_outlets()
        outlet_list = "\n".join(f"  - {o}" for o in outlets)
        if target_date:
            date_instruction = f"around {target_date} (within a few days of that date)"
        else:
            date_instruction = "within the most recent few days"
        search_prompt = SEARCH_PROMPT.format(
            topic=story["topic"],
            outlet_list=outlet_list,
            date_instruction=date_instruction,
        )
        search_options = ClaudeAgentOptions(
            allowed_tools=["WebSearch"],
            permission_mode="bypassPermissions",
            model="claude-sonnet-4-6",
            cwd="/instance",
        )

        # Agent finds URLs only (no fetching)
        from claude_agent_sdk import AssistantMessage
        from claude_agent_sdk.types import TextBlock
        response_text = ""
        def _capture(msg):
            nonlocal response_text
            if on_message:
                on_message(msg)
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        response_text += block.text
        await retry_query(prompt=search_prompt, options=search_options, on_message=_capture)

        # Parse URL list from agent response
        urls = []
        try:
            # Find JSON in response (may have markdown fences)
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                data = json.loads(json_match.group())
                urls = data.get("urls", [])
        except (json.JSONDecodeError, AttributeError):
            log.warning("Failed to parse URL list from agent response")

        if not urls:
            raise RuntimeError("Agent did not return any article URLs")

        log.info(f"Agent found {len(urls)} URLs, fetching with httpx")

        # Fetch articles with Python (no LLM cost)
        def on_fetch_log(line):
            log.info(f"  {line}")

        articles, failed = await _fetch_articles(urls, article_dir, on_log=on_fetch_log)

        # Fallback: use agent WebFetch for URLs that httpx couldn't get
        if failed:
            log.info(f"  {len(failed)} outlets need agent fallback")
            url_list = "\n".join(f"  - {e['outlet']}: {e['url']}" for e in failed)
            fallback_prompt = FALLBACK_PROMPT.format(
                url_list=url_list, article_dir=str(article_dir),
            )
            fallback_options = ClaudeAgentOptions(
                allowed_tools=["WebFetch", "Write", "Bash"],
                permission_mode="bypassPermissions",
                model="claude-sonnet-4-6",
                cwd="/instance",
            )
            await retry_query(prompt=fallback_prompt, options=fallback_options, on_message=on_message)

            # Check which failed articles now have files
            for entry in failed:
                slug = _slug(entry["url"])
                filepath = article_dir / f"{slug}.txt"
                if filepath.exists():
                    word_count = len(filepath.read_text().split())
                    if word_count >= 200:
                        articles.append({
                            "url": entry["url"], "outlet": entry["outlet"],
                            "file": f"{slug}.txt", "word_count": word_count,
                        })
                        log.info(f"  [fallback] {entry['outlet']} recovered ({word_count} words)")

        manifest = {
            "topic": story["topic"],
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "articles": articles,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2))

    if not manifest_path.exists():
        raise FileNotFoundError(f"Agent did not produce manifest at {manifest_path}")

    manifest = json.loads(manifest_path.read_text())
    articles = manifest.get("articles", [])
    log.info(f"{len(articles)} articles ready, analyzing each")
    prompt_template = Path("/app/prompts/extract_article.md").read_text()

    for i, article in enumerate(articles):
        if on_progress:
            on_progress(i, len(articles))
        output_path = phase1_dir / article["file"].replace(".txt", ".json")
        if output_path.exists():
            log.info(f"  [{i+1}/{len(articles)}] {article.get('outlet', '?')} (cached)")
            continue
        article_file = article_dir / article["file"]
        if not article_file.exists():
            continue
        article_text = article_file.read_text()
        if len(article_text.split()) < 200:
            continue

        log.info(f"  [{i+1}/{len(articles)}] {article.get('outlet', '?')}")
        analysis_prompt = (
            f"{prompt_template}\n\n"
            f"ARTICLE TEXT:\n{article_text}\n\n"
            f"Write your JSON output to {output_path}"
        )
        analysis_options = ClaudeAgentOptions(
            allowed_tools=ANALYSIS_TOOLS,
            permission_mode="bypassPermissions",
            model="claude-sonnet-4-6",
            cwd="/instance",
        )
        await retry_query(prompt=analysis_prompt, options=analysis_options, on_message=on_message)

        if output_path.exists():
            try:
                data = json.loads(output_path.read_text())
                data["_outlet"] = article["outlet"]
                data["_url"] = article["url"]
                output_path.write_text(json.dumps(data, indent=2))
            except json.JSONDecodeError:
                log.warning(f"  [{i+1}/{len(articles)}] {article.get('outlet', '?')} wrote invalid JSON, skipping")
                output_path.unlink(missing_ok=True)

    if on_progress:
        on_progress(len(articles), len(articles))
    story["last_run_at"] = datetime.now(timezone.utc).isoformat()
    story["last_sample"] = ts


async def main():
    stories_path = DATA / "stories.json"
    stories = json.loads(stories_path.read_text())
    for story in [s for s in stories if s.get("active")]:
        print(f"Extracting: {story['topic']}")
        try:
            await run_story(story)
        except Exception as e:
            print(f"  Failed: {e}")
    stories_path.write_text(json.dumps(stories, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
