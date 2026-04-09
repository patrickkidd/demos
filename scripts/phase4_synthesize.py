import json, asyncio, logging
from pathlib import Path
from claude_agent_sdk import query, ClaudeAgentOptions

DATA = Path("/instance")
log = logging.getLogger(__name__)

TOOLS = ["Read", "Write"]


async def synthesize_sample(story: dict, sample_id: str, on_message=None):
    sample_dir = DATA / "stories" / story["id"] / "samples" / sample_id
    phase2_path = sample_dir / "phase2.json"
    phase3_path = sample_dir / "phase3.json"

    if not phase2_path.exists():
        log.warning(f"No phase2.json for {story['topic']} sample {sample_id}")
        return None

    log.info(f"Synthesizing centroid for {story['topic']}")
    output_path = str(sample_dir / "phase4.json")

    prompt_template = Path("/app/prompts/synthesize.md").read_text()
    input_note = f"INPUT (aggregated data): {phase2_path}"
    if phase3_path.exists():
        input_note += f"\nINPUT (cluster data): {phase3_path}"
    prompt = (
        f"{prompt_template}\n\n"
        f"{input_note}\n\n"
        f"Write your JSON output to {output_path}"
    ).replace("{topic}", story["topic"]).replace("{sample_id}", sample_id)

    options = ClaudeAgentOptions(
        allowed_tools=TOOLS,
        permission_mode="bypassPermissions",
        model="claude-opus-4-6",
        cwd="/instance",
    )
    async for msg in query(prompt=prompt, options=options):
        if on_message:
            on_message(msg)

    if not Path(output_path).exists():
        log.warning(f"Phase 4 did not produce output for {sample_id}")
        return None

    return json.loads(Path(output_path).read_text())


async def synthesize_story(story: dict, sample_id: str = None, on_message=None):
    if sample_id is None:
        samples_dir = DATA / "stories" / story["id"] / "samples"
        if not samples_dir.exists():
            return None
        sample_dirs = sorted(samples_dir.iterdir())
        if not sample_dirs:
            return None
        sample_id = sample_dirs[-1].name

    return await synthesize_sample(story, sample_id, on_message=on_message)


async def main():
    stories = json.loads((DATA / "stories.json").read_text())
    for story in stories:
        print(f"Synthesizing: {story['topic']}")
        result = await synthesize_story(story)
        if result:
            print(f"  Done: {len(result.get('axis_centroids', []))} centroids")
    print("Done.")

if __name__ == "__main__":
    asyncio.run(main())
