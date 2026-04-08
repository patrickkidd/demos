"""Tests for data model functions and fixture integrity."""
import json
import pytest
from tests.fixtures.factories import make_phase2, make_phase3


def test_phase2_axis_order_coverage():
    p2 = make_phase2(n_axes=5)
    ax_ids = {a["id"] for a in p2["opinion_axes"]}
    order_ids = set(p2["axis_order"])
    assert ax_ids == order_ids


def test_phase2_outlet_consistency():
    outlets = ["A", "B", "C"]
    p2 = make_phase2(outlets=outlets)
    for fact in p2["facts"]:
        for o in fact["outlets"]:
            assert o["name"] in outlets
    for ax in p2["opinion_axes"]:
        for op in ax["opinions"]:
            for o in op["outlets"]:
                assert o["name"] in outlets


def test_phase3_axis_centroid_coverage():
    p2 = make_phase2(n_axes=4)
    p3 = make_phase3(p2)
    p2_ids = {a["id"] for a in p2["opinion_axes"]}
    p3_ids = {c["axis_id"] for c in p3["axis_centroids"]}
    assert p2_ids == p3_ids


def test_centroid_article_multiline():
    p3 = make_phase3()
    paragraphs = [p for p in p3["centroid_article"].split("\n\n") if p.strip()]
    assert len(paragraphs) >= 2


def test_load_sample_complete(populated_instance):
    from app.main import _load_sample
    import app.main as main_mod
    orig = main_mod.DATA
    main_mod.DATA = populated_instance
    try:
        s = _load_sample("s1", "20260407T120000")
        assert s["id"] == "20260407T120000"
        assert s["article_count"] == 6
        assert "phase2" in s
        assert "phase3" in s
    finally:
        main_mod.DATA = orig


def test_load_sample_partial(populated_instance):
    from app.main import _load_sample
    import app.main as main_mod
    orig = main_mod.DATA
    main_mod.DATA = populated_instance
    try:
        s = _load_sample("s1", "20260408T060000")
        assert s["article_count"] == 3
        assert "phase2" not in s
        assert "phase3" not in s
    finally:
        main_mod.DATA = orig


def test_story_samples_sorted(populated_instance):
    from app.main import _story_samples
    import app.main as main_mod
    orig = main_mod.DATA
    main_mod.DATA = populated_instance
    try:
        samples = _story_samples("s1")
        assert samples == ["20260407T120000", "20260408T060000"]
    finally:
        main_mod.DATA = orig


def test_story_samples_empty(populated_instance):
    from app.main import _story_samples
    import app.main as main_mod
    orig = main_mod.DATA
    main_mod.DATA = populated_instance
    try:
        assert _story_samples("s2") == []
    finally:
        main_mod.DATA = orig
