"""HTML structure assertions for sample.html and story.html."""
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
async def test_neutral_summary_paragraphs(client):
    resp = await client.get("/story/s1/samples/20260407T120000")
    soup = BeautifulSoup(resp.text, "html.parser")
    article_div = soup.select_one(".centroid-article")
    assert article_div is not None
    paragraphs = article_div.find_all("p")
    assert len(paragraphs) == 4


@pytest.mark.asyncio
async def test_headline_hidden_when_absent(client):
    resp = await client.get("/story/s1/samples/20260407T120000")
    soup = BeautifulSoup(resp.text, "html.parser")
    # No headline field in test fixture → headline section not rendered
    h1s = [h for h in soup.find_all("h1") if h.text.strip() and "font-size:20px" in h.get("style", "")]
    assert len(h1s) == 0


@pytest.mark.asyncio
async def test_tabs_present(client):
    resp = await client.get("/story/s1/samples/20260407T120000")
    soup = BeautifulSoup(resp.text, "html.parser")
    tabs = soup.select(".tab")
    assert len(tabs) == 2
    labels = [t.text.strip() for t in tabs]
    assert "Opinions" in labels[0]
    # Opinions tab is active by default
    assert "active" in tabs[0].get("class", [])


@pytest.mark.asyncio
async def test_facts_in_tab(client):
    resp = await client.get("/story/s1/samples/20260407T120000")
    soup = BeautifulSoup(resp.text, "html.parser")
    facts_tab = soup.select_one("#tab-facts")
    assert facts_tab is not None
    tags = facts_tab.select(".fact-list .tag")
    assert len(tags) > 0


@pytest.mark.asyncio
async def test_opinion_spectrum_container(client):
    resp = await client.get("/story/s1/samples/20260407T120000")
    soup = BeautifulSoup(resp.text, "html.parser")
    assert soup.select_one("#opinion-spectrum") is not None


@pytest.mark.asyncio
async def test_viz_json_embedded(client):
    resp = await client.get("/story/s1/samples/20260407T120000")
    assert "const phase2 = " in resp.text
    assert "const phase3 = " in resp.text
    start = resp.text.index("const phase2 = ") + len("const phase2 = ")
    end = resp.text.index(";\n", start)
    phase2_json = json.loads(resp.text[start:end])
    assert "opinion_axes" in phase2_json
    assert "axis_order" in phase2_json


@pytest.mark.asyncio
async def test_bias_severity_sort_in_js(client):
    resp = await client.get("/story/s1/samples/20260407T120000")
    assert "biasSeverity" in resp.text


@pytest.mark.asyncio
async def test_centroid_toggle_in_js(client):
    resp = await client.get("/story/s1/samples/20260407T120000")
    assert "centroid-toggle" in resp.text
    assert "Fact Check" in resp.text


@pytest.mark.asyncio
async def test_tab_switching_js(client):
    resp = await client.get("/story/s1/samples/20260407T120000")
    assert "tab.dataset.tab" in resp.text


@pytest.mark.asyncio
async def test_no_circle_viz(client):
    resp = await client.get("/story/s1/samples/20260407T120000")
    assert "viz-canvas" not in resp.text
    assert "viz-container" not in resp.text


@pytest.mark.asyncio
async def test_delete_sample_button_present(client):
    resp = await client.get("/story/s1/samples/20260407T120000")
    soup = BeautifulSoup(resp.text, "html.parser")
    delete_form = soup.select_one('form[action*="delete"]')
    assert delete_form is not None
    assert "20260407T120000" in delete_form["action"]


@pytest.mark.asyncio
async def test_sample_button_present_on_story_page(client):
    resp = await client.get("/story/s1")
    soup = BeautifulSoup(resp.text, "html.parser")
    sample_form = soup.select_one('form[action*="/sample"]')
    assert sample_form is not None
