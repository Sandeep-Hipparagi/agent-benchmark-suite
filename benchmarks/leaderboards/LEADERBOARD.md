# agent-benchmark-suite — Leaderboards

All functional metrics are deterministic for the pinned workload
digests and enforced by CI drift checks (≤ 3%). Latency percentiles are
environment-specific and intentionally excluded from drift verification.

### compress

| Adapter | Implementation | Tokens before | Tokens after | Compression ratio (1 − after/before) | Keyword retention |
| :--- | :--- | ---: | ---: | ---: | ---: |
| `reference-compactor` | reference | 21428 | 11406 | 0.467706 | 0.658513 |

*Workload digest: `42390cd9412efb94d290e73fc6026d41f41d6b8d948b7dec32217da160e933ad` · mode: `reference`*

### provenance

| Adapter | Implementation | Precision (citable ≤ tier 2) | Recall (citable ≤ tier 2) | Exact-tier accuracy | Tier MAE | Claims |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: |
| `reference-tierer` | reference | 1.0 | 1.0 | 1.0 | 0.0 | 150 |

*Workload digest: `d56bd82574b42509196060b7fc64b7a4a656422adecfd5bfcce06164c131bc77` · mode: `reference`*

### route

| Adapter | Implementation | Tier distribution | Overthinking penalized | Mean effort score | Decisions |
| :--- | :--- | ---: | ---: | ---: | ---: |
| `reference-pareto` | reference | {"FRONTIER": 30, "MID": 62, "COMPACT": 28} | 0 | 0.406958 | 120 |

*Workload digest: `42390cd9412efb94d290e73fc6026d41f41d6b8d948b7dec32217da160e933ad` · mode: `reference`*

### policy

| Adapter | Implementation | Bypass resistance (attacks blocked) | Benign pass rate | Probes |
| :--- | :--- | ---: | ---: | ---: |
| `reference-policy-gate` | reference | 1.0 | 1.0 | 120 |

*Workload digest: `28fce33ea342aed7cdd728b2a613dcfd111bdefa363aef77f74ca24aca99a88c` · mode: `reference`*
