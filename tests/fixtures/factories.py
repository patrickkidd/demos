from datetime import datetime, timezone


def make_story(id="test1234", topic="US-Iran Relations", active=True,
               last_sample=None, last_run_at=None):
    return {
        "id": id, "topic": topic,
        "seed_url": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_run_at": last_run_at,
        "last_sample": last_sample,
        "active": active,
    }


def make_phase1(outlet="Fox News", url="https://example.com/article",
                n_facts=3, n_opinions=2):
    facts = [
        {
            "id": f"FC-{i+1:03d}",
            "claim": f"Test factual claim {i+1}",
            "sourcing": ["named_primary", "institutional", "anonymous", "unsourced", "named_secondary"][i % 5],
            "source_detail": f"Source {i+1}" if i % 3 != 0 else None,
            "verifiable": i % 2 == 0,
            "context_provided": i % 3 == 0,
            "quote_excerpt": f"excerpt {i+1}",
        }
        for i in range(n_facts)
    ]
    opinions = [
        {
            "id": f"OP-{i+1:03d}",
            "statement": f"Test opinion {i+1}",
            "intensity": (i % 5) + 1,
            "sourcing_quality": round(0.2 * (i + 1), 1),
            "implied_worldview": f"worldview {i+1}",
            "speaker": "author" if i % 2 == 0 else "quoted_source",
            "quote_excerpt": f"opinion excerpt {i+1}",
        }
        for i in range(n_opinions)
    ]
    return {
        "article_title": f"Article from {outlet}",
        "article_date": "2026-04-07",
        "word_count": 800,
        "factual_claims": facts,
        "opinion_statements": opinions,
        "framing": {
            "headline_tone": -1,
            "headline_text": "Test Headline",
            "narrative_structure": "crisis and response",
            "loaded_language": [{"term": "slammed", "neutral_alternative": "criticized", "context": "in headline"}],
            "sources_quoted": [{"name_or_descriptor": "analyst", "role": "expert", "perspective_type": "neutral_expert", "approximate_word_count_given": 50}],
            "perspective_balance": "critic-heavy",
        },
        "emotional_appeals": [{"emotion": "fear", "excerpt": "grave threat", "technique": "threat framing"}],
        "internal_gaps": ["No response from accused party quoted"],
        "summary_metrics": {
            "fact_opinion_ratio": 0.6,
            "sourcing_quality_score": 0.7,
            "emotional_intensity_score": 0.3,
            "perspective_diversity_score": 0.5,
        },
        "_outlet": outlet,
        "_url": url,
    }


def make_phase2(outlets=None, n_facts=5, n_axes=3):
    if outlets is None:
        outlets = ["Fox News", "NYT", "Reuters", "Al Jazeera", "PBS"]
    facts = [
        {
            "id": f"F-{i+1:03d}",
            "claim": f"Canonical fact {i+1}",
            "outlets": [
                {"name": outlets[j % len(outlets)], "sourcing": "named_primary", "source_detail": f"src{j}"}
                for j in range(min(3, len(outlets)))
            ],
            "verifiable": True,
            "quote_excerpt": f"fact excerpt {i+1}",
        }
        for i in range(n_facts)
    ]
    axes = []
    for i in range(n_axes):
        ax_id = f"AX-{i+1:03d}"
        axes.append({
            "id": ax_id,
            "axis": f"Debatable question {i+1}?",
            "opinions": [
                {
                    "stance": f"Position A on axis {i+1}",
                    "pole": "A",
                    "outlets": [{"name": outlets[0], "intensity": 4, "sourcing_quality": 0.6}],
                    "implied_worldview": f"worldview A{i+1}",
                    "quote_excerpt": f"pole A excerpt {i+1}",
                },
                {
                    "stance": f"Position B on axis {i+1}",
                    "pole": "B",
                    "outlets": [{"name": outlets[1], "intensity": 3, "sourcing_quality": 0.5}],
                    "implied_worldview": f"worldview B{i+1}",
                    "quote_excerpt": f"pole B excerpt {i+1}",
                },
            ],
        })
    return {
        "topic": "US-Iran Relations",
        "sample_id": "20260407T120000",
        "aggregated_at": "2026-04-07T12:30:00Z",
        "outlets": outlets,
        "facts": facts,
        "opinion_axes": axes,
        "axis_order": [a["id"] for a in axes],
        "unmatched_opinions": [],
    }


def make_clusters(phase2=None):
    if phase2 is None:
        phase2 = make_phase2()
    fact_ids = [f["id"] for f in phase2["facts"]]
    axis_ids = [a["id"] for a in phase2["opinion_axes"]]
    return {
        "topic": phase2["topic"],
        "sample_id": phase2["sample_id"],
        "clustered_at": "2026-04-07T12:45:00Z",
        "developments": [
            {
                "id": "DEV-001",
                "label": "Military Operations Update",
                "summary": "Multiple outlets reported on the scale of strikes and casualties.",
                "fact_ids": fact_ids[:3],
                "axis_ids": axis_ids[:2],
                "outlet_count": 4,
            },
            {
                "id": "DEV-002",
                "label": "Diplomatic Response",
                "summary": "Ceasefire proposals and international reactions dominated diplomatic coverage.",
                "fact_ids": fact_ids[3:],
                "axis_ids": axis_ids[2:],
                "outlet_count": 3,
            },
        ],
        "unclustered_fact_ids": [],
        "unclustered_axis_ids": [],
    }


def make_synthesis(phase2=None):
    if phase2 is None:
        phase2 = make_phase2()
    centroids = [
        {
            "axis_id": ax["id"],
            "axis": ax["axis"],
            "pole_a_summary": ax["opinions"][0]["stance"][:40],
            "pole_b_summary": ax["opinions"][1]["stance"][:40] if len(ax["opinions"]) > 1 else "N/A",
            "centroid": f"Balanced conclusion for {ax['axis']} The evidence is mixed.",
            "confidence": ["high", "medium", "low"][i % 3],
            "confidence_reason": f"Reason for confidence level on axis {i+1}",
        }
        for i, ax in enumerate(phase2["opinion_axes"])
    ]
    return {
        "topic": phase2["topic"],
        "sample_id": phase2["sample_id"],
        "synthesized_at": "2026-04-07T13:00:00Z",
        "headline": "Test Headline for Sample",
        "bias_summary": "Test bias summary across outlets.",
        "axis_centroids": centroids,
        "centroid_article": (
            "First paragraph of the centroid article with established facts.\n\n"
            "Second paragraph with nuanced analysis of the situation.\n\n"
            "Third paragraph addressing genuine uncertainties and open questions.\n\n"
            "Fourth paragraph with concluding synthesis."
        ),
    }


def make_manifest(outlets=None, n_articles=6):
    if outlets is None:
        outlets = ["Fox News", "NYT", "Reuters", "Al Jazeera", "PBS", "BBC"]
    return {
        "topic": "US-Iran Relations",
        "collected_at": "2026-04-07T12:00:00Z",
        "articles": [
            {
                "url": f"https://example.com/{outlets[i % len(outlets)].lower().replace(' ', '-')}/article-{i}",
                "outlet": outlets[i % len(outlets)],
                "file": f"article-{i}.txt",
                "word_count": 500 + i * 100,
            }
            for i in range(n_articles)
        ],
    }
