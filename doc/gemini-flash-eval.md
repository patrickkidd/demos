# Gemini Flash vs Claude Sonnet: Extraction Quality Eval

**Date:** 2026-04-09
**Test article:** NPR — "Trump warns strikes will resume if Iran doesn't agree to his terms" (~2k words)
**Prompt:** `prompts/extract_article.md` (identical for both)
**Outputs:** `instance/eval/claude_sonnet.json`, `instance/eval/gemini_flash.json`

## Result Summary

| Dimension | Claude Sonnet 4 | Gemini 2.0 Flash | Winner |
|---|---|---|---|
| Latency | ~94s (sub-agent) | ~31s | Gemini |
| Factual claims extracted | 33 | 31 | Tie |
| Opinion statements | 9 | 8 | Tie |
| Emotional appeals | 8 | 4 | Sonnet |
| Internal gaps detected | 8 | 3 | Sonnet |
| Loaded language identified | 8 | 4 | Sonnet |
| Sources quoted | 13 | 10 | Sonnet |
| JSON schema compliance | Valid | Valid | Tie |

## Quality Failures in Gemini Output

**Sourcing misclassification.** Leavitt's "thrown in the garbage" quote tagged `named_secondary` — should be `named_primary` (she has direct knowledge as press secretary). Saudi-Iran phone call tagged `unsourced` despite the article citing a Saudi Foreign Ministry statement. Trump's troop deployment statement marked `verifiable: false` when troop deployments are publicly trackable.

**Inflated sourcing_quality on opinions.** Iran's condemnation of Israel scored 1.0 (max). This is a political position, not a multi-sourced factual claim. Sonnet scored it 0.4.

**Vague worldview detection.** Gemini produces generic value statements ("strength and dominance are desirable") where Sonnet identifies specific analytical mechanisms ("assumes overwhelming military force is the primary leverage in diplomatic negotiations").

**Shallow gap detection.** Gemini's 3 gaps are surface-level observations. It misses: the Trump "workable" → "garbage" reversal with no explanation, evacuation orders for suburbs followed by strikes on central Beirut, absence of Al Jazeera/Wishah family response to terrorism allegation, Pakistan's unexplained role in the Lebanon inclusion dispute, and no legal basis discussion for Iran's $1M transit toll.

**Speaker field schema error.** Gemini uses the literal string `"quoted_source_name"` instead of actual names (e.g., "Donald Trump"). Would require post-processing to fix.

## Downstream Impact

The quality gaps hit the dimensions that feed later pipeline phases:
- Internal gaps → Phase 4 synthesis (Gemini misses >50% of what Sonnet catches)
- Loaded language → framing analysis and clustering (Gemini misses subtle editorial choices like "grinding halt", "shaky start", "deadliest day")
- Sourcing accuracy → `sourcing_quality_score` metric (errors propagate)
- Worldview detection → Phase 3 clustering (too vague to cluster on)

## Decision

**Gemini Flash is not a viable drop-in replacement for Phase 1 extraction.**

The speed gain (3x raw, ~5x vs Agent SDK cold-start) does not offset the quality loss in the dimensions that matter for downstream analysis. The better optimization target is the Agent SDK cold-start overhead, not the model.

A two-pass architecture (Gemini for initial extraction, Sonnet to deepen opinion/gap/framing) was considered but adds complexity for partial gain.
