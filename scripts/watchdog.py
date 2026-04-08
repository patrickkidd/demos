import sys, json, time, asyncio, logging
from pathlib import Path
from datetime import date, datetime, timezone

sys.path.insert(0, "/app")
from scripts.phase1_extract import run_story, DATA
from scripts.phase2_analyze import analyze_story
from scripts.phase3_synthesize import synthesize_story

INTERVAL = 1800
SLEEP_THRESHOLD = INTERVAL * 1.1

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)


def needs_run(story: dict) -> bool:
    last = story.get("last_run_at")
    if not last:
        return True
    return datetime.fromisoformat(last).astimezone(timezone.utc).date() < date.today()


async def run_full_sample(story: dict):
    log.info(f"  Phase 1: extracting")
    await run_story(story)
    sample_id = story.get("last_sample")
    log.info(f"  Phase 2: analyzing sample {sample_id}")
    result = await analyze_story(story, sample_id)
    if result:
        log.info(f"  Phase 3: synthesizing")
        await synthesize_story(story, sample_id)


async def tick():
    stories_path = DATA / "stories.json"
    stories = json.loads(stories_path.read_text())
    active = [s for s in stories if s.get("active") and needs_run(s)]
    if not active:
        log.info("All stories up to date")
        return
    for story in active:
        log.info(f"Sampling: {story['topic']}")
        try:
            await run_full_sample(story)
        except Exception as e:
            log.error(f"  Failed {story['topic']}: {e}")
    stories_path.write_text(json.dumps(stories, indent=2))


def main():
    log.info("Watchdog started")
    while True:
        t0 = time.monotonic()
        time.sleep(INTERVAL)
        elapsed = time.monotonic() - t0
        if elapsed > SLEEP_THRESHOLD:
            log.info(f"Woke from sleep ({elapsed:.0f}s gap) — skipping catchup")
            continue
        asyncio.run(tick())


if __name__ == "__main__":
    main()
