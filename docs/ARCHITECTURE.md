# SONAR A0 architecture

## Decision: Python command-line investigation, not an application

The GitHub repository was empty when A0 began. Python 3.11+ is suitable for local
Windows execution, exact decimal arithmetic, deterministic standard-library
tests and HTTP probes. BeautifulSoup is the single direct runtime dependency:
it parses real public DOM and structured data without browser automation.
`requirements.lock` pins the tested direct and transitive runtime versions.
The standard library provides HTTP, JSON, decimals, timestamps, the CLI and tests.

No FastAPI, frontend, BoM processing, cloud/database, scheduler, purchasing or
alternative selection is implemented. Those belong to later approved phases.

## Components

```text
CLI search/product/health/verify
              |
      SupplierAdapter contract
         /              \
  OzdisanAdapter    DirencAdapter
         \              /
       HttpClient -> robots policy -> paced public HTTPS -> request evidence
         |
   Document -> pure parse_product -> Offer / PriceBreak / Result
```

`SupplierAdapter.search(query, limit)` discovers product links and returns
normalized offers. `product(url, mpn=...)` retrieves a supplied URL independently;
it cannot establish the feasibility of product discovery. `parse_product` is a
pure function of a supplied document and optional query, enabling deterministic
tests. `health()` checks robot-policy accessibility only.

The adapter owns its URL patterns, allowed host set, DOM selectors and schema
paths. Shared normalization only handles values and MPN comparisons. Future
E-Komponent, Robotistan, Arkotek, Mouser or DigiKey adapters implement the same
contract and explicitly choose their permitted access method. Nothing assumes
they expose the same pages or permit the same requests. They are not implemented
or investigated in this A0.

## Evidence and uncertainty

`Result` records the supplier, operation, query, retrieval status, offers,
diagnostic message and request evidence. Every actual HTTP response has a UTC
receipt timestamp, HTTP status, body size and SHA-256 hash. A robots refusal has
`attempted:false` and `checked_at`, not a fabricated HTTP response or retrieval
time. Redirects and robot requests are separately recorded. Full response bodies
are temporary investigation material outside the committed repository.

`Offer` preserves supplier attribution, canonical observed response URL, receipt
time, explicit MPN and/or inferred title token, supplier SKU/brand, case,
packaging, availability, quantities, pricing tiers, field sources and warnings.
One offer can carry multiple currency/package price lists; callers must not mix
them. Current Direnc.net schema SKU can differ from the displayed stock code;
A0 keeps the explicitly labeled schema SKU and notes this limit in the report.

`PriceBreak` records minimum/maximum quantity, exact Decimal amount, currency,
VAT basis, per-tier packaging and source. No converted currency, VAT rate,
delivery total or shipping guarantee is inferred. DOM quantity input min/step
describes publicly observable UI limits, not a negotiated supplier contract.

Operation states are independent of stock states. For example, `not_found` is an
explicit empty search or HTTP 404; `blocked`, `robots_disallowed`, `timeout`,
`rate_limited` and `parse_error` never become `out_of_stock`. `partial` indicates
usable fields with missing/ambiguous procurement information.

The exact-match label means only full MPN string equality against an explicitly
provided field. It does not prove identical manufacturer, electrical properties,
shipping packaging, source authenticity or purchasing conditions. Title tokens
are inferred and never receive `exact_mpn`. A0 performs no part replacement.

## Supplier decisions

**Özdisan:** The current public search template is `/c?search=...`. Its robots
policy disallows `/*search=`, `/api/` and `/_next/`. The adapter checks that policy
and refuses search without issuing a prohibited request. It reads JSON-LD and
anonymous `__NEXT_DATA__` already embedded in permitted product HTML; it does not
request Next.js internals or API routes. If the policy changes, it reports that
discovery remains unvalidated rather than silently claiming search support.

**Direnc.net:** The observed public form uses `/arama?q=...`. The search adapter
reads server-rendered product card links, deduplicates URLs, fetches up to the
requested limit and records each request. It does not request the disallowed
`/srv/` autocomplete/service routes. Product JSON-LD supplies availability and
supplier identifiers. Visible prices, tax labels, quantity tables and input
constraints add fields with explicit source descriptions. No pagination is
implemented; only the observed page and selected first results are investigated.

## Transport restrictions

The HTTP client identifies itself as SONAR-A0, supports no login/cookies, and
allows HTTPS only to the chosen supplier's approved hosts. Robots wildcard and
end-anchor matching uses longest matching rule, with Allow winning ties; selected
user-agent groups are merged. Crawl-delay is honored as an additional conservative
rule. Policy fetch failure fails closed; a genuine robots 404/410 permits access.
Every redirect target is checked before sending a request. Responses are limited
to 5 MB. Unexpected content types, decoding failures and recognized challenge
pages do not reach successful normalization.

Request starts are at least two seconds apart per host within one sequential
client. There is no parallel crawling or automatic retry. HTTP 429 reports
Retry-After and ends that supplier's remaining suite cases. Do not run concurrent
CLI processes against a supplier; pacing is process-local. This small robots
implementation is tested for the current policies, not advertised as a complete
RFC 9309 implementation (e.g. advanced percent-encoding normalization is outside
A0). New supplier policies require review and corresponding tests.

## Validation and reproducibility

Deterministic tests use minimal synthetic fixtures for normal, missing,
contradictory and changed shapes. Network tests inject failures and verify that
disallowed/redirected requests never happen. No test calls the suppliers.

Live runs use `examples/a0_cases.json` and a new output JSON. Evidence execution
success is explicitly separate from supplier integration success. Sample scope,
first-result limits, manually supplied product URLs and historical timestamps
remain visible. Tests do not justify a universal catalog accuracy claim.

There is no persistent cache. `is_stale` is a reusable freshness check with
timezone-required timestamps; it is tested and ready for later consumers. Stored
evidence is labeled historical and must never be republished as current data.

## Alternatives deferred

- Browser automation: public pages already expose useful data; it would not
  resolve policy restrictions or create missing manufacturer/packaging facts.
- Supplier APIs: appropriate if documented and permitted; none were validated
  as a freely usable public integration in A0. Private disallowed routes are not
  explored.
- Hosted service/database: unnecessary for a local feasibility probe and would
  introduce costs/deployment scope prematurely.
- Broad scraping/sitemap indexing: not used to route around the restricted
  search flow; separate permission and scope would be needed.
