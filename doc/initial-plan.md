# Demos — Spec V1
## Collective intelligence applied to political media analysis
## Everything through Claude Code agent SDK. No other AI dependencies.

---

## 1. Architecture

```
cron
  ├── phase1_extract.py    # daily — agent collects articles, writes run JSON
  └── phase2_analyze.py    # weekly — agent clusters, synthesizes, writes analysis JSON

FastAPI
  └── read-only dashboard
  └── POST /stories
```

Two scripts. One web app. One AI dependency (claude-code-sdk).

---

## 2. Directory Structure

```
demos/
├── Dockerfile
├── docker-compose.yml
├── Caddyfile
├── entrypoint.sh
├── crontab
├── requirements.txt
├── .env.example
├── data/                             # named Docker volume
│   ├── stories.json
│   ├── corpus.json
│   ├── allsides_bias.csv
│   └── stories/
│       └── {story_id}/
│           ├── meta.json
│           ├── analysis.json         # phase 2 output
│           └── runs/
│               └── {timestamp}.json # phase 1 output
├── app/
│   ├── main.py
│   └── templates/
│       ├── base.html
│       ├── index.html
│       ├── story.html
│       └── corpus.html
├── prompts/
│   ├── extract.md                    # phase 1 agent prompt
│   └── analyze.md                   # phase 2 agent prompt
└── scripts/
    ├── init_data.py
    ├── phase1_extract.py
    └── phase2_analyze.py
```

---

## 3. Phase 1 Prompt (prompts/extract.md)

Blind extraction. No framing assumptions. No pole labels.

```
You are a news extraction agent.

TOPIC: {topic}
OUTPUT PATH: {output_path}
ARTICLE DIR: {article_dir}
BIAS DATA: /data/allsides_bias.csv

1. SEARCH
   Search the web for 15-25 recent news articles on this topic.
   Prioritize outlet diversity. Do not filter by political lean.
   Look up each outlet in the CSV for bias_label and bias_score.
   If not found: bias_label "unknown", bias_score null.
   Record ALL URLs found, not just ones you fetch.

2. FOR EACH ARTICLE
   a. Fetch full text
   b. Save raw extracted text to {article_dir}/{{url_slug}}.txt
   c. Produce a losslessly compressed markdown version:
      - Remove ads, navigation, boilerplate
      - Preserve all substantive content, all named sources,
        all quotes, all specific facts, all figures and dates
      - Do not paraphrase or summarize — only remove noise
   d. Write a structured summary:
      - What happened: the core event as reported
      - Who is responsible according to this article
      - Key facts cited with their sources
      - Exact quotes used (headline and body separately)
      - What this article does not mention that is known
        from other articles fetched in this run
   e. Skip articles under 200 words after extraction

3. ANALYZE EACH ARTICLE INDEPENDENTLY
   Extract without interpretation:
   - facts: statements presented as true, with source if named
   - opinions: interpretive statements, with attribution if present
   - inflammatory_language: loaded phrases, location, neutral description
   - foregrounded: topics given prominent placement or repetition
   - backgrounded: topics mentioned briefly or once
   - headline_tone: neutral / sympathetic / critical / inflammatory
   - primary_frame: one sentence — what interpretive lens does this article use?

   Do not compare articles. Do not assign political labels.

4. WRITE OUTPUT to {output_path}:
   {{
     "topic": str,
     "run_at": str,
     "urls_found": [str],
     "urls_fetched": [str],
     "articles": [
       {{
         "url": str,
         "outlet": str,
         "bias_label": str,
         "bias_score": float | null,
         "raw_path": str,
         "compressed_markdown": str,
         "structured_summary": {{
           "what_happened": str,
           "responsibility_claim": str,
           "key_facts": [{{"claim": str, "source": str | null}}],
           "quotes": [{{"text": str, "location": str}}],
           "notable_omissions": [str]
         }},
         "facts": [{{"claim": str, "sourced": bool, "source": str | null}}],
         "opinions": [{{"claim": str, "attributed_to": str | null}}],
         "inflammatory_language": [{{"phrase": str, "location": str, "description": str}}],
         "foregrounded": [str],
         "backgrounded": [str],
         "headline_tone": str,
         "primary_frame": str
       }}
     ]
   }}
```

---

## 4. Phase 2 Prompt (prompts/analyze.md)

```
You are a media analysis agent.

TOPIC: {topic}
INPUT PATH: {input_path}
OUTPUT PATH: {output_path}

Read the JSON file at INPUT PATH. It contains articles extracted from
news coverage of the topic. Each article has facts, opinions, framing,
and outlet bias metadata.

1. GROUP ARTICLES BY FRAMING SIMILARITY
   Read all primary_frame values and foregrounded/backgrounded lists.
   Group articles that share a similar interpretive lens.
   Do not assume how many groups there are — let it emerge from the content.
   Do not label groups as left or right unless the content clearly warrants it.
   Characterize each group by what it emphasizes and what it omits.
   Note the bias_score distribution of outlets in each group.

2. IDENTIFY ACROSS ALL ARTICLES
   - Shared factual core: facts appearing across multiple groups
   - Contested claims: where groups actually disagree on facts
   - Selective omissions: facts one group reports that another omits

3. WRITE CENTROID NARRATIVE
   4-6 paragraphs, neutral precise language.
   Incorporate the shared factual core.
   Acknowledge genuine uncertainties.
   Do not produce false balance — place the centroid where the evidence sits.
   If one group has significantly less factual support than others,
   note this explicitly.

4. SCORE
   asymmetry_score (0.0-1.0): how unequal are the factual bases across groups?
   pole_distance (0.0-1.0): how far apart are the frames?

5. WRITE OUTPUT to {output_path}:
   {{
     "topic": str,
     "analyzed_at": str,
     "article_count": int,
     "groups": [
       {{
         "label": str,
         "description": str,
         "outlets": [str],
         "avg_bias_score": float | null,
         "characteristic_language": [str],
         "key_omissions": [str]
       }}
     ],
     "shared_facts": [{{"claim": str, "group_count": int}}],
     "contested_claims": [{{"claim": str, "positions": {{group_label: str}}}}],
     "selective_omissions": [
       {{"fact": str, "reported_by": [str], "omitted_by": [str]}}
     ],
     "centroid_narrative": str,
     "unresolved": [str],
     "asymmetry_score": float,
     "pole_distance": float
   }}
```

---

## 5. scripts/phase1_extract.py

```python
import json, asyncio
from pathlib import Path
from datetime import datetime, timezone
from claude_code_sdk import query, ClaudeCodeOptions

DATA = Path("/data")

async def run_story(story: dict):
    runs_dir = DATA / "stories" / story["id"] / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    article_dir = DATA / "stories" / story["id"] / "articles"
    article_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    output_path = str(runs_dir / f"{ts}.json")
    prompt = Path("/app/prompts/extract.md").read_text().format(
        topic=story["topic"],
        output_path=output_path,
        article_dir=str(article_dir)
    )
    await query(prompt=prompt, options=ClaudeCodeOptions())
    story["last_run_at"] = datetime.now(timezone.utc).isoformat()

async def main():
    stories_path = DATA / "stories.json"
    stories = json.loads(stories_path.read_text())
    for story in [s for s in stories if s.get("active")]:
        print(f"Extracting: {story['topic']}")
        try:
            await run_story(story)
        except Exception as e:
            print(f"  Failed: {e}")
    stories_path.write_text(json.dumps(stories, indent=2))

asyncio.run(main())
```

---

## 6. scripts/phase2_analyze.py

```python
import json, asyncio
from pathlib import Path
from datetime import datetime, timezone
from claude_code_sdk import query, ClaudeCodeOptions

DATA = Path("/data")

def load_all_articles(story: dict) -> list:
    runs_dir = DATA / "stories" / story["id"] / "runs"
    seen, articles = set(), []
    for rf in sorted(runs_dir.glob("*.json")):
        for a in json.loads(rf.read_text()).get("articles", []):
            if a["url"] not in seen:
                seen.add(a["url"])
                articles.append(a)
    return articles

async def analyze_story(story: dict):
    articles = load_all_articles(story)
    if len(articles) < 5:
        print(f"  Skipping {story['topic']} — only {len(articles)} articles")
        return None

    input_path = f"/tmp/{story['id']}_articles.json"
    output_path = f"/tmp/{story['id']}_analysis.json"
    Path(input_path).write_text(json.dumps(articles, indent=2))

    prompt = Path("/app/prompts/analyze.md").read_text().format(
        topic=story["topic"],
        input_path=input_path,
        output_path=output_path
    )
    await query(prompt=prompt, options=ClaudeCodeOptions())

    analysis = json.loads(Path(output_path).read_text())
    analysis["story_id"] = story["id"]
    analysis["article_count"] = len(articles)
    analysis["run_count"] = len(list(
        (DATA / "stories" / story["id"] / "runs").glob("*.json")
    ))

    (DATA / "stories" / story["id"] / "analysis.json").write_text(
        json.dumps(analysis, indent=2)
    )
    return analysis

def build_corpus(stories: list, analyses: list):
    from collections import defaultdict
    omissions = defaultdict(list)
    for a in analyses:
        for o in a.get("selective_omissions", []):
            for group in o.get("omitted_by", []):
                omissions[group].append({
                    "story": a["topic"],
                    "fact": o["fact"]
                })
    corpus = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "story_count": len(analyses),
        "stories": analyses,
        "asymmetry_ranking": sorted(
            analyses, key=lambda x: x.get("asymmetry_score", 0), reverse=True
        ),
        "pole_distance_ranking": sorted(
            analyses, key=lambda x: x.get("pole_distance", 0), reverse=True
        ),
        "group_omissions": dict(omissions)
    }
    (DATA / "corpus.json").write_text(json.dumps(corpus, indent=2))

async def main():
    stories = json.loads((DATA / "stories.json").read_text())
    analyses = []
    for story in stories:
        print(f"Analyzing: {story['topic']}")
        result = await analyze_story(story)
        if result:
            analyses.append(result)
    build_corpus(stories, analyses)
    print(f"Done. {len(analyses)} stories analyzed.")

asyncio.run(main())
```

---

## 7. app/main.py

```python
from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
import json, uuid
from pathlib import Path
from datetime import datetime, timezone

app = FastAPI()
templates = Jinja2Templates(directory="/app/app/templates")
DATA = Path("/data")

@app.get("/")
async def index(request: Request):
    stories = json.loads((DATA / "stories.json").read_text())
    for s in stories:
        p = DATA / "stories" / s["id"] / "analysis.json"
        if p.exists():
            a = json.loads(p.read_text())
            s["asymmetry_score"] = a.get("asymmetry_score")
            s["pole_distance"] = a.get("pole_distance")
            s["article_count"] = a.get("article_count")
    return templates.TemplateResponse("index.html", {
        "request": request, "stories": stories
    })

@app.get("/story/{story_id}")
async def story(request: Request, story_id: str):
    meta = json.loads((DATA / "stories" / story_id / "meta.json").read_text())
    p = DATA / "stories" / story_id / "analysis.json"
    analysis = json.loads(p.read_text()) if p.exists() else None
    run_count = len(list((DATA / "stories" / story_id / "runs").glob("*.json")))
    return templates.TemplateResponse("story.html", {
        "request": request, "meta": meta,
        "analysis": analysis, "run_count": run_count
    })

@app.get("/corpus")
async def corpus(request: Request):
    p = DATA / "corpus.json"
    corpus = json.loads(p.read_text()) if p.exists() else {}
    return templates.TemplateResponse("corpus.html", {
        "request": request, "corpus": corpus
    })

@app.post("/stories")
async def add_story(topic: str = Form(...), seed_url: str = Form("")):
    stories = json.loads((DATA / "stories.json").read_text())
    sid = str(uuid.uuid4())[:8]
    story = {
        "id": sid, "topic": topic,
        "seed_url": seed_url or None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_run_at": None, "active": True
    }
    stories.append(story)
    (DATA / "stories.json").write_text(json.dumps(stories, indent=2))
    d = DATA / "stories" / sid
    d.mkdir(parents=True, exist_ok=True)
    (d / "runs").mkdir(exist_ok=True)
    (d / "meta.json").write_text(json.dumps(story, indent=2))
    return RedirectResponse("/", status_code=303)
```

---

## 8. requirements.txt

```
fastapi
uvicorn[standard]
jinja2
python-multipart
claude-code-sdk
```

That's the entire dependency list.

---

## 9. Dockerfile

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY crontab /etc/cron.d/synthesis
RUN chmod 0644 /etc/cron.d/synthesis && crontab /etc/cron.d/synthesis
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
CMD ["/entrypoint.sh"]
```

---

## 10. entrypoint.sh

```bash
#!/bin/bash
set -e
python /app/scripts/init_data.py
[ ! -f /data/allsides_bias.csv ] && cp /app/data/allsides_bias.csv /data/allsides_bias.csv
service cron start
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## 11. crontab

```
0 6 * * * cd /app && python scripts/phase1_extract.py >> /var/log/demos.log 2>&1
0 8 * * 0 cd /app && python scripts/phase2_analyze.py >> /var/log/demos.log 2>&1
```

---

## 12. docker-compose.yml

```yaml
version: "3.9"
services:
  app:
    build: .
    restart: unless-stopped
    env_file: .env
    volumes:
      - demos_data:/data
    ports:
      - "8000:8000"
  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config
volumes:
  demos_data:
  caddy_data:
  caddy_config:
```

---

## 13. Caddyfile

```
your-domain.com {
    reverse_proxy app:8000
}
```

---

## 14. .env.example

```
ANTHROPIC_API_KEY=sk-ant-...
```

---

## 15. Dashboard (spec for Claude Code)

### index.html
Story submission form. Table of stories with topic, article count,
asymmetry score (color-coded red/yellow/green), pole distance, last run.

### story.html
- Centroid narrative prominent at top
- Emergent groups table: one column per group, showing label,
  description, outlets, avg bias score, key omissions
- Selective omissions list
- Unresolved questions list
- Asymmetry and pole distance scores with plain English description
- Collapsible article list: outlet, bias label, headline tone,
  primary frame, summary cliff notes

### corpus.html
- Stories ranked by asymmetry
- Stories ranked by pole distance
- Group omission signatures: what each emergent group type
  consistently omits across stories
- Chart.js scatter: asymmetry vs pole distance across all stories

---

## 16. Build Order for Claude Code

1. Dockerfile + entrypoint.sh + docker-compose.yml + Caddyfile + .env.example
2. requirements.txt
3. scripts/init_data.py
4. prompts/extract.md + prompts/analyze.md
5. scripts/phase1_extract.py
6. scripts/phase2_analyze.py
7. app/main.py
8. app/templates/
9. data/allsides_bias.csv (source manually from AllSides)

Test sequence:
- docker compose up
- Add a story via the web form
- docker compose exec app python scripts/phase1_extract.py
- Verify run JSON in volume
- docker compose exec app python scripts/phase2_analyze.py
- Verify analysis.json and corpus.json
- Check all dashboard views render