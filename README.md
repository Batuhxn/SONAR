# SONAR — A1 Engineering Procurement Workspace

SONAR is a self-hosted web application for reviewing electronics BoMs and
preparing procurement lists from Turkish suppliers. It runs locally on Windows
and includes a Docker Compose configuration for later laboratory deployment.
No paid services, cloud infrastructure, API keys or automatic purchasing.

## Start A1 on Windows 11

Python 3.11+ is required (validated with Python 3.12.10). From PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m sonar_web
```

Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)**. Stop with Ctrl+C.
The `sonar` console command starts the same application. The package name remains
`sonar-a0` for compatibility; the existing `sonar-a0` CLI remains available.
Node.js is **not** required to run SONAR; frontend assets are shipped locally.

1. Import an Altium CSV/XLSX or KiCad CSV/TSV in **BoM Workspace**.
2. Review detected columns; choose a worksheet or manual mappings as needed.
3. Edit rows, resolve warnings, select populated components and set PCB quantity.
4. Use **Supplier Explorer** to search Direnc.net or retrieve known product URLs
   from either supplier. Özdisan automatic discovery remains restricted.
5. Compare source fields and price tiers. Acknowledge uncertain product matches
   before selection. Review quantities and missing information in **Procurement**.
6. Export procurement CSV. Original source fields are also exportable per BoM.

Try the representative **synthetic** engineering exports in
[`examples/altium_a1.csv`](examples/altium_a1.csv),
[`examples/altium_a1.xlsx`](examples/altium_a1.xlsx) and
[`examples/kicad_a1.tsv`](examples/kicad_a1.tsv). They are test designs, not actual
laboratory purchasing requirements. No demo statistics are preloaded in the app.

**Session storage:** BoMs are private to the browser's session and held only in
server memory. Default inactivity expiry is two hours; server restarts clear all
sessions. Export work before leaving. A1 has no shared project database or user
accounts. Use a trusted local or IT-restricted laboratory network.

**Costs:** Known item costs use Decimal arithmetic and remain grouped by supplier,
currency and VAT basis. Unknown costs remain empty in exports; no currency
conversion, inferred VAT, shipping charges or purchasing guarantee is included.
Reported MOQ, order multiples and chosen tier minimums can increase order quantity.
Changing component data invalidates previous results and selections; changing PCB
quantity recalculates the chosen product's costs without a new supplier request.

## A1 documentation and validation

- [Architecture and API](docs/A1_ARCHITECTURE.md)
- [Deployment guide for laboratory IT](docs/A1_DEPLOYMENT.md)
- [Validation record and limitations](docs/A1_VALIDATION.md)
- [A0 feasibility report, preserved](docs/A0_FEASIBILITY_REPORT.md)

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

## A0 implementation and original operating guide

The following A0 documentation describes the preserved supplier investigation.
Its scope statements apply to A0, not the new A1 web package.

Local proof of concept for reading genuine public procurement information from
**Özdisan** and **Direnc.net**. This repository implements A0 only: no BoM importer,
UI, database, substitution engine, shopping cart, purchasing or hosted service.

**Current finding: both suppliers are PARTIAL.** Özdisan product-page retrieval
works, but its robots policy disallows the documented MPN search route. Direnc.net
search and product prices/availability work, but explicit manufacturer MPNs,
stock counts and shipping packaging are often missing. See
[the evidence-backed feasibility report](docs/A0_FEASIBILITY_REPORT.md).

## Install on Windows 11

Prerequisites: Python 3.11+ and internet access. Tested on Windows 11 Pro 64-bit
(10.0.26200), Python 3.12.10. No API keys, accounts, paid APIs, proxy services,
hosting, browser driver or database are required.

From the repository directory in PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
```

Use `py -3.11` or `python` for another supported Python installation.
Activation of the virtual environment is optional. On Linux/macOS the equivalent
interpreter is `.venv/bin/python`; these platforms were not validated in A0.

## Execute real requests

```powershell
# Discover product URLs from an actual supplier search, then read their pages.
.\.venv\Scripts\python.exe -m sonar_a0 search direnc LM358P --limit 2

# This should report robots_disallowed with attempted:false for the search URL.
.\.venv\Scripts\python.exe -m sonar_a0 search ozdisan LM358P

# Known public URL retrieval is different from automated product discovery.
.\.venv\Scripts\python.exe -m sonar_a0 product ozdisan "https://www.ozdisan.com/p/amplifikatorler-242/texas-lm358p-13549" --mpn LM358P

# Live active/passive/parametric/negative cases; creates a new evidence file.
.\.venv\Scripts\python.exe -m sonar_a0 verify --cases examples/a0_cases.json --output live-output/my-run.json

# Check robots accessibility only; this does not establish search/product health
.\.venv\Scripts\python.exe -m sonar_a0 health direnc
```

Individual commands: exit `0` = no extraction warnings, `2` = partial data or
explicitly no results, `3` = retrieval/policy/format failure, `1` = invalid input
or command execution failure. A successful HTTP request can still exit `2`.

The `verify` command returns `0` when all investigations executed, **not when
integrations passed**. Its JSON has `execution_completed:true` and
`integration_pass_claimed:false`. Review each case and the feasibility report.
It stops further requests to a supplier after an access/rate-limit/robots-check
failure; skipped cases are explicit. Per-case `robots_disallowed` results do not
stop permitted product-URL probes.

Run these commands sequentially. Each client waits at least two seconds between
request starts per host, honors a longer robots crawl delay, checks every redirect
target, and never calls disallowed APIs or search URLs. 403/429/challenge pages
are not retried or bypassed. Recheck policies on each new command/run.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

Deterministic tests use synthetic minimal fixtures and mocked transport failures.
They do not prove live access. The separate live files in `docs/evidence/` contain
timestamped real requests and normalized offers. They are historical snapshots,
never current-price guarantees; a new live command performs new HTTP retrieval.

## Output rules

- Decimal amounts are JSON strings to preserve precision; missing numbers are
  `null`, never made-up zeros. Currencies remain separate.
- `exact_mpn` requires a full explicitly supplied MPN. Case and outside whitespace
  are normalized; suffixes, slashes and hyphens remain significant.
- `candidate_mpn` is an inferred observed title token. It is never promoted to an
  exact match; common engineering values such as `100nF` are excluded.
- `manufacturer_status:supplier_reported` describes site attribution, not
  independent manufacturer validation. Composite labels are `ambiguous`.
- `package` is the device case, `packaging` is shipping packaging. Price tiers
  keep their own shipping package where provided.
- VAT is `included`, `excluded` or `unknown`, with source attribution. Özdisan
  unit-price VAT semantics remain unverified. No fixed VAT rate or currency
  conversion is applied.
- Stock distinguishes `in_stock`, `out_of_stock`, `not_disclosed`, `unknown`,
  preorder/backorder/discontinued. Direnc.net numeric stock remains unknown even
  when its schema says out of stock; no count is invented.
- Source URLs come from actual supplier links or explicit caller-provided URLs.
  Example Özdisan URLs are manually sourced probes, not search-discovery proof.
- Retrieval timestamps describe when SONAR received the document, not when the
  supplier updated its underlying data. No persistent response cache is used.

## Layout

```text
src/sonar_a0/        models, normalization, policy-aware HTTP, CLI
src/sonar_a0/adapters/   supplier interface and two independent adapters
tests/              deterministic tests and clearly labeled synthetic fixtures
examples/           reproducible live case manifest
docs/ARCHITECTURE.md
docs/A0_FEASIBILITY_REPORT.md
docs/evidence/      committed, limited historical facts and request hashes
```

No full supplier HTML, executable site scripts, reviews, customer data, cookies
or response headers are committed. Website terms are separate from robots
permission; commercial reuse or redistribution must be assessed before a public
service. No supplier permission or stable official API agreement is claimed.

## A1.1 frontend redesign

The `design/sonar-ui` branch integrates the supplied SONAR design system into the existing A1 frontend. See [A1.1 validation and screenshots](docs/A1_1_VALIDATION.md) for verified tests, browser reproduction and limits. A1 backend contracts and temporary-session behavior remain unchanged.
