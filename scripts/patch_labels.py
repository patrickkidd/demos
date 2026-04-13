import json, asyncio, logging
from pathlib import Path

log = logging.getLogger(__name__)
DATA = Path("/instance")

PROMPT = """You will receive a list of opinion axis centroids from a news analysis.
For each axis, generate two short display labels (pole_a_label and pole_b_label).

Rules:
- Each label must be 2-5 words maximum
- Extract a specific number, percentage, timeframe, or dollar amount from the
  pole summary when possible (e.g., "100%", "3-6 months", "$44 billion")
- If no number exists, use the shortest phrase that captures the core assertion
  (e.g., "regime change", "diplomatic failure", "total victory")
- Labels should contrast sharply — they appear side-by-side in a VS comparison

INPUT (axis centroids):
{centroids}

Respond with ONLY a JSON array of objects, one per axis:
[
  {{"axis_id": "AX-001", "pole_a_label": "...", "pole_b_label": "..."}},
  ...
]
"""


async def patch_sample(story_id, sample_id):
    from claude_agent_sdk import query, ClaudeAgentOptions

    sample_dir = DATA / "stories" / story_id / "samples" / sample_id
    phase4_path = sample_dir / "phase4.json"
    if not phase4_path.exists():
        return

    phase4 = json.loads(phase4_path.read_text())
    centroids = phase4.get("axis_centroids", [])
    if not centroids or centroids[0].get("pole_a_label"):
        log.info(f"  {sample_id}: already patched")
        return

    centroid_input = json.dumps([{
        "axis_id": c["axis_id"],
        "axis": c["axis"],
        "pole_a_summary": c["pole_a_summary"],
        "pole_b_summary": c["pole_b_summary"],
    } for c in centroids], indent=2)

    output_path = f"/tmp/patch_labels_{sample_id}.json"
    prompt = PROMPT.format(centroids=centroid_input) + f"\n\nWrite your JSON output to {output_path}"

    options = ClaudeAgentOptions(
        allowed_tools=["Write"],
        permission_mode="bypassPermissions",
        model="claude-sonnet-4-6",
        cwd="/instance",
    )

    async for msg in query(prompt=prompt, options=options):
        pass

    if not Path(output_path).exists():
        log.warning(f"  {sample_id}: patch failed, no output")
        return

    try:
        labels = json.loads(Path(output_path).read_text())
    except json.JSONDecodeError:
        log.warning(f"  {sample_id}: patch failed, invalid JSON")
        return

    label_map = {l["axis_id"]: l for l in labels}
    for c in centroids:
        patch = label_map.get(c["axis_id"], {})
        c["pole_a_label"] = patch.get("pole_a_label", "")
        c["pole_b_label"] = patch.get("pole_b_label", "")

    phase4_path.write_text(json.dumps(phase4, indent=2))
    log.info(f"  {sample_id}: patched {len(labels)} axes")
    Path(output_path).unlink(missing_ok=True)


async def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    stories = json.loads((DATA / "stories.json").read_text())
    for story in stories:
        story_id = story["id"]
        samples_dir = DATA / "stories" / story_id / "samples"
        if not samples_dir.exists():
            continue
        for sample_dir in sorted(samples_dir.iterdir()):
            if (sample_dir / "phase4.json").exists():
                log.info(f"Patching {sample_dir.name}...")
                await patch_sample(story_id, sample_dir.name)


if __name__ == "__main__":
    asyncio.run(main())
