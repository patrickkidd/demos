"""HTML structure assertions for story.html — the most complex template."""
import json
import pytest
from bs4 import BeautifulSoup


@pytest.mark.asyncio
async def test_timeline_dot_count(client):
    resp = await client.get("/story/s1")
    soup = BeautifulSoup(resp.text, "html.parser")
    dots = soup.select(".timeline-dot")
    assert len(dots) == 2


@pytest.mark.asyncio
async def test_timeline_active_dot(client):
    resp = await client.get("/story/s1/samples/20260407T120000")
    soup = BeautifulSoup(resp.text, "html.parser")
    active = soup.select(".timeline-dot.active")
    assert len(active) == 1
    assert active[0]["data-sample"] == "20260407T120000"


@pytest.mark.asyncio
async def test_timeline_analyzed_dot_color(client):
    resp = await client.get("/story/s1")
    soup = BeautifulSoup(resp.text, "html.parser")
    analyzed = soup.select(".timeline-dot.has-analysis")
    assert len(analyzed) >= 1


@pytest.mark.asyncio
async def test_centroid_article_paragraphs(client):
    resp = await client.get("/story/s1/samples/20260407T120000")
    soup = BeautifulSoup(resp.text, "html.parser")
    article_div = soup.select_one(".centroid-article")
    assert article_div is not None
    paragraphs = article_div.find_all("p")
    assert len(paragraphs) == 4


@pytest.mark.asyncio
async def test_axis_centroids_rendered(client):
    resp = await client.get("/story/s1/samples/20260407T120000")
    soup = BeautifulSoup(resp.text, "html.parser")
    axes = soup.select(".axis-centroid")
    assert len(axes) == 3
    for ax in axes:
        assert ax.select_one(".pole-a") is not None
        assert ax.select_one(".pole-b") is not None
        assert ax.select_one(".conclusion") is not None


@pytest.mark.asyncio
async def test_axis_confidence_classes(client):
    resp = await client.get("/story/s1/samples/20260407T120000")
    soup = BeautifulSoup(resp.text, "html.parser")
    for cls in ["confidence-high", "confidence-medium", "confidence-low"]:
        assert soup.select_one(f".{cls}") is not None


@pytest.mark.asyncio
async def test_facts_section(client):
    resp = await client.get("/story/s1/samples/20260407T120000")
    soup = BeautifulSoup(resp.text, "html.parser")
    summary = soup.select_one("details summary")
    assert summary is not None
    assert "5 deduplicated facts" in summary.text


@pytest.mark.asyncio
async def test_facts_outlet_tags(client):
    resp = await client.get("/story/s1/samples/20260407T120000")
    soup = BeautifulSoup(resp.text, "html.parser")
    tags = soup.select(".fact-list .tag")
    assert len(tags) > 0


@pytest.mark.asyncio
async def test_viz_json_embedded(client):
    resp = await client.get("/story/s1/samples/20260407T120000")
    assert "const phase2 = " in resp.text
    # Extract the JSON and validate it
    start = resp.text.index("const phase2 = ") + len("const phase2 = ")
    end = resp.text.index(";\n", start)
    phase2_json = json.loads(resp.text[start:end])
    assert "opinion_axes" in phase2_json
    assert "axis_order" in phase2_json
    # Every axis_order ID exists in opinion_axes
    ax_ids = {a["id"] for a in phase2_json["opinion_axes"]}
    for order_id in phase2_json["axis_order"]:
        assert order_id in ax_ids


@pytest.mark.asyncio
async def test_delete_sample_button_present(client):
    resp = await client.get("/story/s1/samples/20260407T120000")
    soup = BeautifulSoup(resp.text, "html.parser")
    delete_form = soup.select_one('form[action*="delete"]')
    assert delete_form is not None
    assert "20260407T120000" in delete_form["action"]


@pytest.mark.asyncio
async def test_sample_button_present_when_not_running(client):
    resp = await client.get("/story/s1")
    soup = BeautifulSoup(resp.text, "html.parser")
    sample_form = soup.select_one('form[action*="/sample"]')
    assert sample_form is not None
