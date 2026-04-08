import json, sys, os
from pathlib import Path

import pytest

# Ensure project root is on sys.path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.fixtures.factories import make_story, make_phase1, make_phase2, make_phase3, make_manifest


@pytest.fixture
def instance_dir(tmp_path):
    d = tmp_path / "instance"
    d.mkdir()
    (d / "stories").mkdir()
    (d / "stories.json").write_text("[]")
    (d / "allsides_bias.csv").write_text("outlet,bias_label,bias_score\nReuters,Center,0.0\n")
    return d


@pytest.fixture
def populated_instance(instance_dir):
    story = make_story(id="s1", topic="US-Iran Relations", last_sample="20260407T120000")
    story2 = make_story(id="s2", topic="Budget Negotiations", active=True)

    (instance_dir / "stories.json").write_text(json.dumps([story, story2]))

    # Story 1: completed sample + partial sample
    s1 = instance_dir / "stories" / "s1"
    s1.mkdir()
    (s1 / "samples").mkdir()
    (s1 / "articles").mkdir()
    (s1 / "meta.json").write_text(json.dumps(story))

    # Completed sample
    sample1 = s1 / "samples" / "20260407T120000"
    sample1.mkdir()
    p1_dir = sample1 / "phase1"
    p1_dir.mkdir()
    outlets = ["Fox News", "NYT", "Reuters", "Al Jazeera", "PBS", "BBC"]
    for i, outlet in enumerate(outlets):
        (p1_dir / f"article-{i}.json").write_text(
            json.dumps(make_phase1(outlet=outlet, url=f"https://example.com/{i}"))
        )
    phase2 = make_phase2(outlets=outlets)
    (sample1 / "phase2.json").write_text(json.dumps(phase2))
    (sample1 / "phase3.json").write_text(json.dumps(make_phase3(phase2)))
    (sample1 / "manifest.json").write_text(json.dumps(make_manifest(outlets=outlets)))

    # Partial sample (phase1 only)
    sample2 = s1 / "samples" / "20260408T060000"
    sample2.mkdir()
    p1_dir2 = sample2 / "phase1"
    p1_dir2.mkdir()
    for i in range(3):
        (p1_dir2 / f"article-{i}.json").write_text(
            json.dumps(make_phase1(outlet=f"Outlet{i}"))
        )

    # Story 2: no samples
    s2 = instance_dir / "stories" / "s2"
    s2.mkdir()
    (s2 / "samples").mkdir()
    (s2 / "articles").mkdir()
    (s2 / "meta.json").write_text(json.dumps(story2))

    return instance_dir


@pytest.fixture
def patched_app(populated_instance, monkeypatch):
    monkeypatch.setattr("app.main.DATA", populated_instance)
    monkeypatch.setattr("scripts.phase1_extract.DATA", populated_instance)
    monkeypatch.setattr("scripts.phase2_analyze.DATA", populated_instance)
    monkeypatch.setattr("scripts.phase3_synthesize.DATA", populated_instance)

    # Fix template directory for local (non-Docker) testing
    from starlette.templating import Jinja2Templates
    local_templates = str(Path(__file__).parent.parent / "app" / "templates")
    monkeypatch.setattr("app.main.templates", Jinja2Templates(directory=local_templates))

    from app.main import app
    return app


@pytest.fixture
def client(patched_app):
    from httpx import ASGITransport, AsyncClient
    transport = ASGITransport(app=patched_app)
    return AsyncClient(transport=transport, base_url="http://test")
