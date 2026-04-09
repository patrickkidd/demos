import json, asyncio, logging
from pathlib import Path
from datetime import datetime, timezone
from claude_agent_sdk import query, ClaudeAgentOptions

DATA = Path("/instance")
log = logging.getLogger(__name__)

SEARCH_TOOLS = ["WebSearch", "WebFetch", "Read", "Write", "Bash"]
ANALYSIS_TOOLS = ["Read", "Write"]

APP_DIR = Path(__file__).resolve().parent.parent / "app"


def all_outlets() -> list[str]:
    data = json.loads((APP_DIR / "outlets.json").read_text())
    return [o["outlet"] for o in data] + ["White House"]


SEARCH_PROMPT = """You are a news collection agent.

TOPIC: {topic}
OUTPUT DIR: {article_dir}

TARGET OUTLETS (one article per outlet, in order of priority):
{outlet_list}

Search for one recent article on this topic from each target outlet.
For "White House", search for official press releases, briefings, or
statements from whitehouse.gov or state.gov.
Fetch exactly one article per outlet. If you cannot find or fetch an
article from a specific outlet, skip it and note the failure. Do not
substitute a different outlet or double up on any outlet.

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


async def run_story(story: dict, on_message=None, sample_id: str = None, on_progress=None):
    story_dir = DATA / "stories" / story["id"]
    ts = sample_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    sample_dir = story_dir / "samples" / ts
    phase1_dir = sample_dir / "phase1"
    article_dir = sample_dir / "articles"
    for d in (phase1_dir, article_dir):
        d.mkdir(parents=True, exist_ok=True)

    manifest_path = sample_dir / "manifest.json"

    # Skip search if manifest already exists (resume scenario)
    if not manifest_path.exists():
        outlets = all_outlets()
        outlet_list = "\n".join(f"  - {o}" for o in outlets)
        search_prompt = SEARCH_PROMPT.format(
            topic=story["topic"],
            article_dir=str(article_dir),
            manifest_path=str(manifest_path),
            outlet_list=outlet_list,
        )
        search_options = ClaudeAgentOptions(
            allowed_tools=SEARCH_TOOLS,
            permission_mode="bypassPermissions",
            model="claude-sonnet-4-6",
            cwd="/instance",
        )
        async for msg in query(prompt=search_prompt, options=search_options):
            if on_message:
                on_message(msg)

    if not manifest_path.exists():
        raise FileNotFoundError(f"Agent did not produce manifest at {manifest_path}")

    manifest = json.loads(manifest_path.read_text())
    articles = manifest.get("articles", [])
    log.info(f"Collected {len(articles)} articles, analyzing each")
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
        async for msg in query(prompt=analysis_prompt, options=analysis_options):
            if on_message:
                on_message(msg)

        if output_path.exists():
            data = json.loads(output_path.read_text())
            data["_outlet"] = article["outlet"]
            data["_url"] = article["url"]
            output_path.write_text(json.dumps(data, indent=2))

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
