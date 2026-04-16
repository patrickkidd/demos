import sys, json, time, asyncio, logging, shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "/app")
from scripts.phase1_extract import run_story, DATA
from scripts.phase2_analyze import analyze_story
from scripts.phase3_cluster import cluster_sample
from scripts.phase4_synthesize import synthesize_story

INTERVAL = 60  # check every minute
SLEEP_THRESHOLD = INTERVAL * 3

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

# Track which stories already ran today (UTC date → set of story IDs)
ran_today: dict[str, set[str]] = {}


def should_run(story: dict, now: datetime) -> bool:
    if not story.get("schedule_enabled"):
        return False

    today = now.date().isoformat()
    if story["id"] in ran_today.get(today, set()):
        return False

    schedule_time = story.get("schedule_time", "06:00")
    try:
        hour, minute = (int(x) for x in schedule_time.split(":"))
    except (ValueError, AttributeError):
        hour, minute = 6, 0

    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    # Run if we're past the target time but haven't run today
    return now >= target


async def run_full_sample(story: dict):
    log.info(f"  Phase 1: extracting")
    await run_story(story)
    sample_id = story.get("last_sample")
    log.info(f"  Phase 2: aggregating sample {sample_id}")
    result = await analyze_story(story, sample_id)
    if result:
        log.info(f"  Phase 3: clustering")
        await cluster_sample(story, sample_id)
        log.info(f"  Phase 4: synthesizing")
        await synthesize_story(story, sample_id)
    if sample_id:
        _cleanup_empty_sample(story["id"], sample_id)


def _cleanup_empty_sample(story_id: str, sample_id: str):
    sample_dir = DATA / "stories" / story_id / "samples" / sample_id
    if not sample_dir.exists():
        return
    if (sample_dir / "phase2.json").exists():
        return
    log.info(f"Cleaning up incomplete sample {sample_id}")
    shutil.rmtree(sample_dir)


async def tick():
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()

    # Clean old dates from ran_today
    for d in list(ran_today):
        if d != today:
            del ran_today[d]

    stories_path = DATA / "stories.json"
    stories = json.loads(stories_path.read_text())
    due = [s for s in stories if s.get("active") and should_run(s, now)]

    if not due:
        return

    for story in due:
        log.info(f"Scheduled sample: {story['topic']}")
        sample_id_before = story.get("last_sample")
        try:
            await run_full_sample(story)
        except Exception as e:
            log.error(f"  Failed {story['topic']}: {e}")
            sample_id_after = story.get("last_sample")
            if sample_id_after and sample_id_after != sample_id_before:
                _cleanup_empty_sample(story["id"], sample_id_after)
        ran_today.setdefault(today, set()).add(story["id"])
    stories_path.write_text(json.dumps(stories, indent=2))


def cleanup_orphans():
    stories_dir = DATA / "stories"
    if not stories_dir.exists():
        return
    count = 0
    for story_dir in stories_dir.iterdir():
        samples_dir = story_dir / "samples"
        if not samples_dir.is_dir():
            continue
        for sample_dir in samples_dir.iterdir():
            if sample_dir.is_dir() and not (sample_dir / "phase2.json").exists():
                log.info(f"Startup cleanup: removing orphan {story_dir.name}/{sample_dir.name}")
                shutil.rmtree(sample_dir)
                count += 1
    if count:
        log.info(f"Cleaned up {count} orphan sample(s)")


def main():
    log.info("Watchdog started")
    cleanup_orphans()
    while True:
        t0 = time.monotonic()
        time.sleep(INTERVAL)
        elapsed = time.monotonic() - t0
        if elapsed > SLEEP_THRESHOLD:
            log.info(f"Woke from sleep ({elapsed:.0f}s gap) — skipping")
            continue
        asyncio.run(tick())


if __name__ == "__main__":
    main()
