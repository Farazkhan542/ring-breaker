# Ring Breaker: go/no-go experiment

Tests the core claim: three banks working alone miss cross-bank laundering rings, but find them when they share only masked IDs of red-flagged accounts.

## Run
```
pip install pandas numpy networkx
python generate_data.py          # writes data/ (SEED env var changes the random world)
python go_no_go.py               # prints results and writes results.json
```

## Data
`generate_data.py` creates a synthetic 3-bank world in the IBM AML (Kaggle) column layout: about 52,000 transactions and 6,000 accounts over 60 days. It includes normal traffic (salaries, card payments, person-to-person transfers, remittance-style forwarding) and 14 planted laundering rings (cycles, scatter-gather, layering chains), each spread across 2–3 banks. Ground truth is in `data/ground_truth_rings.json`.

## Method
- **Red flags** are objective, COSMIC-style indicators. Each bank computes them for its own customers only: rapid pass-through, rapid fan-in or fan-out of large transfers, new account, amounts just under 10k, mostly cross-bank. An account is flagged when it shows a behaviour flag plus at least one other indicator.
- **Siloed:** each bank links only its own flagged customers.
- **Collaborative:** each bank shares HMAC-masked IDs of its flagged customers and their large transfers (masked IDs, amount, time). An account joins a candidate group only if its own bank flagged it independently.
- A ring counts as found when one group covers at least 60% of its accounts.

## Results (4 random worlds)
| Seed | Siloed (any bank) | Collaborative | False-alarm groups | Transactions shared |
|---|---|---|---|---|
| 42 | 0 / 14 | 14 / 14 | 0 | 1.73% |
| 7 | 0 / 14 | 12 / 14 | 0 | 1.01% |
| 123 | 0 / 14 | 13 / 14 | 0 | 1.24% |
| 2026 | 1 / 14 | 12 / 14 | 0 | 1.75% |

## Caveats
This is our own synthetic data, and the rules were tuned once on seed 42, so real data will be harder. Next step: rerun on IBM's HI-Small file from Kaggle, which has the same From Bank / To Bank structure, and report those numbers in the deck.
