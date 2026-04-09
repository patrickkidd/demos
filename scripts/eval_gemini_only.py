"""Run Gemini Flash extraction only."""

import json
import sys
import time
from pathlib import Path

import google.generativeai as genai

PROMPT_PATH = Path("/Users/patrick/demos/prompts/extract_article.md")
ARTICLE_PATH = Path(
    "/Users/patrick/demos/instance/stories/a0829f0c/samples/20260409T170054/"
    "articles/www-npr-org-2026-04-09-nx-s1-5779000-iran-war-updates.txt"
)
OUT_DIR = Path("/Users/patrick/demos/instance/eval")

GEMINI_KEY = sys.argv[1]


def run_gemini(system_prompt: str, article: str) -> dict:
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel(
        "gemini-2.0-flash",
        system_instruction=system_prompt,
    )
    t0 = time.time()
    resp = model.generate_content(article)
    elapsed = time.time() - t0
    return {"raw": resp.text, "elapsed": elapsed, "model": "gemini-2.0-flash"}


def parse_json(raw: str) -> dict | None:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        return {"_parse_error": str(e), "_raw_excerpt": text[:500]}


def main():
    system_prompt = PROMPT_PATH.read_text()
    article = ARTICLE_PATH.read_text()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Running Gemini Flash...", flush=True)
    result = run_gemini(system_prompt, article)
    print(f"  Done in {result['elapsed']:.1f}s")

    parsed = parse_json(result["raw"])
    (OUT_DIR / "gemini_flash.json").write_text(json.dumps(parsed, indent=2))

    if "_parse_error" in parsed:
        print(f"  WARNING: JSON parse failed: {parsed['_parse_error']}")
        print(f"  Raw excerpt: {parsed['_raw_excerpt']}")
    else:
        fc = len(parsed.get("factual_claims", []))
        op = len(parsed.get("opinion_statements", []))
        ea = len(parsed.get("emotional_appeals", []))
        ig = len(parsed.get("internal_gaps", []))
        ll = len(parsed.get("framing", {}).get("loaded_language", []))
        sq = len(parsed.get("framing", {}).get("sources_quoted", []))
        sm = parsed.get("summary_metrics", {})
        print(f"  {fc} facts, {op} opinions, {ea} emotional appeals, "
              f"{ig} gaps, {ll} loaded terms, {sq} sources")
        print(f"  Metrics: {json.dumps(sm)}")

    # Also dump raw for inspection
    (OUT_DIR / "gemini_flash_raw.txt").write_text(result["raw"])


if __name__ == "__main__":
    main()
