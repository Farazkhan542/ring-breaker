"""Feasibility test on TransXion (30 banks, 3M transactions): do banks find laundering clusters better together?

Part A (ceiling): assume each bank perfectly flags its own laundering-involved customers.
  How much of each laundering cluster can a single bank connect, vs. all banks sharing flagged IDs?
Part B (realistic): each bank flags its riskiest own customers with an unsupervised score
  (no labels used), then the same alone-vs-together comparison.
"""
import json
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

DATA = Path("/home/claude/TransXion/data/tx.csv")
df = pd.read_csv(DATA, parse_dates=["Timestamp"])
df = df[df["From Account"] != df["To Account"]]
bank_of = dict(zip(df["From Account"], df["From Bank"]))
bank_of.update(zip(df["To Account"], df["To Bank"]))

L = df[df["Is Laundering"] == 1]
lg = nx.Graph(); lg.add_edges_from(zip(L["From Account"], L["To Account"]))
clusters = [set(c) for c in nx.connected_components(lg) if len(c) >= 3]
bad = set(lg.nodes)
print(f"accounts {len(bank_of):,} | laundering-involved {len(bad):,} | clusters with >=3 accounts: {len(clusters)}")


def recovered(groups, clusters, cover=0.5):
    """A cluster is recovered if one detected group contains >= cover of its accounts."""
    idx = {}
    for gi, g in enumerate(groups):
        for a in g:
            idx[a] = gi
    n = 0
    for c in clusters:
        counts = pd.Series([idx[a] for a in c if a in idx]).value_counts()
        if len(counts) and counts.iloc[0] / len(c) >= cover:
            n += 1
    return n


def groups_from(flagged, cross_bank_allowed):
    """Link flagged accounts by their transfers. Siloed: only edges where both ends are the same bank's customers."""
    sub = df[df["From Account"].isin(flagged) & df["To Account"].isin(flagged)]
    if not cross_bank_allowed:
        sub = sub[sub["From Bank"] == sub["To Bank"]]
    g = nx.Graph(); g.add_edges_from(zip(sub["From Account"], sub["To Account"]))
    return [set(c) for c in nx.connected_components(g) if len(c) >= 2]


def precision(groups):
    if not groups:
        return 0.0
    return float(np.mean([len(g & bad) / len(g) >= 0.5 for g in groups]))


# ---------- Part A: ceiling with perfect local flags ----------
silo_A = groups_from(bad, cross_bank_allowed=False)
collab_A = groups_from(bad, cross_bank_allowed=True)
A = {"siloed_clusters_recovered": recovered(silo_A, clusters),
     "collab_clusters_recovered": recovered(collab_A, clusters)}
print("A (perfect flags): siloed", A["siloed_clusters_recovered"], "| together", A["collab_clusters_recovered"], "of", len(clusters))

# ---------- Part B: realistic unsupervised flags ----------
out = df.groupby("From Account").agg(out_n=("Amount Paid", "size"), out_amt=("Amount Paid", "sum"),
                                     out_cp=("To Account", "nunique"),
                                     out_xbank=("To Bank", lambda s: 0))
inn = df.groupby("To Account").agg(in_n=("Amount Received", "size"), in_amt=("Amount Received", "sum"),
                                   in_cp=("From Account", "nunique"))
feat = out.join(inn, how="outer").fillna(0)
xb_out = (df["From Bank"] != df["To Bank"]).groupby(df["From Account"]).mean()
feat["xbank_out"] = xb_out.reindex(feat.index).fillna(0)
feat["flow_ratio"] = feat["out_amt"] / (feat["in_amt"] + 1)
feat["cp_per_tx"] = (feat["out_cp"] + feat["in_cp"]) / (feat["out_n"] + feat["in_n"] + 1)
# pass-through speed: hours from each outflow back to the latest inflow of the same account
o = df[["From Account", "Timestamp"]].rename(columns={"From Account": "acct"}).sort_values("Timestamp")
i = df[["To Account", "Timestamp"]].rename(columns={"To Account": "acct", "Timestamp": "t_in"}).sort_values("t_in")
m = pd.merge_asof(o, i, left_on="Timestamp", right_on="t_in", by="acct", direction="backward")
m["hold_h"] = (m["Timestamp"] - m["t_in"]).dt.total_seconds() / 3600
feat["hold_med_h"] = m.groupby("acct")["hold_h"].median().reindex(feat.index).fillna(9999)
feat["active_days"] = df.groupby("From Account")["Timestamp"].agg(lambda s: s.dt.date.nunique()).reindex(feat.index).fillna(0)
feat["bank"] = [bank_of[a] for a in feat.index]
X_cols = ["out_n", "in_n", "out_cp", "in_cp", "xbank_out", "flow_ratio", "cp_per_tx", "hold_med_h", "active_days"]

results_B = {}
for rate in (0.03, 0.05, 0.10):
    flagged = set()
    for b, part in feat.groupby("bank"):  # each bank scores only its own customers
        X = np.log1p(part[X_cols].clip(lower=0))
        s = -IsolationForest(n_estimators=150, random_state=0).fit(X).score_samples(X)
        k = max(1, int(len(part) * rate))
        flagged |= set(part.index[np.argsort(-s)[:k]])
    hit = len(flagged & bad) / len(flagged)
    silo = groups_from(flagged, False)
    coll = groups_from(flagged, True)
    results_B[rate] = {"flagged": len(flagged), "flag_precision": round(hit, 3),
                       "laundering_accounts_flagged": round(len(flagged & bad) / len(bad), 3),
                       "siloed_recovered": recovered(silo, clusters), "collab_recovered": recovered(coll, clusters),
                       "siloed_groups": len(silo), "collab_groups": len(coll),
                       "collab_group_precision": round(precision(coll), 3)}
    print(f"B flag top {rate:.0%}/bank:", results_B[rate])

Path("/home/claude/ring-breaker/transxion_results.json").write_text(json.dumps(
    {"clusters_ge3": len(clusters), "A_perfect_flags": A, "B_unsupervised": results_B}, indent=2))
