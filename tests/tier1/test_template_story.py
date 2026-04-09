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
async def test_summary_paragraphs(client):
    resp = await client.get("/story/s1/samples/20260407T120000")
    soup = BeautifulSoup(resp.text, "html.parser")
    article_div = soup.select_one(".centroid-article")
    assert article_div is not None
    paragraphs = article_div.find_all("p")
    assert len(paragraphs) == 4


@pytest.mark.asyncio
async def test_headline_present(client):
    resp = await client.get("/story/s1/samples/20260407T120000")
    soup = BeautifulSoup(resp.text, "html.parser")
    headline = soup.select_one(".article-headline")
    assert headline is not None
    assert "Test Headline" in headline.text


@pytest.mark.asyncio
async def test_key_developments_section(client):
    resp = await client.get("/story/s1/samples/20260407T120000")
    soup = BeautifulSoup(resp.text, "html.parser")
    assert soup.select_one("#developments") is not None


@pytest.mark.asyncio
async def test_all_data_collapsible(client):
    resp = await client.get("/story/s1/samples/20260407T120000")
    soup = BeautifulSoup(resp.text, "html.parser")
    details = soup.select_one("#all-data")
    assert details is not None
    assert "All data" in details.select_one("summary").text


@pytest.mark.asyncio
async def test_tabs_inside_all_data(client):
    resp = await client.get("/story/s1/samples/20260407T120000")
    soup = BeautifulSoup(resp.text, "html.parser")
    tabs = soup.select(".tab")
    assert len(tabs) == 3
    labels = [t.text.strip() for t in tabs]
    assert any("Opinions" in l for l in labels)
    assert any("Facts" in l for l in labels)
    assert any("Summary" in l for l in labels)


@pytest.mark.asyncio
async def test_opinion_spectrum_container(client):
    resp = await client.get("/story/s1/samples/20260407T120000")
    soup = BeautifulSoup(resp.text, "html.parser")
    assert soup.select_one("#opinion-spectrum") is not None


@pytest.mark.asyncio
async def test_viz_json_embedded(client):
    resp = await client.get("/story/s1/samples/20260407T120000")
    assert "const phase2 = " in resp.text
    assert "const synthesis = " in resp.text
    assert "const clusters = " in resp.text


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
async def test_no_circle_viz(client):
    resp = await client.get("/story/s1/samples/20260407T120000")
    assert "viz-canvas" not in resp.text


@pytest.mark.asyncio
async def test_delete_sample_button_present(client):
    resp = await client.get("/story/s1/samples/20260407T120000")
    soup = BeautifulSoup(resp.text, "html.parser")
    delete_form = soup.select_one('form[action*="delete"]')
    assert delete_form is not None


@pytest.mark.asyncio
async def test_sample_button_present_on_story_page(client):
    resp = await client.get("/story/s1")
    soup = BeautifulSoup(resp.text, "html.parser")
    sample_form = soup.select_one('form[action*="/sample"]')
    assert sample_form is not None
