# SONAR A1 architecture

A1 adds `src/sonar_web` beside the preserved `src/sonar_a0` package. All 41 original
A0 tests and its investigation documents remain unchanged. The remote README
commit `7fe3a3e` is preserved as the parent history of this work.

## Technology decision

Python 3.11+ / FastAPI / Uvicorn reuse the existing A0 Python adapters directly.
The frontend is browser-native HTML, CSS and JavaScript, served from the same
origin. This keeps the runtime small: no Node build, mandatory database, cloud
service, paid API or cross-origin deployment is needed. Openpyxl with defusedxml
handles bounded XLSX reads; Python's CSV module handles delimited files.

```text
Browser UI (Dashboard / Workspace / Suppliers / Procurement)
       │ same-origin HTTP, HttpOnly session cookie, CSRF header
FastAPI endpoints ── temporary session store ── BoM validation / Decimal costs
       │                             └─ CSV / source-field exports
One sequential supplier worker
       │
A1 supplier facade ── A0 Özdisan / Direnc adapters
       │
A0 HTTPS allowlist / robots / pacing / redirects / timeouts / evidence
```

## Ownership and lifetime

Sessions use 256-bit random tokens in HttpOnly, SameSite=Strict cookies. A separate
CSRF token is returned to that session's frontend and required on all mutations.
No BoMs or supplier results are stored in localStorage; only the theme preference
is stored there. Session content is never served from static paths or written to
disk. Original cell values, unknown columns, duplicate column names (numbered),
report preambles and formula text remain inspectable/exportable. Entirely blank
physical rows are omitted; nonblank malformed components remain visible.

Default bounds: 8 MB incoming file, 30 MB expanded XLSX ZIP, 1000 ZIP entries,
5000 component rows, 100 columns, 2000 characters per cell, 10 BoMs and 2 previews
per session, 100 active sessions, two-hour inactivity expiry. JSON mutations are
limited to 256 KB and uploads must arrive within 30 seconds. API models reject
unknown keys and invalid input types. Large/resource-heavy files fail explicitly.
IT should tune capacity and upstream limits for verified server resources.

The application uses **one process / one worker / one replica**. Per-session locks
protect changes; a bounded supplier executor keeps UI/API work responsive. Expired
sessions are purged on subsequent session access. Jobs retained by a session are
bounded; active tasks may finish after session expiry but cannot expose that
expired workspace to another session. No disk persistence is claimed.

## Imports and component state

Headers are recognized from aliases after up to 50 preamble rows. All mappings are
reviewed before import, and unusual export templates support manual mapping.
XLSX worksheet choice is explicit. UTF-8 / UTF-8 BOM and CP1254 delimited exports
are supported; UTF-16, legacy XLS, encrypted and macro workbooks are rejected.
Formula cells are preserved as text and never executed; a formula quantity must
be corrected by the user. Macros and external links are not executed.

MPNs normalize outer whitespace and case only; suffixes, hyphens and slashes stay
significant. Common reference separators and bounded same-prefix ranges are
supported. Missing quantity is inferred from references only if the quantity
column is unmapped. Invalid quantities stay invalid. DNP accepts explicit common
boolean/population terms; Fitted/Populate columns invert that meaning. Unknown DNP
is not silently included in required quantities. Duplicate references and possible
identical rows are flagged, never merged by MPN or silently discarded.

Editing component data increments a revision and clears results/choice. Asynchronous
jobs capture revision and MPN; stale results are discarded. Selection checkboxes
control procurement scope independently. DNP components are excluded. PCB quantity
changes preserve observed offers and recalculate requirements and known costs.

## Supplier jobs

Only `ozdisan` and `direnc` are registered. The A1 facade calls the actual A0
contract, checks fixed supplier domains and non-public DNS answers, refreshes
robots policy per job, and preserves transport request-start clocks. A0 checks
every redirect against its host and robots restrictions and bounds every response.
The OS DNS resolver is trusted for the fixed supplier domains; IT may additionally
restrict outbound egress. There is no user-controlled generic HTTP fetch endpoint.

Automatic queries require MPNs. Manual product URL retrieval supports components
without MPNs, visibly retaining uncertain matching. Özdisan automatic discovery is
disabled in the frontend under the A0 finding; its API still uses A0's policy-aware
search refusal. Direnc searches read up to three candidates. Both integrations
remain partial. Unknown numeric stock stays null, independently of stock status.

One queued job covers at most 10 rows. Session quota is 10 component retrievals per
minute; direct-client IP quota is 20 per minute. Queue capacity is 20 jobs. Requests
are serialized across sessions with A0's minimum two-second host pacing and
longer advertised crawl delays. No retries or CAPTCHA bypass. Blocked/rate-limited/
network/robots-unavailable responses stop remaining rows; completion records report
how many ran. One job completion does not imply supplier success. Reverse-proxy
traffic shares its immediate-client quota because forwarded headers are not trusted.

## Procurement calculation

A user selects one observed offer and one reported price tier. Non-exact matches
require explicit acknowledgment; they remain unverified in review and exports.
Order quantity is rounded up from the maximum of required count, reported MOQ and
chosen tier minimum to a reported order multiple. Unknown MOQ/multiple is not
asserted as a supplier fact; the calculation uses 1 where a constraint is absent
and the original missing fields/warnings stay visible. If quantity exceeds a
tier's maximum, cost is unknown until the user chooses a suitable tier.

Known cost = exact Decimal unit price × order quantity. Totals remain separate by
supplier / currency / VAT basis; missing lines are counted. No VAT rate, exchange
rate, shipping, stock reservation, substitution verification or checkout is
inferred. A chosen price does not establish sufficient stock or exact identity.

CSV exports include source fields as JSON, references, quantities, match status,
price/currency/VAT, warnings and retrieval timestamp. Unassigned selected components
are included with unknown costs. DNP/unselected rows are excluded from the purchasing
list and retained in original source export. Formula-leading values are apostrophe
escaped for spreadsheet consumers; source CSV is a safe reconstruction, not a
byte-identical original workbook or a project-save format.

## API contract

`GET /openapi.json` describes request schemas. Interactive docs are disabled. Error
responses use `detail`; supplier retrieval statuses remain the original A0 statuses.

| Endpoint | Purpose |
|---|---|
| `GET /healthz` | Process health, version and storage mode; no supplier call |
| `GET /api/session` | Create/resume session; BoMs, CSRF token and upload limit |
| `POST /api/import/preview?sheet=...` | Raw file bytes with URL-encoded `X-Filename`; return sample/column mapping |
| `POST /api/boms` | Import stored preview with name and column-index mapping |
| `PATCH /api/boms/{id}` | Set integer PCB production quantity |
| `DELETE /api/boms/{id}` | Remove a session BoM |
| `PATCH /api/boms/{id}/components/{cid}` | Edit fields, DNP or selection |
| `POST /api/boms/{id}/selection` | Set selection for a bounded component-ID list |
| `POST /api/supplier-jobs` | Queue retrieval for component IDs, supplier and optional product URL |
| `GET /api/supplier-jobs/{id}` | Poll session-owned progress and statuses |
| `PUT /api/boms/{id}/components/{cid}/choice` | Choose observed offer/tier with uncertainty acknowledgment |
| `DELETE /api/boms/{id}/components/{cid}/choice` | Clear preferred product |
| `GET /api/procurement` | Session procurement lines and separated known-cost totals |
| `GET /api/procurement.csv` | Download procurement CSV |
| `GET /api/boms/{id}/source.csv` | Download all preserved original fields and preamble |

All API content is `Cache-Control: no-store`. Host validation, allowed mutation
origins, CSRF checks, request limits, CSP, safe DOM text rendering, no CORS access
and CSV formula escaping provide baseline protection. Logs include event type and
row counts, not BoM content, cookies, tokens or supplied URL parameters. A1 is a
trusted laboratory workspace; IT must restrict access at its network/proxy boundary
before deployment. Public deployment and complex user authentication are out of scope.
