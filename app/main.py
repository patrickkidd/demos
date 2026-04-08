import json, uuid, asyncio, subprocess, logging
from pathlib import Path
from datetime import datetime, timezone
import markdown
from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse

from scripts.phase1_extract import run_story
from scripts.phase2_analyze import analyze_story
from scripts.phase3_synthesize import synthesize_story

app = FastAPI()
templates = Jinja2Templates(directory="/app/app/templates")
DATA = Path("/instance")

# story_id → "extracting" | "analyzing" | "synthesizing"
_running: dict[str, str] = {}
# story_id → list of log lines
_logs: dict[str, list[str]] = {}

MAX_LOG_LINES = 500
_logger = logging.getLogger("demos")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")


def _log(story_id: str, line: str):
    _logger.info(f"[{story_id}] {line}")
    buf = _logs.setdefault(story_id, [])
    buf.append(line)
    if len(buf) > MAX_LOG_LINES:
        del buf[:len(buf) - MAX_LOG_LINES]


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
            _log(story_id, f"[tool] {block.name}")


def _story_samples(story_id: str) -> list[str]:
    samples_dir = DATA / "stories" / story_id / "samples"
    if not samples_dir.exists():
        return []
    return sorted(d.name for d in samples_dir.iterdir() if d.is_dir())


def _load_sample(story_id: str, sample_id: str) -> dict:
    sample_dir = DATA / "stories" / story_id / "samples" / sample_id
    result = {"id": sample_id}
    phase2 = sample_dir / "phase2.json"
    phase3 = sample_dir / "phase3.json"
    if phase2.exists():
        result["phase2"] = json.loads(phase2.read_text())
    if phase3.exists():
        result["phase3"] = json.loads(phase3.read_text())
    phase1_dir = sample_dir / "phase1"
    if phase1_dir.exists():
        result["article_count"] = len(list(phase1_dir.glob("*.json")))
    else:
        result["article_count"] = 0
    return result


async def _sample_bg(story_id: str):
    stories_path = DATA / "stories.json"
    stories = json.loads(stories_path.read_text())
    story = next((s for s in stories if s["id"] == story_id), None)
    if not story:
        return
    _logs[story_id] = []
    on_msg = lambda msg: _msg_to_log(story_id, msg)
    try:
        _running[story_id] = "extracting"
        _log(story_id, "--- Phase 1: extracting articles ---")
        await run_story(story, on_message=on_msg)
        stories_path.write_text(json.dumps(stories, indent=2))

        sample_id = story.get("last_sample")
        _running[story_id] = "analyzing"
        _log(story_id, "--- Phase 2: analyzing ---")
        result = await analyze_story(story, sample_id, on_message=on_msg)
        if result:
            _running[story_id] = "synthesizing"
            _log(story_id, "--- Phase 3: synthesizing ---")
            await synthesize_story(story, sample_id, on_message=on_msg)
        _log(story_id, "--- Done ---")
    except Exception as e:
        _log(story_id, f"ERROR: {e}")
        _running[story_id] = "failed"
        await asyncio.sleep(10)
    finally:
        _running.pop(story_id, None)


@app.get("/")
async def index(request: Request):
    stories = json.loads((DATA / "stories.json").read_text())
    for s in stories:
        samples = _story_samples(s["id"])
        s["samples"] = samples
        s["sample_count"] = len(samples)
        analyzed = set()
        for sid in samples:
            if (DATA / "stories" / s["id"] / "samples" / sid / "phase3.json").exists():
                analyzed.add(sid)
        s["analyzed_samples"] = analyzed
        if samples:
            latest = _load_sample(s["id"], samples[-1])
            s["article_count"] = latest.get("article_count", 0)
            s["has_analysis"] = "phase3" in latest
        else:
            s["article_count"] = 0
            s["has_analysis"] = False
    return templates.TemplateResponse(request, "index.html", {
        "stories": stories, "running": _running,
    })


@app.get("/api/status")
async def api_status():
    return JSONResponse(dict(_running))


@app.get("/api/stories/{story_id}/log")
async def api_log(story_id: str, after: int = 0):
    lines = _logs.get(story_id, [])
    return JSONResponse({"lines": lines[after:], "total": len(lines)})


@app.get("/story/{story_id}")
async def story(request: Request, story_id: str):
    meta = json.loads((DATA / "stories" / story_id / "meta.json").read_text())
    samples = _story_samples(story_id)
    analyzed = {s for s in samples
                if (DATA / "stories" / story_id / "samples" / s / "phase3.json").exists()}
    return templates.TemplateResponse(request, "story.html", {
        "meta": meta, "samples": samples, "analyzed_samples": analyzed,
        "running": _running,
    })


@app.get("/story/{story_id}/samples/{sample_id}")
async def sample_view(request: Request, story_id: str, sample_id: str):
    meta = json.loads((DATA / "stories" / story_id / "meta.json").read_text())
    samples = _story_samples(story_id)
    analyzed = {s for s in samples
                if (DATA / "stories" / story_id / "samples" / s / "phase3.json").exists()}
    current = _load_sample(story_id, sample_id) if sample_id in samples else None
    return templates.TemplateResponse(request, "sample.html", {
        "meta": meta, "samples": samples, "analyzed_samples": analyzed,
        "current": current, "running": _running,
    })


@app.get("/api/stories/{story_id}/samples/{sample_id}")
async def api_sample(story_id: str, sample_id: str):
    return JSONResponse(_load_sample(story_id, sample_id))


@app.get("/methodology")
async def methodology(request: Request):
    md_path = Path("/app/doc/methodology.md")
    html = markdown.markdown(md_path.read_text(), extensions=["tables", "fenced_code"])
    return templates.TemplateResponse(request, "methodology.html", {
        "content": html,
    })


@app.get("/corpus")
async def corpus(request: Request):
    return templates.TemplateResponse(request, "corpus.html", {
        "running": _running,
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
async def add_story(topic: str = Form(...), seed_url: str = Form(""),
                    article_count: int = Form(6)):
    stories = json.loads((DATA / "stories.json").read_text())
    sid = str(uuid.uuid4())[:8]
    story = {
        "id": sid, "topic": topic,
        "seed_url": seed_url or None,
        "article_count": max(3, min(article_count, 30)),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_run_at": None, "last_sample": None, "active": True,
    }
    stories.append(story)
    (DATA / "stories.json").write_text(json.dumps(stories, indent=2))
    d = DATA / "stories" / sid
    d.mkdir(parents=True, exist_ok=True)
    (d / "samples").mkdir(exist_ok=True)
    (d / "articles").mkdir(exist_ok=True)
    (d / "meta.json").write_text(json.dumps(story, indent=2))
    return RedirectResponse("/", status_code=303)


@app.post("/stories/{story_id}/settings")
async def update_story_settings(story_id: str, article_count: int = Form(6)):
    stories_path = DATA / "stories.json"
    stories = json.loads(stories_path.read_text())
    story = next((s for s in stories if s["id"] == story_id), None)
    if story:
        story["article_count"] = max(3, min(article_count, 30))
        stories_path.write_text(json.dumps(stories, indent=2))
        meta_path = DATA / "stories" / story_id / "meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            meta["article_count"] = story["article_count"]
            meta_path.write_text(json.dumps(meta, indent=2))
    return RedirectResponse(f"/story/{story_id}", status_code=303)


@app.post("/stories/{story_id}/sample")
async def sample_story(story_id: str):
    if story_id not in _running:
        asyncio.create_task(_sample_bg(story_id))
    return RedirectResponse(f"/story/{story_id}", status_code=303)


@app.post("/stories/{story_id}/delete")
async def delete_story(story_id: str):
    import shutil
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
    sample_dir = DATA / "stories" / story_id / "samples" / sample_id
    if sample_dir.exists():
        shutil.rmtree(sample_dir)
    return RedirectResponse(f"/story/{story_id}", status_code=303)


@app.post("/sample-all")
async def sample_all():
    stories = json.loads((DATA / "stories.json").read_text())
    for s in stories:
        if s.get("active") and s["id"] not in _running:
            asyncio.create_task(_sample_bg(s["id"]))
    return RedirectResponse("/", status_code=303)
