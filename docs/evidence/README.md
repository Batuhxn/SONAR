# A0 historical live evidence

These JSON files were produced by actual HTTP retrieval, not deterministic test
fixtures. Every case includes its supplier, operation, query, normalized fields,
warnings and actual request hashes/timestamps. A denied URL has `attempted:false`.
The report's dates are Türkiye time (UTC+3); JSON timestamps are UTC.

`run-1.json` and `run-2.json` are earlier investigation snapshots. The authoritative
final interpretation is `validated-run.json`, after conservative title-token and
quantity-tier VAT handling. Earlier undocumented `data-vat` interpretations are
superseded; do not consume them as verified tax evidence. No earlier snapshot
ever claims a full supplier integration PASS.

`access-policy.json` records the independently retrieved robots/terms URLs,
timestamps and hashes and only the few relevant robot directives. Robot permission
is not a permission to reuse/redistribute all website content.

`test-results.txt` contains the separate deterministic test output. All unit-test
prices, TEST identifiers and failure responses are explicitly synthetic.

The body hashes identify what was received but cannot reconstruct a full page.
Supplier pages can change. Fresh live verification must be run from
`examples/a0_cases.json`; these files must never be presented as current prices.
