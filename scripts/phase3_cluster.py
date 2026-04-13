import json, asyncio, logging
from pathlib import Path
from claude_agent_sdk import ClaudeAgentOptions
from scripts.retryquery import retry_query

DATA = Path("/instance")
log = logging.getLogger(__name__)

TOOLS = ["Read", "Write"]


async def cluster_sample(story: dict, sample_id: str, on_message=None):
    sample_dir = DATA / "stories" / story["id"] / "samples" / sample_id
    phase2_path = sample_dir / "phase2.json"

    if not phase2_path.exists():
        log.warning(f"No phase2.json for {story['topic']} sample {sample_id}")
        return None

    log.info(f"Clustering developments for {story['topic']}")
    output_path = str(sample_dir / "phase3.json")

    prompt_template = Path("/app/prompts/cluster.md").read_text()
    prompt = (
        f"{prompt_template}\n\n"
        f"INPUT: {phase2_path}\n\n"
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
        log.warning(f"Phase 3 did not produce output for {sample_id}")
        return None

    return json.loads(Path(output_path).read_text())


async def main():
    stories = json.loads((DATA / "stories.json").read_text())
    for story in stories:
        print(f"Clustering: {story['topic']}")
        samples_dir = DATA / "stories" / story["id"] / "samples"
        if not samples_dir.exists():
            continue
        sample_dirs = sorted(samples_dir.iterdir())
        if sample_dirs:
            result = await cluster_sample(story, sample_dirs[-1].name)
            if result:
                print(f"  Done: {len(result.get('developments', []))} developments")
    print("Done.")

if __name__ == "__main__":
    asyncio.run(main())
