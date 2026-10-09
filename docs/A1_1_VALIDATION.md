# SONAR A1.1 frontend redesign — validation

Validated 9 October 2026 on Windows, Python 3.12 and real Chrome (Playwright engine 1.64.0-alpha-1790635538000). Branch `design/sonar-ui` starts at `63965b25146fe4fe19da1373c825923de313aed0`. No merge, deployment, purchasing or paid service was performed.

## Implementation and references

Primary references were the supplied **SONAR Design System.html** (1,878,446 bytes; SHA256 `8c0841a43034556fed51e78a5cb388d86189d0529f86a8034cdf0520b551f577`) and **SONAR-frontend-review-and-handoff.md** from the earlier review. Inspected their unpacked Identity, Components, Projects, BoM, Suppliers, Purchase list, Mobile and Handoff boards. Rendered the original bundle locally and captured its Projects and BoM boards for visual comparison.

Ported the warm paper/night palettes, IBM Plex Sans/Mono, source-point/echo logo, pill buttons and tags, rounded fields/cards, step header and expandable rows into the existing vanilla frontend. All four screens use the same design tokens. Embedded licensed font files are self-hosted and included in the wheel. No React, dc-runtime, CDN, inline handlers, new production dependency or weakened CSP is required.

The Projects screen is deliberately named **Session BoMs** and displays only current session data. Prototype project history, fake statistics, XML import, client-side money arithmetic and the incorrect null-stock availability inference are excluded. Import preview, mappings, worksheets, source inspection, warnings, supplier selection and CSV downloads remain connected to A1. The BoM has real filters, native expandable rows, selection and confirmed bulk DNP actions. Mobile has functional bottom navigation with safe-area spacing, 48px controls and locally scrollable procurement tables retaining every field.

Backend/API files are unchanged. Quantities, MOQ/multiples, tiers, prices, totals, currencies, VAT, revisions and CSV protection remain server-authoritative. Uncertain supplier matches require explicit acknowledgment; unknown stock remains unknown. Existing cookie, CSRF, origin/host, URL/DNS restrictions and CSP protections remain covered by the original suite. The frontend now identifies expiry, displays Retry-After, reports stale supplier results, prevents obsolete procurement responses from appending, and restores keyboard focus after navigation, row/dialog actions and rerenders.

## Results actually executed

| Check | Result |
|---|---|
| Original baseline suite | 97 passed |
| Final full suite, including four new independent design checks | **101 passed** |
| Deterministic real-Chrome regression flow | **105 checks passed**, zero JavaScript errors |
| axe-core 4.10.3 WCAG A/AA scans | **24 scans**, no detected violations, including import dialogs and populated supplier/procurement screens |
| Small text/status/control token contrast | Both themes passed 4.5:1 text and 3:1 essential boundary requirements |
| Responsive layouts | All four screens at 1440, 1024, 760, 390 and 320 px, both themes; no page-wide horizontal overflow |
| Keyboard | Enter disclosure, Space selection, Escape row/dialog close, opener focus restoration, skip link and navigation current-page state passed |
| Motion | Reduced-motion removes transitions |
| Export | Actual procurement download inspected: server Decimal cost, unassigned/unknown lines, preserved source fields and DNP exclusion |
| Syntax/whitespace | `node --check` and `git diff --check` passed |
| Packaging | Final wheel built and installed in a clean venv with locked runtime; all nine static assets (including four WOFF2 files and license) present; `pip check` passed |

The browser regression covers empty boot; CSV manual mapping, XLSX and TSV imports; board count; row editing; warnings/search/filtering; three-state population from imports; selection; bulk DNP; uncertain acknowledgment rejection/focus; explicit tier choice; known TRY and USD totals with distinct VAT bases; unpriced lines; clear choice; partial, network-failure, rate-limit and empty retrieval; permitted known-URL retrieval; disabled Özdisan automatic discovery; reload during an active supplier job; theme persistence; long MPN/HTML text safety; mobile navigation; HTTP 429 Retry-After and explicit HTTP 401 recovery. Supplier retrieval uses the separate synthetic fixture server. HTTP 401/429 presentation tests use controlled browser responses; real expiry/rate-limit enforcement remains covered by the backend suite.

Evidence: [browser check list](evidence/browser-validation.json), [viewport axe audits](evidence/accessibility-audits.json). Eight additional dialog/populated-content scans are recorded as passed checks in the browser list.

## Visual comparison

Before/after captures use the committed example BoM with 25 boards. Source prototype images contain its own fixed sample data; implementation images contain imported test/example data, never preloaded statistics. Compared header proportions, warm surfaces, fonts, radius, row height, field/pill treatment and mobile behavior. Refined MPN wrapping, status-pill stretching, focus outlines and chevrons after reviewing screenshots. Extra A1 validation, acknowledgment and source controls remain available even where the prototype omits them.

| Reference or screen | Capture |
|---|---|
| Claude Projects board | [Reference](screenshots/a1.1/reference-projects.png) |
| Claude BoM board | [Reference](screenshots/a1.1/reference-bom.png) |
| Original desktop BoM | [Before](screenshots/a1.1/before-bom-desktop.png) |
| Redesigned desktop BoM | [After](screenshots/a1.1/after-bom-desktop.png) |
| Original mobile BoM | [Before](screenshots/a1.1/before-bom-mobile.png) |
| Redesigned mobile, both themes | [Light](screenshots/a1.1/after-bom-mobile.png), [dark](screenshots/a1.1/after-bom-mobile-dark.png) |
| Populated supplier review | [Desktop](screenshots/a1.1/suppliers-light.png), [mobile dark](screenshots/a1.1/offer-dark-mobile.png) |
| Procurement | [Desktop](screenshots/a1.1/purchase-light.png), [mobile dark](screenshots/a1.1/purchase-dark-mobile.png) |

Further viewport/theme captures are in `docs/screenshots/a1.1`. Mobile captures include both viewport screenshots and full-page stress cases; fixed navigation appearing partway through a full-page image is a screenshot artifact of its viewport anchoring.

## Reproduce

Install the existing locked runtime/test requirements, then run:

```powershell
$env:PYTHONPATH = (Join-Path $PWD 'src')
python -m unittest discover -s tests -v
node --check src/sonar_web/static/app.js
python tools/browser_fixture_server.py
```

In another shell from the repository root, install optional **development-only** browser tools outside the repository or in ignored `output/browser-tools`, and run:

```powershell
npm install --prefix output/browser-tools playwright@1.64.0-alpha-1790635538000 axe-core@4.10.3
$env:NODE_PATH = (Join-Path $PWD 'output/browser-tools/node_modules')
node tools/browser_regression.cjs
```

The regression uses installed Chrome (`channel: chrome`) and local fixture port 8013. Default evidence output is `output/playwright`; `SONAR_E2E_OUTPUT` overrides it. Screenshot regeneration writes `docs/screenshots/a1.1`. The fixture server is not imported by the production entry point.

## Remaining limitations

- Supplier observations here are deterministic synthetic fixtures, not a claim of current prices, stock, manufacturer identity or live supplier availability. A0 supplier restrictions remain.
- Automated accessibility and exercised keyboard behavior are verified; a manual screen-reader audit and native browser 200% zoom were not performed. The 200% equivalent viewport reflow was exercised. This is not a blanket WCAG certification.
- Docker/Linux/laboratory runtime and production deployment were not tested or performed. Existing temporary, single-process server sessions remain; no persistent project history or accounts were added.
- The original Starlette/HTTPX deprecation warning remains. It does not fail the 101 tests.
- Bulk DNP uses existing per-component mutations, stops at the first failure and reports the number updated; it is not a new transactional backend endpoint. A1 allows preserving unknown population or resolving it to Populate/DNP, not changing an established state back to null.
