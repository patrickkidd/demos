import pytest


@pytest.mark.asyncio
async def test_api_status_empty(client):
    resp = await client.get("/api/status")
    assert resp.status_code == 200
    assert resp.json() == {}


@pytest.mark.asyncio
async def test_api_log_empty(client):
    resp = await client.get("/api/stories/nonexistent/log")
    assert resp.status_code == 200
    assert resp.json() == {"lines": [], "total": 0}


@pytest.mark.asyncio
async def test_api_log_after_param(client, monkeypatch):
    from app.main import _logs
    _logs["s1"] = [f"line {i}" for i in range(10)]
    resp = await client.get("/api/stories/s1/log?after=7")
    data = resp.json()
    assert data["lines"] == ["line 7", "line 8", "line 9"]
    assert data["total"] == 10
    _logs.pop("s1", None)


@pytest.mark.asyncio
async def test_api_sample_json(client):
    resp = await client.get("/api/stories/s1/samples/20260407T120000")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "20260407T120000"
    assert data["article_count"] == 6
    assert "phase2" in data
    assert "phase3" in data
    assert len(data["phase2"]["opinion_axes"]) == 3
    assert "centroid_article" in data["phase3"]


@pytest.mark.asyncio
async def test_api_sample_partial(client):
    resp = await client.get("/api/stories/s1/samples/20260408T060000")
    data = resp.json()
    assert data["article_count"] == 3
    assert "phase2" not in data
    assert "phase3" not in data
