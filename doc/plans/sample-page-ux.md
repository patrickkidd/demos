# Sample Page UX: Making Bias Visible

## Problem

The sample page's biggest value is showing people how biased their news
source is and what they're missing. But the current layout (development
cards with expand → tabbed opinions/facts) treats this as information to
browse. Nobody browses 30 facts and 12 opinion axes. The bias revelation
needs to be experiential — the user should *feel* the gap, not read about
it.

The current UX serves the 1% researcher. The 99% daily reader needs to
see 3-5 things that matter and immediately understand which outlets are
telling them half the story.

## Sub-problem: What is "the story"?

For polarizing topics with daily coverage (the primary use case), a
single day's sample may contain multiple sub-stories. The clustering
phase handles this. But within each development, there's still the
question of how to present facts vs opinions in a way that makes bias
self-evident.

## Ideas

### 1. Bubble simulator

Pick any outlet from a dropdown. The page re-renders showing ONLY what
that outlet covered — which facts, which opinions, which developments.
Everything they didn't cover fades to gray or disappears. Toggle back to
"all outlets" and the gaps become viscerally obvious.

**Strength**: Experiential. The user discovers the bias themselves.
**Weakness**: Requires the user to take an action (pick an outlet).
Passive readers might never click.

### 2. Fact → Opinion gradient

Single scrollable page. Facts at top (solid, confident, neutral colors),
sorted by consensus (most outlets reporting = most certain). Gradually
transitions to opinions at bottom (divergent colors, spectrum bars,
contested). The page itself is a visual gradient from "things we know"
to "things we argue about." No tabs, just scroll.

**Strength**: Teaches the fact/opinion distinction without explaining it.
Works for passive readers.
**Weakness**: Long page. Doesn't surface outlet-specific gaps.

### 3. Lead with gaps

For each outlet, show what they DIDN'T cover that others did. "Fox News
did not report: [3 facts that 8 other outlets reported]." The omission
list is the primary content, not the coverage.

**Strength**: Fastest path to the "oh shit" moment.
**Weakness**: Confrontational. May feel like the app is attacking specific
outlets rather than helping the user.

### 4. Combine: gradient + bubble toggle

Fact→Opinion gradient as the default passive view. Bubble simulator as a
toggle in the corner for users who want to explore specific outlets.
Best of both but more UI complexity.

## Open questions

- Should the default view be passive (gradient, everyone sees the same
  thing) or interactive (pick your outlet, see your blind spots)?
- How much should the UI editorialize about which outlets are "better"
  vs letting the data speak?
- The spectrum bars already show outlet positioning on opinions. Is the
  problem that they're buried inside expand toggles, or that the visual
  metaphor itself doesn't land?
- Would a "coverage score" per outlet (X% of consensus facts reported)
  be useful as a summary stat, or is it reductive?
