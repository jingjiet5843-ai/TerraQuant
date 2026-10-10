# TerraQuant Hyperliquid — First Genuine Orderflow Screen

Historical sample: BTC 2026-09-02 12:00–13:00 UTC (one hour).
Trades: 20,881; book rows: 26,120; snapshots: 653; median book interval 5.392s.

> No trading alpha is established by one hour of data. Numbers are preliminary.

| Strategy | Hold | Train N | Test N | Test mean net bps | Test win % |
|---|---:|---:|---:|---:|---:|
| flow_momentum | 30s | 19 | 7 | -10.143 | 0.0 |
| flow_momentum | 60s | 14 | 5 | -11.468 | 0.0 |
| flow_momentum | 120s | 9 | 4 | -9.1098 | 0.0 |
| flow_exhaustion | 30s | 23 | 14 | -11.7546 | 0.0 |
| flow_exhaustion | 60s | 15 | 9 | -12.7661 | 0.0 |
| flow_exhaustion | 120s | 10 | 6 | -11.1971 | 0.0 |
| book_imbalance | 30s | 30 | 14 | -11.6985 | 0.0 |
| book_imbalance | 60s | 21 | 9 | -12.4769 | 0.0 |
| book_imbalance | 120s | 13 | 6 | -12.0206 | 0.0 |
| sweep_reversion | 30s | 2 | 0 | None | None |
| sweep_reversion | 60s | 2 | 0 | None | None |
| sweep_reversion | 120s | 2 | 0 | None | None |
| price_momentum | 30s | 16 | 5 | -11.8083 | 0.0 |
| price_momentum | 60s | 13 | 5 | -11.4168 | 0.0 |
| price_momentum | 120s | 8 | 4 | -11.3247 | 0.0 |
| price_reversion | 30s | 16 | 5 | -10.4524 | 0.0 |
| price_reversion | 60s | 13 | 5 | -10.8439 | 0.0 |
| price_reversion | 120s | 8 | 4 | -10.9359 | 0.0 |

Fee assumption: 9 bps round-trip, plus 2 bps adverse execution; bid/ask crossing included in prices.
Sample cannot verify repeatability or 1-second execution. Needs 30–90 full continuous days with event-level L2 and out-of-sample validation.