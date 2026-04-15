import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

DATA = Path("/instance")
MANIFEST_PATH = DATA / "publish_manifest.json"


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {"stories": {}}


def save_manifest(manifest: dict):
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def is_published(story_id: str, sample_id: str = None) -> bool:
    m = load_manifest()
    story = m["stories"].get(story_id)
    if not story:
        return False
    if sample_id is None:
        return True
    return sample_id in story.get("samples", {})


def is_stale(story_id: str, sample_id: str, current_hash: str) -> bool:
    m = load_manifest()
    story = m["stories"].get(story_id)
    if not story:
        return False
    sample = story.get("samples", {}).get(sample_id)
    if not sample:
        return False
    return sample["content_hash"] != current_hash


def mark_published(story_id: str, wp_page_id: int, content_hash_val: str,
                   sample_id: str = None, sample_wp_id: int = None,
                   sample_hash: str = None):
    m = load_manifest()
    now = datetime.now(timezone.utc).isoformat()
    if story_id not in m["stories"]:
        m["stories"][story_id] = {"samples": {}}
    entry = m["stories"][story_id]
    entry["wp_page_id"] = wp_page_id
    entry["content_hash"] = content_hash_val
    entry["published_at"] = now
    if sample_id and sample_wp_id:
        entry["samples"][sample_id] = {
            "wp_page_id": sample_wp_id,
            "content_hash": sample_hash or "",
            "published_at": now,
        }
    save_manifest(m)


def mark_sample_published(story_id: str, sample_id: str,
                          wp_page_id: int, hash_val: str):
    m = load_manifest()
    now = datetime.now(timezone.utc).isoformat()
    if story_id not in m["stories"]:
        m["stories"][story_id] = {"samples": {}}
    m["stories"][story_id]["samples"][sample_id] = {
        "wp_page_id": wp_page_id,
        "content_hash": hash_val,
        "published_at": now,
    }
    save_manifest(m)


def mark_redacted(story_id: str, sample_id: str = None):
    m = load_manifest()
    story = m["stories"].get(story_id)
    if not story:
        return
    if sample_id:
        story.get("samples", {}).pop(sample_id, None)
    else:
        m["stories"].pop(story_id, None)
    save_manifest(m)


def get_story_sync_status(story_id: str, all_sample_ids: list[str],
                          analyzed_ids: set[str]) -> dict:
    m = load_manifest()
    story = m["stories"].get(story_id)
    if not story:
        return {"status": "unpublished", "samples": {}}
    result = {
        "status": "synced",
        "wp_page_id": story.get("wp_page_id"),
        "published_at": story.get("published_at"),
        "samples": {},
    }
    published_samples = story.get("samples", {})
    for sid in all_sample_ids:
        if sid not in analyzed_ids:
            continue
        ps = published_samples.get(sid)
        if not ps:
            result["samples"][sid] = {"status": "unpublished"}
            result["status"] = "stale"
        else:
            result["samples"][sid] = {
                "status": "synced",
                "wp_page_id": ps["wp_page_id"],
                "published_at": ps["published_at"],
                "content_hash": ps["content_hash"],
            }
    # Check for samples published but deleted locally
    for sid in list(published_samples.keys()):
        if sid not in all_sample_ids:
            result["samples"][sid] = {"status": "deleted_locally"}
            result["status"] = "stale"
    return result
