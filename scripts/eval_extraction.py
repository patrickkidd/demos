"""Compare Claude Sonnet vs Gemini Flash on article extraction."""

import json
import sys
import time
from pathlib import Path

import anthropic
import google.generativeai as genai

PROMPT_PATH = Path("/Users/patrick/demos/prompts/extract_article.md")
ARTICLE_PATH = Path(
    "/Users/patrick/demos/instance/stories/a0829f0c/samples/20260409T170054/"
    "articles/www-npr-org-2026-04-09-nx-s1-5779000-iran-war-updates.txt"
)
OUT_DIR = Path("/Users/patrick/demos/instance/eval")

GEMINI_KEY = sys.argv[1]


def run_claude(system_prompt: str, article: str) -> dict:
    client = anthropic.Anthropic()
    t0 = time.time()
    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8192,
        system=system_prompt,
        messages=[{"role": "user", "content": article}],
    )
    elapsed = time.time() - t0
    text = resp.content[0].text
    return {"raw": text, "elapsed": elapsed, "model": "claude-sonnet-4-20250514"}


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

    print("Running Claude Sonnet...", flush=True)
    claude_result = run_claude(system_prompt, article)
    print(f"  Done in {claude_result['elapsed']:.1f}s")

    print("Running Gemini Flash...", flush=True)
    gemini_result = run_gemini(system_prompt, article)
    print(f"  Done in {gemini_result['elapsed']:.1f}s")

    claude_json = parse_json(claude_result["raw"])
    gemini_json = parse_json(gemini_result["raw"])

    (OUT_DIR / "claude_sonnet.json").write_text(json.dumps(claude_json, indent=2))
    (OUT_DIR / "gemini_flash.json").write_text(json.dumps(gemini_json, indent=2))

    print("\nOutputs saved to instance/eval/")
    print(f"  Claude: {len(claude_result['raw'])} chars, {claude_result['elapsed']:.1f}s")
    print(f"  Gemini: {len(gemini_result['raw'])} chars, {gemini_result['elapsed']:.1f}s")

    for label, data in [("Claude", claude_json), ("Gemini", gemini_json)]:
        if "_parse_error" in data:
            print(f"\n  WARNING: {label} output failed JSON parse: {data['_parse_error']}")
        else:
            fc = len(data.get("factual_claims", []))
            op = len(data.get("opinion_statements", []))
            ea = len(data.get("emotional_appeals", []))
            ig = len(data.get("internal_gaps", []))
            ll = len(data.get("framing", {}).get("loaded_language", []))
            sq = len(data.get("framing", {}).get("sources_quoted", []))
            sm = data.get("summary_metrics", {})
            print(f"\n  {label}: {fc} facts, {op} opinions, {ea} emotional appeals, "
                  f"{ig} gaps, {ll} loaded terms, {sq} sources")
            print(f"    Metrics: {json.dumps(sm, indent=None)}")


if __name__ == "__main__":
    main()
