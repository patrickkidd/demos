import json, asyncio, logging
from pathlib import Path
from datetime import datetime, timezone
from claude_agent_sdk import ClaudeAgentOptions
from scripts.retryquery import retry_query

DATA = Path("/instance")
log = logging.getLogger(__name__)

TOOLS = ["Read", "Write"]


async def analyze_sample(story: dict, sample_id: str, on_message=None):
    sample_dir = DATA / "stories" / story["id"] / "samples" / sample_id
    phase1_dir = sample_dir / "phase1"

    extractions = []
    for f in sorted(phase1_dir.glob("*.json")):
        extractions.append(json.loads(f.read_text()))

    if len(extractions) < 5:
        log.info(f"Skipping {story['topic']} sample {sample_id} — only {len(extractions)} articles")
        return None

    log.info(f"Analyzing {len(extractions)} articles for {story['topic']}")
    input_path = f"/tmp/{story['id']}_{sample_id}_phase1.json"
    output_path = str(sample_dir / "phase2.json")
    Path(input_path).write_text(json.dumps(extractions, indent=2))

    prompt_template = Path("/app/prompts/aggregate.md").read_text()
    prompt = (
        f"{prompt_template}\n\n"
        f"INPUT: {input_path}\n"
        f"Each article JSON has _outlet and _url fields with the source info.\n\n"
        f"Write your JSON output to {output_path}"
    ).replace("{topic}", story["topic"]).replace("{sample_id}", sample_id)

    options = ClaudeAgentOptions(
        allowed_tools=TOOLS,
        permission_mode="bypassPermissions",
        model="claude-opus-4-6",
        cwd="/instance",
    )
    await retry_query(prompt=prompt, options=options, on_message=on_message)

    if not Path(output_path).exists():
        log.warning(f"Phase 2 did not produce output for {sample_id}")
        return None

    return json.loads(Path(output_path).read_text())


async def analyze_story(story: dict, sample_id: str = None, on_message=None):
    if sample_id is None:
        samples_dir = DATA / "stories" / story["id"] / "samples"
        if not samples_dir.exists():
            log.info(f"No samples for {story['topic']}")
            return None
        sample_dirs = sorted(samples_dir.iterdir())
        if not sample_dirs:
            return None
        sample_id = sample_dirs[-1].name

    return await analyze_sample(story, sample_id, on_message=on_message)


async def main():
    stories = json.loads((DATA / "stories.json").read_text())
    for story in stories:
        print(f"Analyzing: {story['topic']}")
        result = await analyze_story(story)
        if result:
            print(f"  Done: {len(result.get('facts', []))} facts, "
                  f"{len(result.get('opinion_axes', []))} axes")
    print("Done.")

if __name__ == "__main__":
    asyncio.run(main())
