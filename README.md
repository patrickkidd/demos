# Demos

Collective intelligence applied to political media analysis. Claude agents
sample news coverage across the political spectrum, separate fact from opinion,
and synthesize a centroid article representing the most objective available
understanding of each story.

## TLDR

```bash
# Prerequisites: Docker, Claude Max subscription, claude CLI on host
docker compose up --build -d
./scripts/export_auth.sh && docker compose restart
open http://localhost:8000
# Add a topic, click "Sample" — watch it progress through extracting → analyzing → synthesizing
# Click the green dot on the timeline to see the centroid article and opinion landscape
```

---

## How it works

Each "sample" collects 15-25 articles from diverse outlets on a topic and runs
a 3-phase pipeline:

**Phase 1 — Extract** (Sonnet, parallel per article)
Blind per-article analysis: facts with 5-tier sourcing, opinions with intensity
and implied worldview, framing metadata, emotional appeals. Outlet identity
hidden from the model.

**Phase 2 — Aggregate** (Opus)
Deduplicate facts and opinions across articles, tag each with contributing
outlets, group opinions into issue axes with opposing poles, order axes by
topical relatedness.

**Phase 3 — Synthesize** (Opus)
Write a per-axis centroid conclusion (balanced by evidence weight), then
synthesize a meta-centroid article — what a perfectly informed, unbiased
reporter would write.

See `/methodology` in the web UI for the full theoretical basis (collective
intelligence research, Bowen's family systems theory, Haidt's moral
foundations).

**Dashboard**
- `/` — topic list with inline timelines, Sample buttons
- `/story/{id}` — timeline, centroid article, circular opinion landscape,
  axis conclusions, deduplicated facts
- `/methodology` — theoretical foundations and pipeline documentation
- `/auth` — authentication status

---

## Setup

### 1. Build and run

```bash
docker compose up --build -d
```

### 2. Authenticate

OAuth in Docker is a [known upstream issue](https://github.com/anthropics/claude-code/issues/34917).
The workaround: authenticate on your host, then export credentials to the
container volume.

```bash
# If not already logged in on your host:
claude auth login

# Export credentials from macOS Keychain to the container volume:
./scripts/export_auth.sh
docker compose restart
```

Verify at `http://localhost:8000/auth`. Credentials persist in
`./instance/.claude/` across container rebuilds.

### 3. Use it

Open `http://localhost:8000`. Add a topic (e.g., "US-Iran relations"). Click
**Sample**. The status badge updates through extracting → analyzing →
synthesizing. When done, a green dot appears on the timeline. Click it.

The watchdog also auto-samples all active topics once daily when the machine
is awake.

---

## Data layout

```
instance/
├── stories.json                 # topic registry
├── allsides_bias.csv            # outlet bias ratings (collection only)
└── stories/{id}/
    ├── meta.json
    ├── articles/                # raw article text (shared across samples)
    └── samples/{YYYYMMDDTHHMMSS}/
        ├── manifest.json        # collected article list
        ├── phase1/              # per-article extraction JSONs
        │   └── {slug}.json
        ├── phase2.json          # deduplicated facts + opinion axes
        └── phase3.json          # axis centroids + centroid article
```

Data is bind-mounted to `./instance/` on the host.

---

## First run notes

If upgrading from a previous version, delete the old test data:

```bash
rm -rf instance/stories/*/runs
```

The V2 pipeline uses `samples/` instead of `runs/`.

---

## Bias data

`data/allsides_bias.csv` ships with ~25 major outlets, used only to guide
source diversity during article collection. To add outlets:

```
outlet,bias_label,bias_score
My Outlet,Center,0.0
```

Score range: -2.0 (far left) to +2.0 (far right).
