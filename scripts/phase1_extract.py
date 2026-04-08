import json, asyncio, logging
from pathlib import Path
from datetime import datetime, timezone
from claude_agent_sdk import query, ClaudeAgentOptions

DATA = Path("/instance")
log = logging.getLogger(__name__)

SEARCH_TOOLS = ["WebSearch", "WebFetch", "Read", "Write", "Bash"]
ANALYSIS_TOOLS = ["Read", "Write"]

SEARCH_PROMPT = """You are a news collection agent.

TOPIC: {topic}
BIAS DATA: /instance/allsides_bias.csv
OUTPUT DIR: {article_dir}

1. Read the AllSides bias CSV to understand the available outlet ratings.

2. Search the web for exactly {article_count} recent news articles on this topic.
   Prioritize outlet diversity across the political spectrum using the
   AllSides ratings as a guide. Include left-leaning, right-leaning,
   centrist, and wire service sources. Do not exceed {article_count} articles.

3. For each article found:
   a. Fetch the full text.
   b. Save extracted text to {article_dir}/{{url_slug}}.txt
   c. Skip articles under 200 words after extraction.

4. Write a JSON manifest to {manifest_path}:
   {{
     "topic": "{topic}",
     "collected_at": "ISO 8601",
     "articles": [
       {{
         "url": "string",
         "outlet": "string",
         "file": "filename.txt",
         "word_count": number
       }}
     ]
   }}

Collect as many articles as possible. Do not analyze them."""


async def run_story(story: dict, on_message=None):
    story_dir = DATA / "stories" / story["id"]
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    sample_dir = story_dir / "samples" / ts
    phase1_dir = sample_dir / "phase1"
    article_dir = story_dir / "articles"
    for d in (phase1_dir, article_dir):
        d.mkdir(parents=True, exist_ok=True)

    manifest_path = str(sample_dir / "manifest.json")

    article_count = story.get("article_count", 6)
    search_prompt = SEARCH_PROMPT.format(
        topic=story["topic"],
        article_dir=str(article_dir),
        manifest_path=manifest_path,
        article_count=article_count,
    )
    search_options = ClaudeAgentOptions(
        allowed_tools=SEARCH_TOOLS,
        permission_mode="bypassPermissions",
        model="claude-sonnet-4-6",
        cwd="/instance",
    )
    try:
        async for msg in query(prompt=search_prompt, options=search_options):
            if on_message:
                on_message(msg)
    except Exception:
        import shutil
        shutil.rmtree(sample_dir, ignore_errors=True)
        raise

    if not Path(manifest_path).exists():
        import shutil
        shutil.rmtree(sample_dir, ignore_errors=True)
        raise FileNotFoundError(f"Agent did not produce manifest at {manifest_path}")

    manifest = json.loads(Path(manifest_path).read_text())
    articles = manifest.get("articles", [])
    log.info(f"Collected {len(articles)} articles, analyzing each")
    prompt_template = Path("/app/prompts/extract_article.md").read_text()

    for i, article in enumerate(articles):
        article_file = article_dir / article["file"]
        if not article_file.exists():
            continue
        article_text = article_file.read_text()
        if len(article_text.split()) < 200:
            continue

        log.info(f"  [{i+1}/{len(articles)}] {article.get('outlet', '?')}")
        output_path = phase1_dir / article["file"].replace(".txt", ".json")
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
        async for msg in query(prompt=analysis_prompt, options=analysis_options):
            if on_message:
                on_message(msg)

        if output_path.exists():
            data = json.loads(output_path.read_text())
            data["_outlet"] = article["outlet"]
            data["_url"] = article["url"]
            output_path.write_text(json.dumps(data, indent=2))

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
