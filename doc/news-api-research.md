# News API Research Findings

## Context

Fetching full article text from 28 outlets is unreliable via direct HTTP.
Paywalls and bot protection block many major outlets. The current hybrid
approach (httpx → agent WebFetch fallback) works but burns Claude tokens
on fallback fetches. Evaluated paid news APIs as an alternative.

## Findings

No service provides full article text at $20/mo. The cheapest viable
option is $84/mo.

| Service | Cheapest full-text tier | Requests | Sources |
|---|---|---|---|
| GNews | $84/mo | Basic tier | 60k+ |
| Perigon | $250/mo | 10k/mo | 80k |
| NewsData.io | $350/mo | 50k credits/mo | 87k+ |
| NewsCatcher | $449/mo | Enterprise | 70k+ |
| NewsAPI.org | N/A | No full text | 80k+ |

## Recommendation

**Stick with the hybrid approach for now.** On the 20x Claude Max plan,
the agent fallback for paywalled sites likely costs less than $84/mo in
effective quota usage. Monitor how many outlets consistently need fallback
— if it's 10+ per sample, GNews becomes worth it. If it's 3-4, the
current approach is cheaper.

**If we add a paid API later**, GNews is the best fit: cheapest full-text
tier, deep-learning article extractor, and the API is simple (search by
keyword + source, get full text back). Integration would replace the
httpx fetch step — the agent search step stays the same.

## Sources

- https://newsdata.io/blog/pricing-plan-in-newsdata-io/
- https://www.perigon.io/products/pricing
- https://www.newscatcherapi.com/pricing
- https://gnews.io/pricing
- https://newsdata.io/blog/news-api-comparison/
