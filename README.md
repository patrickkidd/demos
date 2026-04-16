# Demos

A news reader that shows you what every outlet is saying — and what they're
leaving out. Demos samples 28 outlets across the political spectrum, separates
fact from opinion, and shows you where the biases are so you can make up your
own mind.

```bash
docker compose up --build -d
./scripts/export_auth.sh && docker compose restart
open http://localhost:8000
```

Add a topic. Click **Sample**. Get the full picture in minutes.

<img src="doc/screenshots/Screenshot%202026-04-16%20at%207.20.18%20AM.png" width="520" alt="Landing page — story list with sample timeline">

<img src="doc/screenshots/Screenshot%202026-04-16%20at%207.20.47%20AM.png" width="520" alt="Sample analysis — biggest gap between narrative and evidence">

<img src="doc/screenshots/Screenshot%202026-04-16%20at%207.21.05%20AM.png" width="520" alt="Outlet picker — what your source is not telling you">

<img src="doc/screenshots/Screenshot%202026-04-16%20at%207.21.20%20AM.png" width="520" alt="The full picture — consensus, divergence, and blind spots">

---

## How it works

Each sample queries 28 outlets (27 news + White House) and runs a 4-phase
pipeline:

1. **Extract** — blind per-article analysis (facts, opinions, framing)
2. **Aggregate** — deduplicate across outlets, map opinion axes
3. **Cluster** — group into 3-5 key developments
4. **Synthesize** — balanced centroid conclusions + neutral summary article

See `/methodology` in the app for the theoretical basis.

---

## Setup

**Prerequisites**: Docker, Claude Max subscription, `claude` CLI on your Mac.

```bash
# Build and start
docker compose up --build -d

# Authenticate (one-time, or when tokens expire)
claude auth login          # if not already logged in on host
./scripts/export_auth.sh
docker compose restart
```

Verify at `http://localhost:8000/auth`.

---

## Data

```
instance/stories/{id}/samples/{timestamp}/
  articles/         # raw article text
  phase1/           # per-article extraction JSONs
  phase2.json       # deduplicated facts + opinion axes
  phase3.json       # clustered developments
  phase4.json       # centroid synthesis + neutral article
```

Bind-mounted to `./instance/` on the host.

---

## Outlet data

`app/outlets.json` ships with 27 outlets rated by AllSides. Add entries to
include more outlets in sampling:

```json
{"outlet": "My Outlet", "bias_label": "Center", "bias_score": 0.0}
```
