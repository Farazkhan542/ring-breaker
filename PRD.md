# Ring Breaker — Product Requirements Document (PRD)

**Project:** Ring Breaker. Bank agents that catch money-laundering rings together, without sharing customer data.
**Competition:** Google Cloud AI Builder Cup 2026 (run by Hack2skill on behalf of Google Cloud)
**Theme:** BFSI — Intelligent Risk, Fraud & Financial Experiences
**Team:** Faraz Khan (agents, backend, Google Cloud) · Yumna (UI, demo story, submission)
**PRD date:** 15 October 2026 · **Submission deadline:** 18 October 2026 (aim to submit by midday)

> **For Claude Code:** this PRD is the source of truth. Read Section 1 (competition rules) first; every rule there is a hard constraint. Build in the milestone order in Section 11. When a library API is uncertain (ADK, A2A, Gemini model IDs), check the current official docs before writing code rather than guessing. Existing experiment code from `ring-breaker-go-no-go.zip` (`generate_data.py`, `go_no_go.py`, `transxion_test.py`, `transxion_test2.py`) should be reused and refactored, not thrown away.

---

## 1. Competition rules (hard constraints)

Sources: aibuildercup.com (home, FAQ, themes pages) and the organisers' emails. We could not read the full "Initiative Terms & Conditions" document, so check it on the participant dashboard.

### 1.1 Eligibility and team
- Open to **working professionals, entrepreneurs and startups**. Students are **not eligible**; a team with any student member is disqualified, even after shortlisting. Age **21+**. All members **based in the JAPAC region** (Japan & Asia-Pacific). Country was declared at registration and the registration was confirmed.
- Eligibility "may be verified at any point".
- Teams of **2–4 members**. Registration closed 11 October; team formation closed **14 October 2026**. One person can be in only one team.
- **One solution per team, under one problem statement / theme.** We submit only Ring Breaker, under BFSI.
- If shortlisted for the Grand Finale, **only 2 members travel** to Singapore (no third member, even self-funded). Flights, accommodation and meals on the finale day are sponsored for them. Flights are booked in each traveller's name, so travellers **cannot be swapped late**. Finalists are announced about 4 weeks ahead. A **valid passport** is required, and **visas (application, fees, timelines) are the participants' own responsibility**. **Action now:** decide the two travellers and check both passports.
- The programme is operated independently by Hack2skill and is not directly administered by Google Cloud.

### 1.2 Originality ("fresh work")
- Build window: **7 September – 18 October 2026** (programme registration opened 1 September).
- FAQ: "**Only fresh projects built during the hackathon timeline are eligible.**" "**Submissions based on pre-existing projects, or work started before the program launch, will not be considered.**" The go/no-go experiment code was written on 15 October 2026, inside the window.
- So all code is written during the hackathon. The repo must be **new**, with commit history from these days. Open-source libraries, official samples and public datasets are used **with credit** in the README. Whether this is acceptable has been raised with the organisers; record their answer in Section 15.

### 1.3 Technical requirements
- The solution **must leverage Google AI models (e.g. Gemini or Gemma)**, or be built with an agentic platform such as **Agent Platform, Antigravity or AI Studio**.
- The solution **must be deployed on Google Cloud** using **Cloud Run or Firebase**. The themes page phrases it as "deployed on Cloud Run/GCP/Firebase".
- It must be a **functional working prototype**, "not just a pitch deck or a mockup". A prototype is enough if it **runs end to end** and is deployed.
- Solutions "built primarily on **other clouds** are not eligible". **Rule for us:** everything runs on Google Cloud, and the product calls only Google models (Gemini/Gemma). No other LLM providers or hosting in the product.
- The themes page also asks that the solution "consider **scalability, performance, and integration with existing systems**". See Section 6.2.

### 1.4 What the submission must demonstrate
1. The problem being solved, and why it matters
2. How the solution addresses it
3. How Google AI models or agentic technologies are integrated
4. A functional working prototype
5. How it is deployed on GCP

### 1.5 Submission deliverables
- **A working deployed link** to the prototype. It must stay up during evaluation.
- **A video demo under 3 minutes** (target 2:45), as a public YouTube, Vimeo or Google Drive link. Add **English captions**.
- **A public GitHub repository** of the prototype.
- **A PDF deck** explaining the solution in detail, covering the **problem, the benefit to the community (Section 2.1), feasibility and scalability**. A deck template may be provided on the dashboard; use it if so.
- Identify the chosen **problem statement / theme**. The form's category list (Healthcare, Education, Sustainability, Accessibility, Social Good) doesn't match the six themes; ask the organisers and record the answer in Section 15.
- **All submission materials, including code, documentation and presentations, must be in English.**
- Themes page, general expectation: solutions should be "**functional, user-friendly, accessible, scalable, and aligned with social impact**". Accessibility is covered in Section 8 and social impact in Section 2.1.

### 1.6 Judging criteria (weighted)
| Criterion | Weight | Sub-points |
|---|---|---|
| Technical Merit & Gen AI Implementation | **40%** | Meaningful use of Gen AI (does it directly solve the problem?); technical implementation (functional, sound); scalability & sustainability |
| Problem Alignment & Impact | **25%** | Fit with the chosen theme; clear, meaningful value for intended users |
| Innovation & Creativity | **25%** | Originality and meaningful differentiation from existing solutions; creative use of Gen AI beyond the basic or superficial |
| User Experience & Solution Design | **10%** | Usability and accessibility; components, including Gen AI, working together smoothly |

### 1.7 Timeline after submission
- **18 Oct 2026:** submissions close (exact time and time zone: see Section 15, Q6)
- **19 Oct – 6 Nov 2026:** evaluation (scoring round). **The deployed link must stay up and fast for this whole window**; we keep it live until at least 7 Nov.
- **October:** Top 200 shortlist and **architecture sprints**. Keep the architecture diagram, scalability story (Section 6.2) and cost estimate ready to present.
- **7 Nov 2026:** Top 50 finalists announced, followed by mentorship
- **4 December 2026:** Grand Finale (Demo Day) in Singapore, live in-person demo

### 1.8 Support
- Organiser sessions (intro and problem-statement explainer) are in the dashboard's interaction section. **Watch the BFSI explainer** and note anything it stresses (Section 15).
- Contact: support+aibuildercup@hack2skill.com, or the Discord community.

---

## 2. Problem

Launderers spread money-mule rings across several banks, so each bank sees only a harmless-looking slice. Banks can't simply pool customer data because of confidentiality and privacy law. Investigators inside one bank therefore can't see the whole ring.

**Evidence (cite in the deck):**
- Swift ran experiments with 13 banks, with Google Cloud as a technology partner, on 10 million artificial transactions. A collaborative model was **twice as effective** at identifying known fraud as single-bank models. It used privacy-enhancing tech and federated learning, **not LLM agents**.
- Singapore's MAS launched **COSMIC** in April 2024 with DBS, OCBC, UOB, Citibank, HSBC and Standard Chartered. Banks share customer information **only when "objectively defined indicators of suspicion" are present**.
- BIS Innovation Hub's **Project Aurora** found collaborative analysis detects laundering networks more effectively than siloed analysis.
- **Our own result (Section 9):** on synthetic three-bank worlds with strict scoring, banks alone find 1–4 of 14 rings, plain linking of masked IDs 9–12, and agent investigations 12–14, sharing under 2% of transactions. The Gemini planner cuts cross-bank questions by 58%. **Do not cite the old TransXion "369 of 369" or "16×" figures:** re-scored on 15 Oct with the strict rule, they do not hold (see Section 9.2).

**Opening story for the video:** "Five accounts at three banks pass money in a loop. Each bank sees two ordinary-looking transfers. Together, they form a laundering ring that none of them can see alone."

### 2.1 Community benefit and social impact (deck slide)
- **Scam victims:** mule rings move stolen money from investment, romance and job scams. Finding the whole ring sooner gives a better chance of freezing funds before they leave the system.
- **People recruited as mules:** mule networks often recruit students, job seekers and migrant workers, who face criminal liability. Catching rings early limits the damage to them, and the skeptic agent plus human review protect innocent people from wrong accusations.
- **Smaller banks and digital banks:** they lack big investigation teams and see only small slices. A shared agent protocol lets them collaborate without building a data-sharing platform.
- **Privacy for everyone:** collaboration happens with masked IDs only, triggered by objective red flags. Customers who aren't flagged are never shared.
- **Regulators:** every cross-bank message is audited and rule-checked, which makes the collaboration easy to supervise.

---

## 3. Solution overview

Each bank runs its **own investigator agent on its own data only**. When a customer shows **objective red flags**, the agent can ask other banks' agents narrow questions over **Google's A2A (Agent2Agent) protocol**. A **policy agent** enforces COSMIC-style sharing rules: share only when objective red flags exist, and share only **masked account IDs and risk signals, never raw customer data**. The agents link the pieces into one ring and co-write a **joint case file**. A **skeptic agent** argues the innocent explanation, and each bank's human officer approves or rejects their part.

### 3.1 What exists vs. what we add (deck slide)
| Already exists | Ring Breaker adds |
|---|---|
| Cross-bank AML using privacy tech and federated learning (Swift experiments, BIS Aurora, Rhino, Partisia, Duality); hashing-based collaborative mining (paper "Towards Collaborative AML Among Financial Institutions", 2025) | **LLM investigator agents** that talk to each other and **explain their reasoning** |
| Human-driven sharing platforms (MAS COSMIC) | **Sharing rules as readable policy** enforced automatically by a policy agent |
| Agentic AML investigation tools inside a single bank (Hummingbird, Unit21, Hawk AI, Lucinity, NICE Actimize) | Agents at **different banks working one case together over A2A**, with human sign-off per bank |

Claim wording: "To our knowledge (searches on 14–15 October 2026), no one has built an LLM-agent version of cross-bank investigation."

---

## 4. Users and user stories
- **Bank AML investigator (primary).** "When my customer shows red flags, I want to know whether they're part of a wider ring at other banks, without breaking privacy rules, so I can file a stronger report."
- **Compliance officer.** "I want to read and change the sharing rules in plain language, and see an audit trail of every piece of data that left my bank."
- **Regulator or consortium operator (secondary).** "I want evidence that collaboration finds more rings while sharing minimal data."
- **Judge (demo persona).** "Within 30 seconds of opening the link, I want to see the ring go from invisible to visible, and understand why."

---

## 5. Scope

### 5.1 In scope (MVP, must ship)
1. **Data layer:** TransXion benchmark (30 banks) for the evaluation, plus our synthetic 3-bank dataset for the scripted demo scenario.
2. **Bank agent** (one instance per bank): deterministic red-flag and graph tools over its own data only; Gemini explains the findings.
3. **Policy agent:** enforces sharing rules from a readable `policy.yaml`, and blocks and logs violations.
4. **A2A exchange:** bank agents expose an A2A endpoint and query each other with narrow, policy-checked questions.
5. **Case builder / writer agent:** links answers into ring candidates and drafts a joint case file (suspicious-activity report style).
6. **Skeptic agent:** argues the innocent explanation for each case and lists missing evidence.
7. **Human approval:** each bank's officer approves or rejects their portion; decisions are stored.
8. **Evaluation harness:** reproducible "alone vs. together" experiment with metrics (Section 9).
9. **Web UI** with the screens in Section 8, a **"Try the demo" button with sample data and no login**.
10. **Deployment on Cloud Run**, with a public URL that stays up through evaluation.

### 5.2 Stretch (only after the MVP is deployed)
- **Event-triggered ATM video evidence** (Section 13): faces blurred, no identification, behaviour description only.
- Memory of officer decisions (ADK memory / Memory Bank) to adjust future confidence.
- BigQuery for the audit log and metrics.
- Rerun on IBM AMLworld HI-Small (Kaggle) if downloaded manually.

### 5.3 Out of scope
- Real bank data or real customer information
- Facial recognition, identity guessing, emotion inference, live surveillance
- Automatic filing to any regulator; anything without human approval
- Legal advice: the sharing rules are *modelled on* COSMIC, not legally certified

---

## 6. Architecture

```
                 ┌───────────────────────── Web UI (Next.js, Cloud Run) ─────────────────────────┐
                 │  Bank views · Shared-data panel · A2A conversation · Joint case file · Metrics │
                 └───────────────────────────────┬────────────────────────────────────────────────┘
                                                 │ REST/WebSocket
                         ┌───────────────────────▼────────────────────────┐
                         │  Orchestrator API (FastAPI + ADK, Cloud Run)   │
                         │  Case builder / writer agent · Skeptic agent   │
                         │  Policy agent (policy.yaml) · Audit log        │
                         └──────┬──────────────────┬──────────────────┬───┘
                           A2A  │             A2A  │             A2A  │
                    ┌───────────▼───┐   ┌──────────▼────┐   ┌─────────▼─────┐
                    │ Bank A agent  │   │ Bank B agent  │   │ Bank C agent  │   (each: ADK agent,
                    │ own data only │   │ own data only │   │ own data only │    own data partition)
                    └───────────────┘   └───────────────┘   └───────────────┘
                       Tools: red_flags(), local_graph(), answer_query() — deterministic Python
                       LLM: Gemini (explanations, query planning, report drafting)
```

**Key design rules**
- **Gemini for understanding and explanation; code for numbers.** All metrics, graph analysis and red flags are deterministic Python tools. The LLM never computes amounts or counts.
- **Gemini must do real decision work, not just write summaries** (Technical Merit & Gen AI is 40% of the score; judges look for use "beyond the basic or superficial"). Gemini's jobs, each visible in the UI:
  1. **Investigation planning:** the bank agent decides which narrow question to ask which bank next, based on the evidence so far, and stops when the case is complete or the policy limit is reached.
  2. **Policy reasoning:** the policy agent turns a compliance officer's plain-English rule ("never share anything about accounts older than 5 years unless…") into `policy.yaml` for human review, and explains in words why each request was allowed or blocked.
  3. **Case splitting:** the case builder proposes how to split an over-merged group (by time window, flow direction, pattern) and justifies it; code checks the split.
  4. **Adversarial review:** the skeptic agent argues the innocent explanation and names missing evidence; the case builder must respond.
  5. **Report drafting:** the joint case file in suspicious-transaction-report style.
- **Data isolation.** Each bank agent loads only its own partition (accounts where `bank == X`, plus transactions touching them). Enforce this in code and test it.
- **Masking.** Account IDs crossing banks use `HMAC-SHA256(consortium_key, account_id)[:12]`. The key is held by the orchestrator (consortium operator), never shown in the UI, and stored in Secret Manager.
- **Every cross-bank message passes the policy agent** and is written to the audit log: who asked, what was asked, what was shared, which rule allowed it.

### 6.1 Tech stack
- **Language:** Python 3.11+ (agents, API); TypeScript/Next.js (UI). A plain React or Vite build is acceptable if faster.
- **Agents:** Google **Agent Development Kit (ADK)** for Python, with ADK's **A2A** support for bank-to-bank calls. Check the current ADK docs for exact A2A APIs.
- **Model:** Gemini via **Vertex AI** (preferred, uses Google Cloud credits) or the Gemini API. Default to the current stable Flash model. Google's model list on 14 Oct 2026 showed `gemini-3.8-flash` as stable; verify before use and keep the model ID in config.
- **Hosting:** **Cloud Run**, either two services (`api`, `web`) or one service per bank agent plus orchestrator if time allows. A single API service that hosts three in-process bank agents talking over real A2A HTTP endpoints is acceptable for the MVP.
- **Storage:** data partitions as Parquet in **Cloud Storage** (or baked into the container if under ~300 MB); case and decision store in **Firestore** or SQLite; secrets in **Secret Manager**.
- **Optional:** BigQuery for the audit log and metrics.

### 6.2 Scalability, performance and integration with existing systems
**Integration (how a real bank would adopt it):**
- **Input:** the bank agent reads alerts from the bank's existing transaction-monitoring system (e.g. NICE Actimize, SAS, Oracle FCCM) through a small adapter that maps alerts and transactions to our schema (IBM AMLworld column layout). Our red flags supplement the bank's alerts; they don't replace them.
- **Output:** the joint case file exports as JSON and PDF, with fields mapped to a suspicious-transaction report (e.g. UNODC goAML-style fields), so it fits the bank's existing case-management and filing process. The human officer still files.
- **Between banks:** A2A is an open protocol, so each bank hosts its own agent in its own Google Cloud project. A consortium operator (for example a COSMIC-style platform) holds the masking key and policy file.
- **Identity and access:** each bank's officer sees only their bank's view. Each bank agent authenticates to others (service identity per bank on Cloud Run).

**Scalability:**
- Bank agents are stateless Cloud Run services that scale out per bank. Adding a bank means adding one agent and one entry in the consortium registry.
- Cross-bank traffic grows with the number of **flagged** accounts (about 1–2% of transactions shared in our tests), not with total transaction volume.
- The deterministic feature and graph work runs in batch (and can move to BigQuery); Gemini is called only per case, not per transaction.
- Shown on TransXion: 30 banks, about 3M transactions.

**Performance targets (measure and report):**
- Demo scenario end to end: < 60 s, with cached Gemini responses as fallback.
- One case build (queries + linking + case file draft): target < 20 s with live Gemini.
- TransXion evaluation harness: report runtime and machine size.
- Cost: estimated Gemini calls and USD cost per case built (deck "feasibility" slide).

---

## 7. Agents — detailed spec

### 7.1 Bank agent (×N)
- **Input data:** its own partition only.
- **Tools (deterministic):**
  - `compute_red_flags(account_id)` returns the list of objective indicators. Start from `go_no_go.py`: rapid pass-through, rapid fan-in, rapid fan-out of large transfers, new account, amounts just under a reporting threshold, mostly cross-bank. On TransXion, use the learned risk score from `transxion_test2.py` (a model trained on *other* banks' labelled cases) as an extra indicator.
  - `list_flagged_customers()` returns the bank's flagged customers with indicators.
  - `local_graph(account_id, hops=2)` returns the local transaction neighbourhood (own customers plus masked external counterparties).
  - `answer_query(query)` answers narrow A2A questions about the bank's **own** customers, e.g. "Is masked account X flagged? Did X receive ≥3 transfers from new accounts within 72h? Which masked counterparties did X forward funds to within 72h?" It returns booleans, counts, masked IDs, amount bands and time windows **only**.
- **LLM role:** plans which questions to ask other banks, summarises local evidence in plain English, and explains why a customer is flagged.

### 7.2 Policy agent
- Loads `policy.yaml`, written in plain language and machine-checkable. Example rules:
  - `share_only_if`: the subject account is flagged locally with ≥2 objective indicators
  - `allowed_fields`: masked_id, bank_code, amount_band, time_window, indicator_names
  - `forbidden_fields`: names, raw account numbers, addresses, balances, device/IP data
  - `max_hops_per_case`: 3; `max_queries_per_case`: 20
- Checks every outgoing A2A request and response. Blocked requests are shown in the UI with the rule that blocked them. **The demo must include at least one blocked request.**

### 7.3 Case builder / writer agent
- Merges answers into a ring graph across banks.
- Splits over-merged groups. On TransXion, simple linking can merge several rings into one blob, so the agent should split by time windows and flow direction.
- Assigns a confidence score with reasons, and drafts the **joint case file**: summary, ring map, timeline, per-bank evidence (masked), indicators, recommended action.

### 7.4 Skeptic agent
- For each case, writes the strongest innocent explanation (e.g. payroll, family remittance, merchant settlement) and lists the evidence that would confirm or refute it. The case file shows both sides.

### 7.5 Human approval
- Each bank's officer sees only their bank's portion plus the masked shared picture, and approves, rejects or requests more evidence. Decisions are stored with timestamp and reason. Nothing is "filed" automatically.

---

## 8. UI screens (Yumna)
1. **Landing / "Try the demo"**: one-sentence pitch and a big button that runs the scripted scenario on synthetic data. No login.
2. **Three bank views side by side**: each shows only its own flagged customers and partial transfers. A banner reads "Bank A alone: no ring found".
3. **A2A conversation panel**: live stream of agent-to-agent questions and answers, each tagged with the policy rule that allowed it. Blocked requests are shown in red.
4. **Shared-data panel**: exactly what left each bank (masked IDs, bands, windows) vs. what was withheld. Shows the "% of transactions shared" counter.
5. **Ring map and joint case file**: graph visualisation of the reconstructed ring across banks, timeline, skeptic's view, approve/reject buttons per bank.
6. **Metrics page**: alone vs. together results on TransXion (Section 9 table), with the method and caveats.

**UX requirements:** works on a laptop screen at 1366px wide; readable in light theme; the full demo completes in under 60 seconds; every number has a tooltip explaining it.

**Accessibility requirements (judged under "Usability and accessibility"):**
- Everything works with the keyboard alone, with visible focus.
- Text contrast meets WCAG 2.1 AA (4.5:1 for normal text).
- Ring map colours that colour-blind users can tell apart, and banks also distinguished by shape or label, not colour alone. Blocked and allowed states use an icon and text as well as red and green.
- A **text alternative to the ring map** (a table of masked accounts, banks and links) for screen readers.
- Live A2A conversation panel announced politely to screen readers (`aria-live="polite"`) and pausable.
- Plain-language explanations; abbreviations (A2A, AML, STR) explained on first use.
- Demo video has English captions.

---

## 9. Data and evaluation

### 9.1 Datasets
| Dataset | Use | Notes |
|---|---|---|
| **TransXion** (KDD 2026, Fudan University). Repo: github.com/chaos-max/TransXion (MIT licence). `tx.csv` downloadable from `https://media.githubusercontent.com/media/chaos-max/TransXion/main/data/tx.csv` (245 MB) | **Main evaluation** | 3,029,170 transactions, 47,526 accounts, 30 banks, 4,641 laundering transactions, 365 days. Every account belongs to exactly one bank. 1,804 laundering clusters, 97% spanning ≥2 banks; 369 clusters have ≥3 accounts. Laundering amounts resemble normal amounts (median ~53 vs ~52), so detection must use flow, timing and graph features. |
| **Our synthetic 3-bank dataset** (`generate_data.py`) | **Scripted demo scenario** | ~52k transactions, 6k accounts, 3 banks, 14 planted rings (cycle, scatter-gather, layering). IBM-style columns. |
| IBM AMLworld HI-Small (Kaggle) | Optional second benchmark | Kaggle is blocked from the build sandbox; only if downloaded manually. |

Credit all datasets in the README and deck. Say clearly that no real customer data is used; the SynthAML paper (*Scientific Data*, 2023) notes there are no public real AML datasets because bank transactions are confidential.

### 9.2 Baseline results already obtained (reproduce in the harness)
- **Synthetic, 4 random worlds:** alone 0–1 of 14 rings; together 12–14 of 14; 0 false-alarm groups; 1.0–1.8% of transactions shared.
- **TransXion, perfect local flags (ceiling):** alone 22 of 369 clusters; together 369 of 369.
- **TransXion, unsupervised flags (Isolation Forest per bank):** together beats alone at every flag rate (best: 31 vs 2 at 10%).
- **TransXion, supervised flags (model trained on the other half of banks, no leakage):**

| Flag rate | Flag precision | Alone | Together |
|---|---|---|---|
| 5% | 0.90 | 2 | 32 |
| 10% | 0.65 | 5 | 17 |
| 15% | 0.49 | 8 | 16 |

**Re-scored on 15 Oct (`experiments/transxion_rescore.py`, results/transxion.json):** under the strict rule, TransXion clusters recovered are alone 0–3, together 0–2, agent cases 0–7 of 369, even with perfect flags; pair precision is about 0.01. Laundering accounts of different rings also trade with each other normally, so linking flagged accounts merges rings. Present TransXion as a hard benchmark and a stated limitation, with the next step "link through suspicious transfers, not just suspicious accounts". The synthetic results and planner comparison are the headline evidence.

**Known problem with these numbers (found on 15 Oct review):** the scoring credits a cluster as "recovered" if any group holds ≥50% of its accounts, so one giant group gets credit for every cluster inside it. The supervised 5% result (32 vs 2) comes from **a single group** (`collab_groups: 1`), and the unsupervised 10% result (31 vs 2) is also one group with group precision 0.0. On the synthetic data, 14 rings were found in only 11 groups, so some groups merge rings. Until re-scored, the most defensible realistic number is supervised 10%: **17 vs 5 (about 3.4×) across 56 groups, group precision 0.75**.

### 9.3 Metrics the harness must output
- Clusters/rings recovered alone vs. together. A ring is recovered if one group holds ≥50% of its accounts **and** that ring makes up ≥50% of the group (i.e. the group is mostly this ring). Use the same rule for synthetic and TransXion data, and also report the old, looser rule for comparison.
- Group precision (share of candidate groups that are mostly laundering)
- Flag precision and recall
- **Data shared:** masked accounts shared (% of all accounts) and records shared (% of transactions)
- **Agent value-add (target):** ring recovery and precision after the case-builder agent splits and refines groups, vs. the plain linking baseline
- Average case-build time

### 9.4 Honesty rules
- Report real numbers only, with the method and seeds.
- State that the synthetic results are easier than TransXion.
- Headline claim (synthetic, strict rule): "**Banks alone found 1–4 of 14 rings; agents working together found 12–14, sharing under 2% of transactions as masked IDs. The Gemini planner cut cross-bank questions by 58%.**" Earlier template: "Sharing finds N× more rings…", where N comes from the strict rule in Section 9.3, with the caveat that absolute recall is modest. Do **not** use the old "16×" figure unless it survives the strict rule.
- Show the plain-linking baseline and the case-builder agent's split side by side. The improvement from splitting is the agents' measurable contribution.
- The synthetic rules were tuned on seed 42, and the planted rings use the patterns the rules look for. Say so in the deck. The demo uses seed 42 (at seed 2026 one bank finds a ring alone).

---

## 10. Non-functional requirements
- **Deployment:** Cloud Run, region near Asia-Pacific (e.g. `asia-southeast1`); **min instances 1 from submission until at least 7 Nov 2026** (the whole evaluation window, 19 Oct – 6 Nov) so the link loads quickly; health check endpoint; an uptime check with email alert; a **billing budget alert** so credits don't run out mid-evaluation. Don't redeploy breaking changes during evaluation.
- **Google-only stack:** all hosting, storage and models on Google Cloud (Section 1.3).
- **Accessibility:** see Section 8.
- **Reliability:** if Gemini calls fail or quota is hit, the UI falls back to precomputed explanations for the demo scenario and still completes.
- **Cost:** cache Gemini responses for the scripted demo; precompute TransXion features offline.
- **Security:** no secrets in the repo; Secret Manager for the consortium key and API keys; read-only data.
- **Logging:** Cloud Logging for agent steps; audit log for every cross-bank message.
- **Repo:** public GitHub, new repo, README with setup, architecture diagram, dataset credits, results table, and a "fresh work during hackathon" note.

---

## 11. Milestones (Pakistan time)

| When | Faraz (agents, backend, GCP) | Yumna (UI, story, submission) | Done when |
|---|---|---|---|
| **Thu 15 Oct** | New repo; port experiment code; fix the scoring rule (Section 9.3) and re-score; data partitions per bank; ADK skeleton with one bank agent and one tool; deploy "hello" to Cloud Run | Watch the BFSI explainer session; screen sketches; demo script; questions to organisers (Discord/email); decide the two finale travellers | Public Cloud Run URL responds; repo public |
| **Fri 16 Oct** | 3 bank agents + policy agent + real A2A calls; case builder; scripted synthetic scenario end to end on Cloud Run | Build screens 1–5 against the API | Demo scenario runs end to end on the deployed URL |
| **Sat 17 Oct** | Skeptic agent; approvals; evaluation harness on TransXion; metrics endpoint; caching and fallback | Metrics page; record the video (<3 min); write the deck | Numbers in the deck come from the harness; video recorded |
| **Sun 18 Oct** | Bug fixes; README and architecture diagram; final redeploy | Final checks; **submit by midday** | All 4 deliverables submitted |

Stretch (Section 13) is attempted only if the Friday "done when" is met.

---

## 12. Acceptance criteria
- [ ] Opening the deployed URL shows "Try the demo"; the full scenario completes in under 60 s with no login.
- [ ] Each bank view shows "no ring found" when working alone; after A2A, the ring map shows the full ring across 3 banks.
- [ ] At least one A2A request is **blocked by the policy agent**, with the rule shown.
- [ ] The shared-data panel shows only masked IDs, bands and windows; a test asserts no raw account IDs leave a bank.
- [ ] The joint case file includes the skeptic's view and per-bank approve/reject actions; decisions persist.
- [ ] The metrics page shows alone vs. together on TransXion, reproduced by `python -m ringbreaker.eval` with fixed seeds.
- [ ] Gemini runs through ADK (Vertex AI or Gemini API); the model ID is configurable.
- [ ] Deployed on Cloud Run; the repo is public; the README credits datasets and libraries; everything is in English.
- [ ] Demo video under 3 minutes with English captions; PDF deck covers problem, community benefit (Section 2.1), feasibility (incl. cost per case), scalability and integration (Section 6.2), plus the "what exists vs. what we add" slide.
- [ ] Every headline number in the deck uses the strict scoring rule (Section 9.3).
- [ ] UI passes the accessibility checks in Section 8 (keyboard-only run of the demo; contrast check; text alternative for the ring map).
- [ ] The product uses only Google Cloud and Google models.
- [ ] Uptime check and billing alert are set; min instances 1 until at least 7 Nov.

---

## 13. Stretch: event-triggered ATM video evidence (privacy-safe)
- **Trigger:** only after a ring is confirmed and a ring account makes a cash withdrawal. Pull the clip for that ATM and time only. No live monitoring.
- **Processing:** blur faces before any model sees the frame (e.g. a face-detection library such as MediaPipe). Gemini describes **actions only** ("second person stands within arm's length", "user checks phone before each step"). **No identification, no emotion inference, no demographic attributes.**
- **Sharing:** the clip never leaves the bank. Only a one-line text signal can be shared over A2A, through the policy agent.
- **Data:** 3–4 staged clips with consenting actors, including one innocent withdrawal the agent should clear.
- **Rationale:** the EU AI Act has prohibited, since 2 Feb 2025, emotion recognition at work and in education, biometric categorisation by sensitive traits, untargeted facial scraping from CCTV, and real-time remote biometric identification in public for law enforcement. Singapore's PDPC has CCTV guidance. Use this as the design benchmark.

---

## 14. Responsible AI (deck slide and README section)
- Human in the loop: no case is filed without officer approval; the skeptic agent challenges every case.
- Data minimisation: only masked IDs and coarse bands cross banks; every transfer is audited and policy-checked.
- No protected attributes are used as features; explanations are shown for every flag.
- Synthetic and benchmark data only; limitations and false-positive risk are stated openly.

---

## 15. Open questions (fill in from Ask the Expert / organisers)
1. Are open-source reference code (ADK samples) and public datasets acceptable under the fresh-work rule, and how should we credit them? → *Answer:*
2. If agents run on Agent Engine and the frontend on Cloud Run, does that meet the "Cloud Run or Firebase" requirement? → *Answer:*
3. How long after 18 Oct must the link stay live? Will evaluators use their own inputs? → *Partial answer (home page):* evaluation runs 19 Oct – 6 Nov and finalists are announced 7 Nov, so we keep it live until at least 7 Nov (longer if shortlisted). Still ask whether evaluators use their own inputs.
4. Do the credits cover the Gemini API or only Vertex AI? → *Answer:*
5. Which category to select, given the form lists categories (Healthcare, Education, Sustainability, Accessibility, Social Good) that don't match the six themes? → *Answer:*
6. Exact submission closing time on 18 Oct and time zone? (The welcome email's timeline says "prototype build and submission: September 2026", but the stated deadline is 18 Oct.) → *Answer:*
7. What did the BFSI problem-statement explainer session emphasise? → *Notes:*
8. Will there be a deck template on the dashboard? → *Answer:*

Ask on Discord or at support+aibuildercup@hack2skill.com.

---

## 16. Sources
- AI Builder Cup: https://aibuildercup.com · FAQ: https://aibuildercup.com/Faqs.html · Themes and judging: https://aibuildercup.com/themes.html (checked again 15 Oct 2026) · Organiser welcome email
- Swift collaborative fraud experiments: https://www.swift.com/news-events/news/swift-led-experiments-reveal-blueprint-collaborative-fraud-defence-using-ai
- MAS COSMIC (iTnews): https://www.itnews.asia/news/singapore-launches-digital-platform-to-combat-financial-crime-606626
- BIS Project Aurora: https://www.bis.org/publ/othp66.htm
- TransXion: https://github.com/chaos-max/TransXion · paper: https://arxiv.org/pdf/2604.17420
- IBM AMLworld paper: https://arxiv.org/html/2306.16424v1 · Kaggle: https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml
- Towards Collaborative AML Among Financial Institutions: https://arxiv.org/pdf/2502.19952
- SynthAML (Scientific Data 2023): https://pmc.ncbi.nlm.nih.gov/articles/PMC10539331
- Gemini models: https://ai.google.dev/gemini-api/docs/models
- EU AI Act Article 5 summary: https://cdn.presencis.com/regulations/eu-ai-act/article-5/
- Singapore PDPC advisory guidelines: https://pdpc.gov.sg/-/media/files/pdpc/pdf-files/advisory-guidelines/ag-on-selected-topics/advisory-guidelines-on-the-pdpa-for-selected-topics-(revised-may-2024).pdf
