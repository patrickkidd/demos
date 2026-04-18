import json, uuid, asyncio, subprocess, logging, shutil
from enum import Enum
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
import markdown
from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse


class Phase(Enum):
    Extracting = "extracting"
    Analyzing = "analyzing"
    Clustering = "clustering"
    Synthesizing = "synthesizing"
    Failed = "failed"

from scripts.phase1_extract import run_story
from scripts.phase2_analyze import analyze_story
from scripts.phase3_cluster import cluster_sample
from scripts.phase4_synthesize import synthesize_story

app = FastAPI()
templates = Jinja2Templates(directory="/app/app/templates")
DATA = Path("/instance")

# story_id → {"phase": str, "sample": str}
_running: dict[str, dict] = {}
# story_id → list of log lines
_logs: dict[str, list[str]] = {}

MAX_LOG_LINES = 500
_logger = logging.getLogger("demos")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")


def _log_path(story_id: str) -> Path:
    return DATA / "stories" / story_id / "sample.log"


def _log(story_id: str, line: str):
    _logger.info(f"[{story_id}] {line}")
    buf = _logs.setdefault(story_id, [])
    buf.append(line)
    if len(buf) > MAX_LOG_LINES:
        del buf[:len(buf) - MAX_LOG_LINES]
    try:
        with open(_log_path(story_id), "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _load_log(story_id: str) -> list[str]:
    p = _log_path(story_id)
    if p.exists():
        lines = p.read_text().splitlines()
        return lines[-MAX_LOG_LINES:]
    return []


def _summarize_tool_input(name: str, inp: dict) -> str:
    if not isinstance(inp, dict):
        return ""
    if name == "WebFetch":
        return inp.get("url", "")[:120]
    if name == "WebSearch":
        return inp.get("query", "")[:120]
    if name in ("Read", "Write"):
        return inp.get("file_path", "")[:120]
    if name == "Bash":
        cmd = inp.get("command", "")
        return cmd[:120] if len(cmd) <= 120 else cmd[:117] + "..."
    return ""


def _msg_to_log(story_id: str, msg):
    from claude_agent_sdk import AssistantMessage
    from claude_agent_sdk.types import TextBlock, ToolUseBlock
    if not isinstance(msg, AssistantMessage):
        return
    for block in msg.content:
        if isinstance(block, TextBlock) and block.text.strip():
            for line in block.text.strip().splitlines():
                _log(story_id, line)
        elif isinstance(block, ToolUseBlock):
            summary = _summarize_tool_input(block.name, block.input)
            _log(story_id, f"[tool] {block.name} {summary}" if summary else f"[tool] {block.name}")


def _story_samples(story_id: str) -> list[str]:
    samples_dir = DATA / "stories" / story_id / "samples"
    if not samples_dir.exists():
        return []
    return sorted(d.name for d in samples_dir.iterdir() if d.is_dir())


def _sample_headlines(story_id: str, sample_ids: list[str]) -> dict[str, str]:
    result = {}
    for sid in sample_ids:
        p4 = DATA / "stories" / story_id / "samples" / sid / "phase4.json"
        if p4.exists():
            try:
                result[sid] = json.loads(p4.read_text())["headline"]
            except (json.JSONDecodeError, KeyError):
                pass
    return result


def _load_sample(story_id: str, sample_id: str) -> dict:
    sample_dir = DATA / "stories" / story_id / "samples" / sample_id
    result = {"id": sample_id}
    phase2 = sample_dir / "phase2.json"
    phase3 = sample_dir / "phase3.json"
    phase4 = sample_dir / "phase4.json"
    if phase2.exists():
        result["phase2"] = json.loads(phase2.read_text())
    if phase4.exists():
        # New format: phase3 = clusters, phase4 = synthesis
        if phase3.exists():
            result["clusters"] = json.loads(phase3.read_text())
        result["synthesis"] = json.loads(phase4.read_text())
    elif phase3.exists():
        # Old format: phase3 = synthesis (no clusters)
        data = json.loads(phase3.read_text())
        if "centroid_article" in data:
            result["synthesis"] = data
    phase1_dir = sample_dir / "phase1"
    outlet_urls = {}
    if phase1_dir.exists():
        p1_files = list(phase1_dir.glob("*.json"))
        result["article_count"] = len(p1_files)
        for f in p1_files:
            try:
                d = json.loads(f.read_text())
                name = d.get("_outlet")
                url = d.get("_url")
                if name and url:
                    outlet_urls[name] = url
            except (json.JSONDecodeError, KeyError):
                pass
    else:
        result["article_count"] = 0
    result["outlet_urls"] = outlet_urls
    return result


async def _run_sample_phases(story_id: str, sample_id: str,
                             target_date: str = None):
    """Run all pipeline phases for one sample. Caller manages _running lifecycle."""
    stories_path = DATA / "stories.json"
    stories = json.loads(stories_path.read_text())
    story = next((s for s in stories if s["id"] == story_id), None)
    if not story:
        return
    on_msg = lambda msg: _msg_to_log(story_id, msg)
    def on_progress(done, total):
        r = _running.get(story_id)
        if r:
            r["done"] = done
            r["total"] = total

    _running[story_id]["phase"] = Phase.Extracting
    _log(story_id, "--- Phase 1: extracting articles ---")
    await run_story(story, on_message=on_msg, sample_id=sample_id,
                    on_progress=on_progress, target_date=target_date)
    stories_path.write_text(json.dumps(stories, indent=2))

    _running[story_id]["phase"] = Phase.Analyzing
    _log(story_id, "--- Phase 2: aggregating ---")
    result = await analyze_story(story, sample_id, on_message=on_msg)
    if result:
        _running[story_id]["phase"] = Phase.Clustering
        _log(story_id, "--- Phase 3: clustering ---")
        await cluster_sample(story, sample_id, on_message=on_msg)

        _running[story_id]["phase"] = Phase.Synthesizing
        _log(story_id, "--- Phase 4: synthesizing ---")
        await synthesize_story(story, sample_id, on_message=on_msg)
    _log(story_id, "--- Done ---")


async def _sample_bg(story_id: str, sample_id: str, target_date: str = None):
    _logs[story_id] = []
    try:
        _log_path(story_id).unlink(missing_ok=True)
    except OSError:
        pass
    try:
        _running[story_id] = {"phase": Phase.Extracting, "sample": sample_id, "done": 0, "total": 0}
        await _run_sample_phases(story_id, sample_id, target_date)
    except Exception as e:
        _log(story_id, f"ERROR: {e}")
        _running[story_id] = {"phase": Phase.Failed, "sample": sample_id}
        await asyncio.sleep(10)
    finally:
        _running.pop(story_id, None)
        _cleanup_empty_sample(story_id, sample_id)


def _cleanup_empty_sample(story_id: str, sample_id: str):
    sample_dir = DATA / "stories" / story_id / "samples" / sample_id
    if not sample_dir.exists():
        return
    if (sample_dir / "phase2.json").exists():
        return
    _logger.info(f"[{story_id}] Cleaning up incomplete sample {sample_id}")
    shutil.rmtree(sample_dir)


@app.get("/")
async def index(request: Request):
    stories = json.loads((DATA / "stories.json").read_text())
    for s in stories:
        samples = _story_samples(s["id"])
        s["samples"] = samples
        s["sample_count"] = len(samples)
        analyzed = set()
        for sid in samples:
            if (DATA / "stories" / s["id"] / "samples" / sid / "phase4.json").exists() or (DATA / "stories" / s["id"] / "samples" / sid / "phase3.json").exists():
                analyzed.add(sid)
        s["analyzed_samples"] = analyzed
        s["headlines"] = _sample_headlines(s["id"], samples)
        if samples:
            latest = _load_sample(s["id"], samples[-1])
            s["article_count"] = latest.get("article_count", 0)
            s["has_analysis"] = "synthesis" in latest
        else:
            s["article_count"] = 0
            s["has_analysis"] = False
    return templates.TemplateResponse(request, "index.html", {
        "stories": stories, "running": _running,
    })


@app.get("/api/status")
async def api_status():
    result = {}
    for k, v in _running.items():
        entry = {"phase": v["phase"].value, "sample": v["sample"],
                 "done": v.get("done", 0), "total": v.get("total", 0)}
        if v.get("backfill"):
            entry["backfill"] = True
            entry["bf_current"] = v["bf_current"]
            entry["bf_total"] = v["bf_total"]
        result[k] = entry
    return JSONResponse(result)


@app.get("/api/stories/{story_id}/log")
async def api_log(story_id: str, after: int = 0):
    lines = _logs.get(story_id) or _load_log(story_id)
    return JSONResponse({"lines": lines[after:], "total": len(lines)})


def _queued_samples(story_id: str) -> list[str]:
    bf_path = DATA / "stories" / story_id / "backfill.json"
    if not bf_path.exists():
        return []
    bf = json.loads(bf_path.read_text())
    existing = set(_story_samples(story_id))
    return [e["sample_id"] for e in bf["samples"] if e["sample_id"] not in existing]


def _all_samples(story_id: str) -> list[str]:
    return sorted(set(_story_samples(story_id)) | set(_queued_samples(story_id)))


def _stopped_samples(story_id: str) -> dict[str, str]:
    samples_dir = DATA / "stories" / story_id / "samples"
    if not samples_dir.exists():
        return {}
    running_sid = _running.get(story_id, {}).get("sample")
    result = {}
    for d in samples_dir.iterdir():
        if not d.is_dir() or d.name == running_sid:
            continue
        if (d / "phase2.json").exists() or (d / "phase3.json").exists() or (d / "phase4.json").exists():
            continue
        if not (d / "manifest.json").exists() and not (d / "phase1").exists():
            continue
        ref = d / "manifest.json" if (d / "manifest.json").exists() else d
        ts = datetime.fromtimestamp(ref.stat().st_mtime, tz=timezone.utc)
        result[d.name] = ts.strftime("%-d %b %H:%M UTC")
    return result


@app.get("/story/{story_id}")
async def story(request: Request, story_id: str):
    meta = json.loads((DATA / "stories" / story_id / "meta.json").read_text())
    samples = _all_samples(story_id)
    analyzed = {s for s in samples
                if (DATA / "stories" / story_id / "samples" / s / "phase4.json").exists() or (DATA / "stories" / story_id / "samples" / s / "phase3.json").exists()}
    headlines = _sample_headlines(story_id, samples)
    queued = set(_queued_samples(story_id))
    stopped = _stopped_samples(story_id)
    return templates.TemplateResponse(request, "story.html", {
        "meta": meta, "samples": samples, "analyzed_samples": analyzed,
        "headlines": headlines, "running": _running, "queued_samples": queued,
        "stopped_samples": stopped,
    })


@app.get("/story/{story_id}/samples/{sample_id}")
async def sample_view(request: Request, story_id: str, sample_id: str):
    meta = json.loads((DATA / "stories" / story_id / "meta.json").read_text())
    existing = _story_samples(story_id)
    samples = _all_samples(story_id)
    analyzed = {s for s in samples
                if (DATA / "stories" / story_id / "samples" / s / "phase4.json").exists() or (DATA / "stories" / story_id / "samples" / s / "phase3.json").exists()}
    current = _load_sample(story_id, sample_id) if sample_id in existing else None
    outlets = json.loads((Path("/app/app/outlets.json")).read_text())
    bias_scores = {o["outlet"]: o["bias_score"] for o in outlets}
    headlines = _sample_headlines(story_id, samples)
    queued = set(_queued_samples(story_id))
    stopped = _stopped_samples(story_id)
    return templates.TemplateResponse(request, "sample.html", {
        "meta": meta, "samples": samples, "analyzed_samples": analyzed,
        "headlines": headlines, "current": current, "running": _running,
        "bias_scores": bias_scores, "queued_samples": queued,
        "stopped_samples": stopped,
    })


@app.get("/api/stories/{story_id}/samples/{sample_id}")
async def api_sample(story_id: str, sample_id: str):
    return JSONResponse(_load_sample(story_id, sample_id))


@app.get("/why")
async def why(request: Request):
    md_path = Path("/app/doc/why.md")
    html = markdown.markdown(md_path.read_text(), extensions=["tables", "fenced_code"])
    return templates.TemplateResponse(request, "why.html", {
        "content": html,
    })


@app.get("/methodology")
async def methodology(request: Request):
    md_path = Path("/app/doc/methodology.md")
    html = markdown.markdown(md_path.read_text(), extensions=["tables", "fenced_code"])
    return templates.TemplateResponse(request, "methodology.html", {
        "content": html,
    })


@app.get("/auth")
async def auth(request: Request):
    result = subprocess.run(
        ["claude", "auth", "status"], capture_output=True, text=True
    )
    status = (result.stdout + result.stderr).strip()
    return templates.TemplateResponse(request, "auth.html", {
        "status": status,
        "authenticated": result.returncode == 0,
    })


@app.post("/stories")
async def add_story(topic: str = Form(...), seed_url: str = Form("")):
    stories = json.loads((DATA / "stories.json").read_text())
    sid = str(uuid.uuid4())[:8]
    story = {
        "id": sid, "topic": topic,
        "seed_url": seed_url or None,
        "schedule_enabled": False,
        "schedule_time": "06:00",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_run_at": None, "last_sample": None, "active": True,
    }
    stories.append(story)
    (DATA / "stories.json").write_text(json.dumps(stories, indent=2))
    d = DATA / "stories" / sid
    d.mkdir(parents=True, exist_ok=True)
    (d / "samples").mkdir(exist_ok=True)
    (d / "meta.json").write_text(json.dumps(story, indent=2))
    return RedirectResponse("/", status_code=303)


@app.post("/stories/{story_id}/settings")
async def update_story_settings(story_id: str,
                                schedule_enabled: str = Form(""),
                                schedule_time: str = Form("06:00")):
    stories_path = DATA / "stories.json"
    stories = json.loads(stories_path.read_text())
    story = next((s for s in stories if s["id"] == story_id), None)
    if story:
        story["schedule_enabled"] = schedule_enabled == "on"
        story["schedule_time"] = schedule_time
        stories_path.write_text(json.dumps(stories, indent=2))
        meta_path = DATA / "stories" / story_id / "meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            meta["schedule_enabled"] = story["schedule_enabled"]
            meta["schedule_time"] = story["schedule_time"]
            meta_path.write_text(json.dumps(meta, indent=2))
    return RedirectResponse(f"/story/{story_id}", status_code=303)


@app.post("/stories/{story_id}/sample")
async def sample_story(story_id: str):
    if story_id not in _running:
        sample_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        asyncio.create_task(_sample_bg(story_id, sample_id))
        return RedirectResponse(f"/story/{story_id}/samples/{sample_id}", status_code=303)
    running = _running[story_id]
    return RedirectResponse(f"/story/{story_id}/samples/{running['sample']}", status_code=303)


@app.post("/stories/{story_id}/samples/{sample_id}/resume")
async def resume_sample(story_id: str, sample_id: str):
    if story_id not in _running:
        target_date = f"{sample_id[:4]}-{sample_id[4:6]}-{sample_id[6:8]}" if sample_id.endswith("T000000") else None
        asyncio.create_task(_sample_bg(story_id, sample_id, target_date))
    return RedirectResponse(f"/story/{story_id}/samples/{sample_id}", status_code=303)


async def _analyze_bg(story_id: str, sample_id: str):
    stories_path = DATA / "stories.json"
    stories = json.loads(stories_path.read_text())
    story = next((s for s in stories if s["id"] == story_id), None)
    if not story:
        return
    _logs[story_id] = []
    try:
        _log_path(story_id).unlink(missing_ok=True)
    except OSError:
        pass
    on_msg = lambda msg: _msg_to_log(story_id, msg)
    try:
        _running[story_id] = {"phase": Phase.Analyzing, "sample": sample_id}
        _log(story_id, "--- Phase 2: aggregating ---")
        result = await analyze_story(story, sample_id, on_message=on_msg)
        if result:
            _running[story_id] = {"phase": Phase.Clustering, "sample": sample_id}
            _log(story_id, "--- Phase 3: clustering ---")
            await cluster_sample(story, sample_id, on_message=on_msg)

            _running[story_id] = {"phase": Phase.Synthesizing, "sample": sample_id}
            _log(story_id, "--- Phase 4: synthesizing ---")
            await synthesize_story(story, sample_id, on_message=on_msg)
        _log(story_id, "--- Done ---")
    except Exception as e:
        _log(story_id, f"ERROR: {e}")
        _running[story_id] = {"phase": Phase.Failed, "sample": sample_id}
        await asyncio.sleep(10)
    finally:
        _running.pop(story_id, None)


@app.post("/stories/{story_id}/samples/{sample_id}/analyze")
async def analyze_sample_route(story_id: str, sample_id: str):
    if story_id not in _running:
        asyncio.create_task(_analyze_bg(story_id, sample_id))
    return RedirectResponse(f"/story/{story_id}/samples/{sample_id}", status_code=303)


@app.post("/stories/{story_id}/delete")
async def delete_story(story_id: str):
    import shutil
    from scripts.publish_state import is_published
    from scripts.publish import redact_story
    if is_published(story_id):
        try:
            redact_story(story_id)
        except Exception:
            pass
    stories_path = DATA / "stories.json"
    stories = json.loads(stories_path.read_text())
    stories = [s for s in stories if s["id"] != story_id]
    stories_path.write_text(json.dumps(stories, indent=2))
    story_dir = DATA / "stories" / story_id
    if story_dir.exists():
        shutil.rmtree(story_dir)
    _logs.pop(story_id, None)
    return RedirectResponse("/", status_code=303)


@app.post("/stories/{story_id}/samples/{sample_id}/delete")
async def delete_sample(story_id: str, sample_id: str):
    import shutil
    from scripts.publish_state import is_published
    from scripts.publish import redact_sample
    if is_published(story_id, sample_id):
        try:
            redact_sample(story_id, sample_id)
        except Exception:
            pass
    sample_dir = DATA / "stories" / story_id / "samples" / sample_id
    if sample_dir.exists():
        shutil.rmtree(sample_dir)
    return RedirectResponse(f"/story/{story_id}", status_code=303)


@app.post("/sample-all")
async def sample_all():
    stories = json.loads((DATA / "stories.json").read_text())
    for s in stories:
        if s.get("active") and s["id"] not in _running:
            sid = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            asyncio.create_task(_sample_bg(s["id"], sid))
    return RedirectResponse("/", status_code=303)


def _sample_complete(story_id: str, sample_id: str) -> bool:
    sample_dir = DATA / "stories" / story_id / "samples" / sample_id
    return (sample_dir / "phase4.json").exists() or (sample_dir / "phase3.json").exists()


async def _backfill_bg(story_id: str):
    bf_path = DATA / "stories" / story_id / "backfill.json"
    _logs[story_id] = []
    try:
        _log_path(story_id).unlink(missing_ok=True)
    except OSError:
        pass
    sid = None
    try:
        while bf_path.exists():
            bf = json.loads(bf_path.read_text())
            samples = bf["samples"]
            for e in samples:
                (DATA / "stories" / story_id / "samples" / e["sample_id"]).mkdir(parents=True, exist_ok=True)
            pending = [e for e in samples if not _sample_complete(story_id, e["sample_id"])]
            if not pending:
                bf_path.unlink(missing_ok=True)
                break
            entry = pending[0]
            sid = entry["sample_id"]
            td = entry["target_date"]
            total = len(samples)
            current = next(i + 1 for i, e in enumerate(samples) if e["sample_id"] == sid)
            _log(story_id, f"[backfill {current}/{total}] {td} — starting")
            _running[story_id] = {
                "phase": Phase.Extracting, "sample": sid,
                "done": 0, "total": 0,
                "backfill": True, "bf_current": current, "bf_total": total,
            }
            await _run_sample_phases(story_id, sid, target_date=td)
        _log(story_id, "Backfill complete")
    except Exception as e:
        _log(story_id, f"Backfill stopped: {e}")
        if sid:
            _running[story_id] = {"phase": Phase.Failed, "sample": sid, "backfill": True}
        await asyncio.sleep(10)
    finally:
        _running.pop(story_id, None)


@app.post("/stories/{story_id}/backfill")
async def backfill_story(story_id: str,
                         start_date: str = Form(...),
                         end_date: str = Form(...),
                         step_days: int = Form(3)):
    if story_id in _running:
        return RedirectResponse(f"/story/{story_id}", status_code=303)
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    samples = []
    d = start
    while d <= end:
        sample_id = d.strftime("%Y%m%dT000000")
        samples.append({"sample_id": sample_id, "target_date": d.isoformat()})
        (DATA / "stories" / story_id / "samples" / sample_id).mkdir(parents=True, exist_ok=True)
        d += timedelta(days=step_days)
    bf = {
        "start_date": start_date,
        "end_date": end_date,
        "step_days": step_days,
        "samples": samples,
    }
    bf_path = DATA / "stories" / story_id / "backfill.json"
    bf_path.write_text(json.dumps(bf, indent=2))
    asyncio.create_task(_backfill_bg(story_id))
    return RedirectResponse(f"/story/{story_id}", status_code=303)


@app.post("/stories/{story_id}/queue")
async def queue_date(story_id: str, target_date: str = Form(...)):
    sid = datetime.strptime(target_date, "%Y-%m-%d").strftime("%Y%m%dT000000")
    (DATA / "stories" / story_id / "samples" / sid).mkdir(parents=True, exist_ok=True)
    bf_path = DATA / "stories" / story_id / "backfill.json"
    bf = json.loads(bf_path.read_text()) if bf_path.exists() else {"samples": []}
    if not any(e["sample_id"] == sid for e in bf["samples"]):
        bf["samples"].append({"sample_id": sid, "target_date": target_date})
        bf_path.write_text(json.dumps(bf, indent=2))
    if story_id not in _running:
        asyncio.create_task(_backfill_bg(story_id))
    return RedirectResponse(f"/story/{story_id}", status_code=303)


# --- Publish routes ---

@app.get("/publish")
async def publish_dashboard(request: Request):
    from scripts.publish_state import load_manifest, get_story_sync_status
    from scripts.publish import test_connection

    stories = json.loads((DATA / "stories.json").read_text())
    manifest = load_manifest()
    config_exists = (DATA / "publish_config.json").exists()
    connection = test_connection() if config_exists else {"ok": False, "error": "publish_config.json not found"}

    story_statuses = []
    for s in stories:
        samples = _story_samples(s["id"])
        analyzed = {sid for sid in samples
                    if (DATA / "stories" / s["id"] / "samples" / sid / "phase4.json").exists()
                    or (DATA / "stories" / s["id"] / "samples" / sid / "phase3.json").exists()}
        sync = get_story_sync_status(s["id"], samples, analyzed)
        story_statuses.append({
            "id": s["id"],
            "topic": s["topic"],
            "total_samples": len(samples),
            "analyzed": len(analyzed),
            "published": len([v for v in sync["samples"].values() if v["status"] == "synced"]),
            "stale": len([v for v in sync["samples"].values() if v["status"] in ("unpublished", "deleted_locally")]),
            "sync": sync,
        })

    return templates.TemplateResponse(request, "publish.html", {
        "stories": story_statuses,
        "connection": connection,
        "config_exists": config_exists,
    })


@app.post("/publish/all")
def publish_all_route():
    from scripts.publish import publish_story, publish_index, publish_methodology, publish_why
    stories = json.loads((DATA / "stories.json").read_text())
    for s in stories:
        publish_story(s["id"])
    publish_index()
    publish_methodology()
    publish_why()
    return RedirectResponse("/publish", status_code=303)


@app.post("/publish/story/{story_id}")
def publish_story_route(story_id: str):
    from scripts.publish import publish_story
    publish_story(story_id)
    return RedirectResponse("/publish", status_code=303)


@app.post("/publish/story/{story_id}/samples/{sample_id}")
def publish_sample_route(story_id: str, sample_id: str):
    from scripts.publish import publish_sample
    from scripts.publish_state import mark_sample_published, load_manifest

    meta = json.loads((DATA / "stories" / story_id / "meta.json").read_text())
    manifest = load_manifest()
    existing = manifest.get("stories", {}).get(story_id, {}).get("samples", {}).get(sample_id, {})

    wp_id, h = publish_sample(story_id, sample_id, meta["topic"], existing.get("wp_page_id"))
    mark_sample_published(story_id, sample_id, wp_id, h)
    return RedirectResponse("/publish", status_code=303)


@app.post("/publish/index")
def publish_index_route():
    from scripts.publish import publish_index
    publish_index()
    return RedirectResponse("/publish", status_code=303)


@app.post("/publish/methodology")
def publish_methodology_route():
    from scripts.publish import publish_methodology
    publish_methodology()
    return RedirectResponse("/publish", status_code=303)


@app.post("/publish/why")
def publish_why_route():
    from scripts.publish import publish_why
    publish_why()
    return RedirectResponse("/publish", status_code=303)


@app.post("/redact/story/{story_id}")
def redact_story_route(story_id: str):
    from scripts.publish import redact_story
    redact_story(story_id)
    return RedirectResponse("/publish", status_code=303)


@app.post("/redact/story/{story_id}/samples/{sample_id}")
def redact_sample_route(story_id: str, sample_id: str):
    from scripts.publish import redact_sample
    redact_sample(story_id, sample_id)
    return RedirectResponse("/publish", status_code=303)


@app.get("/api/publish/test")
async def api_publish_test():
    from scripts.publish import test_connection
    return JSONResponse(test_connection())


@app.on_event("startup")
async def resume_backfills():
    stories_dir = DATA / "stories"
    if not stories_dir.exists():
        return
    for story_dir in stories_dir.iterdir():
        if not story_dir.is_dir():
            continue
        bf_path = story_dir / "backfill.json"
        if bf_path.exists():
            story_id = story_dir.name
            _log(story_id, "Resuming backfill from previous run")
            asyncio.create_task(_backfill_bg(story_id))
