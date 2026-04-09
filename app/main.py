import json, uuid, asyncio, subprocess, logging
from enum import Enum
from pathlib import Path
from datetime import datetime, timezone
import markdown
from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse


class Phase(Enum):
    Extracting = "extracting"
    Analyzing = "analyzing"
    Synthesizing = "synthesizing"
    Failed = "failed"

from scripts.phase1_extract import run_story
from scripts.phase2_analyze import analyze_story
from scripts.phase3_synthesize import synthesize_story

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


async def _sample_bg(story_id: str, sample_id: str):
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
    def on_progress(done, total):
        r = _running.get(story_id)
        if r:
            r["done"] = done
            r["total"] = total
    try:
        _running[story_id] = {"phase": Phase.Extracting, "sample": sample_id, "done": 0, "total": 0}
        _log(story_id, "--- Phase 1: extracting articles ---")
        await run_story(story, on_message=on_msg, sample_id=sample_id, on_progress=on_progress)
        stories_path.write_text(json.dumps(stories, indent=2))

        _running[story_id] = {"phase": Phase.Analyzing, "sample": sample_id}
        _log(story_id, "--- Phase 2: analyzing ---")
        result = await analyze_story(story, sample_id, on_message=on_msg)
        if result:
            _running[story_id] = {"phase": Phase.Synthesizing, "sample": sample_id}
            _log(story_id, "--- Phase 3: synthesizing ---")
            await synthesize_story(story, sample_id, on_message=on_msg)
        _log(story_id, "--- Done ---")
    except Exception as e:
        _log(story_id, f"ERROR: {e}")
        _running[story_id] = {"phase": Phase.Failed, "sample": sample_id}
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
    return JSONResponse({
        k: {"phase": v["phase"].value, "sample": v["sample"],
            "done": v.get("done", 0), "total": v.get("total", 0)}
        for k, v in _running.items()
    })


@app.get("/api/stories/{story_id}/log")
async def api_log(story_id: str, after: int = 0):
    lines = _logs.get(story_id) or _load_log(story_id)
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
        asyncio.create_task(_sample_bg(story_id, sample_id))
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
        _log(story_id, "--- Phase 2: analyzing ---")
        result = await analyze_story(story, sample_id, on_message=on_msg)
        if result:
            _running[story_id] = {"phase": Phase.Synthesizing, "sample": sample_id}
            _log(story_id, "--- Phase 3: synthesizing ---")
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
            sid = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            asyncio.create_task(_sample_bg(s["id"], sid))
    return RedirectResponse("/", status_code=303)
