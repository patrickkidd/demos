import json
import pytest
from pathlib import Path


@pytest.mark.asyncio
async def test_add_story(client, populated_instance):
    resp = await client.post("/stories", data={"topic": "New Topic", "seed_url": ""}, follow_redirects=False)
    assert resp.status_code == 303

    stories = json.loads((populated_instance / "stories.json").read_text())
    new = [s for s in stories if s["topic"] == "New Topic"]
    assert len(new) == 1
    assert new[0]["active"] is True
    assert new[0]["seed_url"] is None
    assert len(new[0]["id"]) == 8

    story_dir = populated_instance / "stories" / new[0]["id"]
    assert (story_dir / "samples").is_dir()
    assert (story_dir / "articles").is_dir()
    assert (story_dir / "meta.json").exists()


@pytest.mark.asyncio
async def test_add_story_with_seed_url(client, populated_instance):
    resp = await client.post("/stories", data={"topic": "T", "seed_url": "https://example.com"}, follow_redirects=False)
    assert resp.status_code == 303
    stories = json.loads((populated_instance / "stories.json").read_text())
    new = [s for s in stories if s["topic"] == "T"][0]
    assert new["seed_url"] == "https://example.com"


@pytest.mark.asyncio
async def test_delete_story(client, populated_instance):
    resp = await client.post("/stories/s1/delete", follow_redirects=False)
    assert resp.status_code == 303

    stories = json.loads((populated_instance / "stories.json").read_text())
    assert not any(s["id"] == "s1" for s in stories)
    assert not (populated_instance / "stories" / "s1").exists()


@pytest.mark.asyncio
async def test_delete_story_nonexistent(client, populated_instance):
    resp = await client.post("/stories/nonexistent/delete", follow_redirects=False)
    assert resp.status_code == 303
    stories = json.loads((populated_instance / "stories.json").read_text())
    assert len(stories) == 2


@pytest.mark.asyncio
async def test_delete_sample(client, populated_instance):
    assert (populated_instance / "stories" / "s1" / "samples" / "20260407T120000").exists()
    resp = await client.post("/stories/s1/samples/20260407T120000/delete", follow_redirects=False)
    assert resp.status_code == 303
    assert not (populated_instance / "stories" / "s1" / "samples" / "20260407T120000").exists()
    # Other sample still exists
    assert (populated_instance / "stories" / "s1" / "samples" / "20260408T060000").exists()


@pytest.mark.asyncio
async def test_delete_sample_nonexistent(client, populated_instance):
    resp = await client.post("/stories/s1/samples/99990101T000000/delete", follow_redirects=False)
    assert resp.status_code == 303
