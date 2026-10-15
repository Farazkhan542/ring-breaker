# Ring Breaker

**Bank agents that catch money-laundering rings together, without sharing customer data.**
Google Cloud AI Builder Cup 2026 · Theme: BFSI (intelligent risk, fraud and financial experiences)

Launderers spread money-mule rings across several banks, so each bank sees only a harmless-looking slice. In Ring
Breaker, each bank runs its own investigator agent on its own data only. When a customer shows objective red flags,
the agent asks other banks' agents narrow questions over Google's **Agent2Agent (A2A)** protocol. A **policy agent**
enforces COSMIC-style sharing rules on every message (masked IDs, amount bands and 6-hour windows only), a
**case-writer agent** (Gemini via ADK) drafts the joint case file, a **skeptic agent** argues the innocent
explanation, and each bank's officer approves or rejects their part.

### Where Google AI does the work

| Agent | Model (via Google ADK) | What it decides or writes |
|---|---|---|
| Investigation planner | Gemini 3.5 Flash-Lite | Which cross-bank leads to follow next and which to drop, with a reason for the officer. Code checks it can only pick real leads; the policy agent checks every question it causes. |
| Bank assistant | Gemma 4 (open model a bank could host in-house); Gemini Flash-Lite as backup | Explains to the bank's own investigator why its customer was flagged. Runs on that bank's data only. |
| Case writer | Gemini 3.8 Flash | The joint case file in suspicious-transaction-report style, from masked facts only. |
| Skeptic | Gemini 3.8 Flash | The strongest innocent explanation, the evidence that would settle it, and the case's weak points. |

Every call has a fallback chain (other Gemini models, then a cached answer, then template text), so the demo always
completes. The page shows which model produced each piece of text.

## What exists, and what Ring Breaker adds

Banks already share intelligence across institutions, through people: Salv Bridge (Europe), Nasdaq Verafin's
consortium (US), BioCatch Trust (Australia) and MAS COSMIC (Singapore). AI agents for AML are arriving inside
individual banks (for example FIS with Anthropic, Hummingbird, Lucinity). The cross-bank step is still people
messaging people. Ring Breaker is the missing layer: **each bank's AI agent does the first round of cross-bank
questions itself, in seconds, under machine-checked sharing rules**, rebuilds the whole ring, and hands a joint
case to each bank's officer. To our knowledge (searches 14-16 Oct 2026), no product has AI agents at different
banks investigating one case together under automatically enforced sharing rules.

Why now: the EU AML Regulation makes AML information-sharing between institutions mandatory from July 2027, and
85% of 1,440 banking leaders surveyed by BioCatch (June 2026) say interbank sharing would help stop financial crime.

## Architecture

```
Browser ──► Cloud Run service (FastAPI)
             ├─ /                     web UI (static)
             ├─ /api/demo/run         orchestrator: streams the investigation (server-sent events)
             ├─ /a2a/bank_a|b|c/      three bank agents, each an A2A JSON-RPC endpoint + agent card,
             │                        each loaded with ONLY its own data partition
             ├─ policy agent          policy.yaml checks + audit log for every cross-bank message
             ├─ planner               Gemini (ADK) chooses which leads to follow
             ├─ bank assistants       Gemma (ADK) explains each bank's own flagged customers
             ├─ case writer, skeptic  Gemini (ADK) (live → cache → template fallback)
             ├─ decisions             Firestore (SQLite locally)
             └─ audit + results       BigQuery → Regulator tab and Looker Studio
```

The lead bank's agent reaches the other banks' agents through real A2A HTTP calls, even though all three are hosted
in one container for the prototype. In production each bank would run its agent as its own Cloud Run service in its
own Google Cloud project; the client currently reaches peers at `RB_A2A_BASE_URL/a2a/<bank>`, so separate services
need either one gateway with path-based routing or a small change to give each bank its own URL.

Design rules: **Gemini writes and argues; code computes every number.** Red flags, graph linking, confidence scores
and metrics are deterministic Python. Account IDs that cross banks are `HMAC-SHA256(consortium_key, id)` pseudonyms.

## Integration, scalability and performance

**Fitting into a bank's existing systems** (design; the adapters are not built in this prototype):
- *Input:* the bank agent would read alerts and transactions from the bank's existing transaction-monitoring system
  through an adapter to the IBM AMLworld column layout the agents already use. Ring Breaker adds to the bank's alerts
  rather than replacing them.
- *Output:* the joint case file is structured data (facts, confidence and reasons, case text, skeptic's view) whose
  fields map to a suspicious-transaction report, so it can feed the bank's case-management and filing process. A
  goAML-style export is planned. The officer still files.
- *Between banks:* A2A is an open protocol, so any bank's agent that speaks it can join. A consortium operator, such
  as a COSMIC-style platform, would hold the masking key and the shared `policy.yaml`.

**Scalability:** bank agents are stateless Cloud Run services that scale out; adding a bank means adding one agent.
Cross-bank traffic grows with the number of *flagged* customers, not total volume: under 2% of transactions were
shared in our synthetic tests. Red flags and graph work are plain Python and can run in batch, while models are
called per case, not per transaction. The IBM benchmark run (4.5 million transactions, 23,000+ banks) completes
offline in about 5 minutes on a laptop.

**Performance (measured on a laptop):** one case built in-process takes about 40-50 ms with 6-15 cross-bank
questions; the full demo, with live Gemini calls over A2A, finishes in about 36 seconds; officer decisions are
stored in Firestore.

## Regulator view (BigQuery and Looker Studio)

Every cross-bank message from the policy agent's audit log, every finished case and every evaluation result is written
to BigQuery (dataset `ringbreaker`: tables `audit_log`, `cases`, `eval_results`; views `v_bank_activity`,
`v_blocked_by_rule`, `v_cases_daily`) with batch load jobs from a background thread, so investigations never wait on
it. The app's **Regulator** tab reads the views back: questions answered, answers withheld, requests blocked and
masked IDs shared per bank, plus recent cases. Without BigQuery the same tab is computed from the server's memory.

Set up and load evaluation results: `RB_BQ_DATASET=ringbreaker GOOGLE_CLOUD_PROJECT=<project> python -m
ringbreaker.analytics setup`, then `... export-eval`. For a Looker Studio report, create a report in Looker Studio,
add a BigQuery data source pointing at `<project>.ringbreaker.v_bank_activity` (and the other views), and set
`RB_LOOKER_URL` on the service so the Regulator tab links to it.

## Run locally

```
uv venv .venv --python 3.12 && uv pip install --python .venv -r requirements.txt pytest
set GOOGLE_API_KEY=...            # or Vertex AI: GOOGLE_GENAI_USE_VERTEXAI=true + GOOGLE_CLOUD_PROJECT + GOOGLE_CLOUD_LOCATION
.venv/Scripts/python -m uvicorn ringbreaker.api:app --port 8080
.venv/Scripts/python -m pytest tests          # isolation, no raw IDs cross banks, forbidden asks blocked
.venv/Scripts/python -m ringbreaker.eval      # alone vs together -> results/metrics.json
```

Settings (environment variables): `RB_MODEL_ID` (default `gemini-3.8-flash`), `RB_FALLBACK_MODELS`,
`RB_LLM=off` to skip Gemini, `RB_CACHE_FIRST=true` for an instant demo from cached Gemini output,
`RB_CONSORTIUM_KEY` (Secret Manager in production).

## Deploy to Cloud Run

```
gcloud run deploy ring-breaker --source . --region asia-southeast1 --allow-unauthenticated \
  --min-instances 1 --memory 2Gi --cpu 2 \
  --set-env-vars GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=<project>,GOOGLE_CLOUD_LOCATION=global \
  --set-secrets RB_CONSORTIUM_KEY=rb-consortium-key:latest
```

## Results (synthetic three-bank worlds, strict scoring)

A ring counts as found only if one group holds at least half of its accounts **and** that ring makes up at least
half of the group. Reproduce with `python -m ringbreaker.eval`.

| Seed | Alone (best single bank) | Plain linking of masked IDs | Agent investigations | Agent false alarms | % transactions shared |
|---|---|---|---|---|---|
| 42 | 3 / 14 | 10 / 14 | 14 / 14 | 0 | 1.73% |
| 7 | 1 / 14 | 10 / 14 | 12 / 14 | 1 | 1.01% |
| 123 | 2 / 14 | 12 / 14 | 13 / 14 | 0 | 1.24% |
| 2026 | 4 / 14 | 9 / 14 | 12 / 14 | 1 | 1.75% |

Gemini planner vs rule-based order (seed 42, same 20 starting customers, `python -m ringbreaker.eval_planner`):
the planner asked **58% fewer cross-bank questions** (6.5 vs 15.3 per case) and added fewer wrong accounts
(0.45 vs 0.75 per case), for slightly lower ring coverage (0.59 vs 0.64).

Caveats: this is our own synthetic data, easier than real data, and the red-flag rules were tuned once on seed 42.

**IBM AMLworld HI-Small (public benchmark, 5M transactions, 30,470 banks, 282 labelled laundering rings with 3+
accounts; 366 of IBM's 370 rings span two or more banks)**, strict rule, `experiments/ibm_eval.py`:

| Local flags | Alone | Together (plain linking) | Agent cases |
|---|---|---|---|
| Perfect flags (ceiling) | 2 | 122 | 178 |
| Shared risk model, top 5% flagged | 0 | 40 | 56 |
| Shared risk model, top 2% flagged | 0 | 23 | 22 |
| Shared risk model, top 1% flagged | 0 | 13 | 11 |

Banks working alone recover essentially no rings; working together they recover up to 56 with realistic flags. With
perfect flags, case-by-case agent investigations beat plain linking (178 vs 122 rings, pair precision 0.40 vs 0.04).
Absolute recall with realistic flags is modest: flag quality (precision 0.10-0.19) is the bottleneck.

**TransXion (30 banks, 3M transactions), honestly reported:** under the strict rule almost no laundering clusters
are recovered by any method, even with perfect flags (2-7 of 369), because laundering accounts of different rings
also trade with each other normally, so linking flagged accounts merges rings. Our earlier "369 of 369" and
"32 vs 2" figures came from a loose rule that credited giant mixed groups. Next step: link through suspicious
transfers, not just suspicious accounts. Reproduce with `experiments/transxion_rescore.py`.

## Data and credits

- Synthetic data generated by `ringbreaker/synth.py` (IBM AMLworld column layout). **No real customer data is used.**
- IBM AMLworld HI-Small (IBM Research and ETH Zurich, NeurIPS 2023; CDLA-Sharing 1.0):
  https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml
  (mirror used: https://huggingface.co/datasets/OsamaMIT/IBM-AML-HI-Small). Paper: https://arxiv.org/abs/2306.16424
- TransXion benchmark (KDD 2026, Fudan University, MIT licence): https://github.com/chaos-max/TransXion
- Libraries: Google Agent Development Kit (Apache 2.0), A2A Python SDK (Apache 2.0), google-genai, FastAPI,
  pandas, NetworkX, scikit-learn. Fonts: IBM Plex (SIL OFL) via Google Fonts.
- Sharing rules are modelled on MAS COSMIC's principle of sharing only on objective indicators of suspicion;
  they are not legal advice.

## Responsible AI

Human in the loop (nothing is filed without each bank officer's approval); a skeptic agent challenges every case;
only masked IDs and coarse bands cross banks, and every message is policy-checked and audited; no protected
attributes are used; synthetic data only.

## Fresh work

All code in this repository was written during the AI Builder Cup build window (from 15 October 2026). The
`experiments/` folder holds our go/no-go scripts from the same day.
