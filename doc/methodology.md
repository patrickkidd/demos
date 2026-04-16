# News Reader — Methodology

## Why This Exists

Journalism's founding promise was to separate fact from opinion and present
facts free of interpretation, allowing readers to form their own conclusions.
That promise has eroded. Most outlets now blend reporting with framing,
editorial judgment, and emotional appeal in ways that are difficult for readers
to detect — especially when they consume only one or two sources.

Demos does not attempt to fix journalism. It accepts the current landscape and
applies a different strategy: **sample widely across biased sources, separate
fact from opinion mechanically, and triangulate toward objectivity through
collective intelligence.**

## Theoretical Foundations

### Collective Intelligence & the Centroid

The core claim: an average of diverse opinions is more objectively accurate (or
at least more *adaptive*) than any single opinion, no matter how expert. This
is supported by research on collective intelligence — from Galton's
ox-weighing experiment to modern prediction markets and the Wisdom of Crowds
literature (Surowiecki, 2004).

In Demos, the "centroid" is this average. It is not a simple mean of text — it
is a natural language synthesis that represents the balanced conclusion derived
from opposing opinion poles, weighted by evidence strength. The centroid article
is the product: what a perfectly informed, unbiased reporter would write given
all available facts and the full spectrum of interpretation.

### Bowen's Family Systems Theory

Murray Bowen's research on family systems and triangulation provides a
structural lens. Bowen observed that polarized positions in a system emerge *in
reaction to each other* — they are co-created. The extreme positions on any
issue are not independent data points; they are paired responses.

This implies that the truth is literally somewhere between the poles — not as
false balance, but as a structural consequence of how polarization works. When
two outlets take opposing stances on the same issue, the centroid between them
(weighted by evidence) is a better approximation of reality than either pole.

### Haidt & Peterson: Moral Foundations of Political Bias

Jonathan Haidt's Moral Foundations Theory and Jordan Peterson's work on
personality traits underlying political affiliation explain *why* outlets
cluster the way they do. Different moral foundations (care/harm, fairness,
loyalty, authority, purity) weight differently across the political spectrum,
producing predictable framing patterns.

Demos does not use this to pre-label outlets. Instead, it provides a framework
for understanding *why* opinion axes form the poles they do. If emergent
clusters correlate with known moral foundation profiles, that's validation of
the model — not an input to it.

## The Pipeline

### Sampling

Each "sample" is a single day's collection of articles on a tracked topic. The
goal is outlet diversity across the political spectrum. AllSides bias ratings
are used during collection to ensure adequate representation — not as
analytical input. A good sample includes left-leaning, right-leaning, centrist,
and wire service sources.

### Phase 1: Per-Article Extraction (Blind)

Each article is analyzed independently with the outlet's identity hidden from
the model. This prevents the model from applying preconceived notions about an
outlet's bias.

Extraction produces:
- **Factual claims**: each with a 5-tier sourcing taxonomy (named primary
  source through unsourced assertion), verifiability assessment, and quote
  excerpts
- **Opinion statements**: each with content, intensity (1-5), implied
  worldview, sourcing quality, and speaker attribution
- **Framing metadata**: headline tone, loaded language with neutral
  alternatives, narrative structure, emotional appeals, and internal gaps

The key distinction: facts are statements presented as true with verifiable
sourcing. Opinions are interpretive, judgmental, or predictive statements. The
boundary is not always clean, but the model errs toward classifying ambiguous
statements as opinion.

### Phase 2: Deduplication & Axis Mapping

Outlet identities are reintroduced. All Phase 1 extractions are merged:

- **Fact deduplication**: semantically identical claims across articles collapse
  into canonical facts, each tagged with every outlet that reported it and
  their sourcing levels
- **Opinion deduplication**: semantically identical opinions merge with outlet
  tags, preserving per-outlet intensity and sourcing quality
- **Opinion axis identification**: deduplicated opinions are grouped into
  "issue axes" — each axis represents one debatable question with two poles.
  Opposing opinions sit on opposite poles of the same axis
- **Axis ordering**: axes are arranged by topical relatedness into a 1D
  ordering, which maps around 360 degrees for visualization. Related axes
  cluster together; unrelated axes are distant

### Phase 3: Clustering

Deduplicated facts and opinion axes are grouped into 3-5 **key developments**
— distinct narrative threads within the day's coverage. Each development
has a label, summary, and references to which facts and opinions belong to
it, ordered by coverage breadth (most outlets = lead story). This gives
readers a 1-minute overview before diving into detail.

### Phase 4: Centroid Synthesis

- **Per-axis centroid**: for each opinion axis, a natural language balanced
  conclusion weighted by evidence strength. Not false balance — if one pole has
  substantially stronger sourcing, the centroid shifts toward it
- **Meta-centroid article**: a synthesized narrative combining all deduplicated
  facts with all per-axis centroids. This is the final product — the
  reconstructed "objective" article

### Centroid Weighting

The centroid position on each axis is influenced by opinion intensity and may
in the future incorporate sourcing quality. The raw data preserves both
dimensions per opinion, allowing the weighting formula to evolve without
re-running extraction. The current approach uses intensity alone; the
relationship between sourcing quality and centroid positioning is an open
research question within this project.

## The Visualization

Each sample is represented as a dot on a timeline for its topic. Clicking a
dot reveals two complementary views of the same data:

### Circular Overview

- **Center**: deduplicated facts
- **Radiating outward**: opinion axes, arranged by topical relatedness around
  360 degrees
- **Each axis**: two poles on opposite sides of center, with opinions placed at
  a distance proportional to their intensity
- **Colors**: orange (Pole A / "For") and teal (Pole B / "Against"). These
  colors are deliberately non-political — Pole A and B have no stable mapping
  to left/right across axes. Orange and teal were chosen to avoid evoking US
  party colors.

### Opinion Spectrum (Vertical List)

Below the circle, each opinion axis is rendered as a card showing:
- The debatable question as a title
- "For" and "Against" sections with each pole's stance and a horizontal bar
  positioning outlets by their opinion intensity
- Single-pole axes (where no outlet covered the opposing view) show a ✕ on
  the empty side — omissions are flagged visually, not buried in text
- A collapsible "Show centroid" section with the balanced conclusion and a
  certainty rating (high/medium/low) indicating confidence in the centroid
  position

Cards are sorted by **bias severity** — axes where outlets express high-
intensity opinions with low sourcing quality appear first. This surfaces the
most egregious instances of opinion presented as fact.

Bias severity formula: `avg_intensity × (1 - avg_sourcing_quality)` across
all opinions on the axis.

### Government Sources

Article collection explicitly includes official government sources (White
House press releases, State Department briefings) alongside news outlets.
These are analyzed blindly like any other article but ensure that
administration framing — which often drives polarization — is represented
in the sample.

## Known Limitations

- The LLM performing extraction is itself a biased instrument. Its training
  data and RLHF tuning embed assumptions about what constitutes fact vs.
  opinion. Blind extraction mitigates but does not eliminate this.
- Fact deduplication requires semantic judgment. Two outlets may report the
  "same" fact with meaningfully different framing that gets lost in
  deduplication.
- Opinion intensity scoring is subjective. The 1-5 scale is calibrated by
  prompt instruction, not by ground truth data.
- The centroid is only as good as the sample. If the source selection is
  skewed (e.g., 5 left-leaning outlets and 1 right-leaning), the centroid
  shifts accordingly. AllSides-guided sampling mitigates this but depends on
  AllSides ratings being accurate.
- Axis ordering by topical relatedness is approximate. The 1D projection of a
  high-dimensional relatedness space necessarily loses information.
- This system cannot detect facts that *no* outlet reported. Its omission
  detection is relative to the sample, not to ground truth.

## Source Code

The complete source code for Demos is available at
[github.com/patrickkidd/demos](https://github.com/patrickkidd/demos).

## Relationship to AllSides

AllSides media bias ratings are used exclusively to guide source diversity
during article collection. They are not used as analytical input — no
extraction, deduplication, axis mapping, or centroid calculation references
AllSides scores.

AllSides data is retained for potential future meta-analysis: comparing
LLM-derived framing patterns against AllSides classifications could validate
(or challenge) both approaches.
