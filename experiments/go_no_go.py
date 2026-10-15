"""Go/no-go experiment: can three banks find laundering rings together that none can find alone?

Siloed: each bank only sees transactions touching its own customers and can only judge its own customers.
Collaborative: each bank flags its own customers using objective red flags (COSMIC-style), then shares ONLY
masked IDs of flagged accounts and their large transfers. A consortium graph links flagged accounts across banks.
"""
import hashlib
import hmac
import json
from pathlib import Path

import networkx as nx
import pandas as pd

D = Path(__file__).parent / "data"
tx = pd.read_csv(D / "transactions.csv", parse_dates=["Timestamp"])
acc = pd.read_csv(D / "accounts.csv").set_index("id")
rings = json.loads((D / "ground_truth_rings.json").read_text())
BANKS = ["BANK_A", "BANK_B", "BANK_C"]
START = tx["Timestamp"].min().normalize()
CONSORTIUM_KEY = b"demo-consortium-key"  # in reality: a key held by the sharing platform, never by a single bank
LARGE = 3000
COVER = 0.6  # a ring counts as found if one detected group covers >= 60% of its accounts


def mask(account_id: str) -> str:
    return hmac.new(CONSORTIUM_KEY, account_id.encode(), hashlib.sha256).hexdigest()[:12]


def red_flags(bank: str) -> dict:
    """Objective indicators for the bank's OWN customers, computed only from the bank's own view."""
    view = tx[(tx["From Bank"] == bank) | (tx["To Bank"] == bank)]
    own = acc.index[acc["bank"] == bank]
    flags = {}
    inc = view[view["To Bank"] == bank].groupby("To Account")
    out = view[view["From Bank"] == bank].groupby("From Account")
    for a in own:
        i = inc.get_group(a) if a in inc.groups else view.iloc[0:0]
        o = out.get_group(a) if a in out.groups else view.iloc[0:0]
        li, lo = i[i["Amount"] >= LARGE], o[o["Amount"] >= LARGE]  # judge on large transfers only
        indicators = []
        # 1. rapid pass-through: share of large inflow forwarded as large outflow within 72h
        if len(li) and len(lo):
            fwd = 0.0
            for t, amt in zip(li["Timestamp"], li["Amount"]):
                w = lo[(lo["Timestamp"] > t) & (lo["Timestamp"] <= t + pd.Timedelta(hours=72))]["Amount"].sum()
                fwd += min(w, amt)
            if li["Amount"].sum() >= 5000 and fwd / li["Amount"].sum() >= 0.7:
                indicators.append("rapid pass-through")
        # 2. rapid fan-in: large transfers from 3+ different senders, most from other banks, within 72h
        if len(li) >= 3:
            li_sorted = li.sort_values("Timestamp")
            for t in li_sorted["Timestamp"]:
                w = li_sorted[(li_sorted["Timestamp"] >= t) & (li_sorted["Timestamp"] <= t + pd.Timedelta(hours=72))]
                if w["From Account"].nunique() >= 3 and (w["From Bank"] != bank).mean() >= 0.5:
                    indicators.append("rapid fan-in"); break
        # 3. rapid fan-out: large transfers to 3+ different receivers within 48h
        if len(lo) >= 3:
            lo_sorted = lo.sort_values("Timestamp")
            for t in lo_sorted["Timestamp"]:
                w = lo_sorted[(lo_sorted["Timestamp"] >= t) & (lo_sorted["Timestamp"] <= t + pd.Timedelta(hours=48))]
                if w["To Account"].nunique() >= 3:
                    indicators.append("rapid fan-out"); break
        if not indicators:
            continue
        opened = pd.Timestamp(acc.loc[a, "opened"])
        if (START - opened).days < 90:
            indicators.append("new account")
        big = pd.concat([li, lo])
        if ((big["Amount"] >= 8000) & (big["Amount"] < 10000)).sum() >= 2:
            indicators.append("amounts just under 10k")
        if len(big) and (big["From Bank"] != big["To Bank"]).mean() >= 0.7:
            indicators.append("mostly cross-bank")
        if len(indicators) >= 2:
            flags[a] = indicators
    return flags


def score(groups):
    """Match detected groups (sets of real account ids) against ground-truth rings."""
    found, fp = [], 0
    for g in groups:
        hit = False
        for r in rings:
            cover = len(g & set(r["accounts"])) / len(r["accounts"])
            if cover >= COVER:
                found.append(r["ring_id"]); hit = True
        if not hit and not any(len(g & set(r["accounts"])) / len(g) >= 0.5 for r in rings):
            fp += 1
    return sorted(set(found)), fp


flags = {b: red_flags(b) for b in BANKS}
ring_accounts = {a for r in rings for a in r["accounts"]}

# ---------------- siloed ----------------
silo = {}
for b in BANKS:
    g = nx.Graph()
    own_flagged = set(flags[b])
    view = tx[((tx["From Bank"] == b) | (tx["To Bank"] == b)) & (tx["Amount"] >= LARGE)]
    for _, r in view.iterrows():
        if r["From Account"] in own_flagged and r["To Account"] in own_flagged:
            g.add_edge(r["From Account"], r["To Account"])
    groups = [set(c) for c in nx.connected_components(g) if len(c) >= 3]
    found, fp = score(groups)
    silo[b] = {"flagged_own_accounts": len(own_flagged),
               "flagged_that_are_ring_members": len(own_flagged & ring_accounts),
               "rings_found": found, "false_alarm_groups": fp}
silo_union = sorted({r for b in BANKS for r in silo[b]["rings_found"]})

# ---------------- collaborative (minimal sharing) ----------------
shared_ids = {mask(a): (b, a) for b in BANKS for a in flags[b]}  # (b, a) kept only for scoring, never shared
shared_edges = []
for b in BANKS:
    own_flagged = set(flags[b])
    view = tx[((tx["From Bank"] == b) | (tx["To Bank"] == b)) & (tx["Amount"] >= LARGE)]
    for _, r in view.iterrows():
        mine = r["From Account"] if r["From Bank"] == b else r["To Account"]
        if mine in own_flagged:
            shared_edges.append((mask(r["From Account"]), mask(r["To Account"]), b))
g = nx.Graph()
for s, t, _ in shared_edges:
    if s in shared_ids and t in shared_ids:  # both ends independently flagged by their own bank
        g.add_edge(s, t)
groups_masked = [c for c in nx.connected_components(g)
                 if len(c) >= 3 and len({shared_ids[m][0] for m in c}) >= 2]
groups = [{shared_ids[m][1] for m in c} for c in groups_masked]
collab_found, collab_fp = score(groups)

total_accounts = len(acc)
result = {
    "dataset": {"transactions": len(tx), "accounts": total_accounts, "rings": len(rings),
                "ring_accounts": len(ring_accounts)},
    "siloed": silo,
    "siloed_rings_found_any_bank": silo_union,
    "collaborative": {"rings_found": collab_found, "false_alarm_groups": collab_fp,
                      "candidate_groups": len(groups)},
    "data_shared": {"masked_accounts_shared": len(shared_ids),
                    "share_of_all_accounts": round(len(shared_ids) / total_accounts, 4),
                    "transfer_records_shared": len(shared_edges),
                    "share_of_all_transactions": round(len(shared_edges) / len(tx), 4),
                    "raw_customer_data_shared": "none (masked IDs, bank code, amount and time only)"},
}
(Path(__file__).parent / "results.json").write_text(json.dumps(result, indent=2))

print(f"Rings planted: {len(rings)}")
for b in BANKS:
    s = silo[b]
    print(f"  {b} alone: flagged {s['flagged_own_accounts']} own accounts "
          f"({s['flagged_that_are_ring_members']} are ring members) -> rings found {len(s['rings_found'])}, false alarms {s['false_alarm_groups']}")
print(f"Siloed, best of all banks: {len(silo_union)}/{len(rings)} rings")
print(f"Collaborative: {len(collab_found)}/{len(rings)} rings, false-alarm groups {collab_fp}")
print(f"Shared: {len(shared_ids)} masked accounts ({len(shared_ids)/total_accounts:.2%} of accounts), "
      f"{len(shared_edges)} transfer records ({len(shared_edges)/len(tx):.2%} of transactions)")
missed = sorted({r['ring_id'] for r in rings} - set(collab_found))
print("Missed by collaboration:", missed)
