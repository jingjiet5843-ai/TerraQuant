# TerraQuant Hyperliquid — First Genuine Orderflow Screen

Historical sample: BTC 2026-09-02 00:00–24:00 UTC (one day).
Trades: 356,331; book rows: 642,640; snapshots: 16,066; median book interval 5.389s.

> No trading alpha is established by one day of data. Numbers are preliminary.

| Strategy | Hold | Train N | Test N | Test mean net bps | Test win % |
|---|---:|---:|---:|---:|---:|
| flow_momentum | 30s | 481 | 147 | -11.0441 | 0.0 |
| flow_momentum | 60s | 378 | 123 | -11.0065 | 2.4 |
| flow_momentum | 120s | 271 | 95 | -10.7496 | 3.2 |
| flow_exhaustion | 30s | 621 | 260 | -11.5631 | 0.0 |
| flow_exhaustion | 60s | 462 | 194 | -11.3819 | 0.0 |
| flow_exhaustion | 120s | 311 | 132 | -11.8662 | 1.5 |
| book_imbalance | 30s | 736 | 297 | -10.7715 | 0.3 |
| book_imbalance | 60s | 529 | 214 | -10.5313 | 1.4 |
| book_imbalance | 120s | 347 | 146 | -11.0519 | 2.7 |
| sweep_reversion | 30s | 26 | 0 | None | None |
| sweep_reversion | 60s | 26 | 0 | None | None |
| sweep_reversion | 120s | 26 | 0 | None | None |
| price_momentum | 30s | 390 | 107 | -11.0644 | 0.9 |
| price_momentum | 60s | 308 | 89 | -11.3669 | 2.2 |
| price_momentum | 120s | 227 | 72 | -11.7131 | 2.8 |
| price_reversion | 30s | 390 | 107 | -11.2018 | 0.0 |
| price_reversion | 60s | 308 | 89 | -10.9066 | 1.1 |
| price_reversion | 120s | 227 | 72 | -10.5548 | 6.9 |

Fee assumption: 9 bps round-trip, plus 2 bps adverse execution; bid/ask crossing included in prices.
Sample cannot verify repeatability or 1-second execution. Needs 30–90 full continuous days with event-level L2 and out-of-sample validation.