"""IBM AMLworld HI-Small (adapted from transxion_rescore.py): alone vs together vs agent cases, scored against the
370 labelled laundering rings in HI-Small_Patterns.txt.

    python experiments/ibm_eval.py <folder with HI-Small files>   -> results/ibm_hi_small.json

Original description of the TransXion script follows.
Re-score TransXion (30 banks, ~3M transactions) with the strict rule, and add agent-style investigations.

Strict rule: a laundering cluster (>=3 accounts) is recovered only if one group holds >=50% of the cluster's accounts
AND the cluster makes up >=50% of that group. Flags are reproduced from transxion_test.py / transxion_test2.py.

Agent-style investigation (mirrors ringbreaker.investigation with the rule-based planner): one case per flagged
account; follow transfers only to accounts their own bank also flagged, at most 3 hops and 20 cross-bank questions;
each case's result is one group.

    python experiments/transxion_rescore.py <path/to/tx.csv>   -> results/transxion.json
"""
import json
import sys
import time
from collections import deque
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

t0 = time.time()
DATA = Path(sys.argv[1])  # folder with HI-Small_Trans.csv and HI-Small_Patterns.txt
df = pd.read_csv(DATA / "HI-Small_Trans.csv", dtype={"From Bank": str, "To Bank": str, "Account": str, "Account.1": str})
df["Timestamp"] = pd.to_datetime(df["Timestamp"], format="%Y/%m/%d %H:%M")
# an account is identified by bank + account number
df["From Account"] = df["From Bank"] + ":" + df["Account"]
df["To Account"] = df["To Bank"] + ":" + df["Account.1"]
df = df[df["From Account"] != df["To Account"]]
bank_of = dict(zip(df["From Account"], df["From Bank"]))
bank_of.update(zip(df["To Account"], df["To Bank"]))
clusters, cur, ring_type = [], None, []
for line in open(DATA / "HI-Small_Patterns.txt"):
    line = line.strip()
    if line.startswith("BEGIN"):
        cur, kind = set(), line.split(" - ")[1].split(":")[0]
    elif line.startswith("END"):
        if len(cur) >= 3:
            clusters.append(cur); ring_type.append(kind)
        cur = None
    elif line and cur is not None:
        p = line.split(",")
        cur.update({f"{p[1]}:{p[2]}", f"{p[3]}:{p[4]}"})
bad = set(df.loc[df["Is Laundering"] == 1, "From Account"]) | set(df.loc[df["Is Laundering"] == 1, "To Account"])
cluster_of = {}
for i, c in enumerate(clusters):
    for a in c:
        cluster_of.setdefault(a, i)
print(f"loaded {len(df):,} tx, {len(bank_of):,} accounts, {df['From Bank'].nunique():,} banks in {time.time() - t0:.0f}s; "
      f"labelled rings>=3 accounts: {len(clusters)}", flush=True)


def recovered(groups, strict=True):
    found, good = set(), 0
    for g in groups:
        counts = pd.Series([cluster_of[a] for a in g if a in cluster_of]).value_counts()
        for ci, n in counts.items():
            if n / len(clusters[ci]) >= 0.5 and (not strict or n / len(g) >= 0.5):
                found.add(ci)
        good += len(g & bad) / len(g) >= 0.5
    return len(found), (round(good / len(groups), 3) if groups else 0.0)


# ---------- features (identical to transxion_test.py) ----------
out = df.groupby("From Account").agg(out_n=("Amount Paid", "size"), out_amt=("Amount Paid", "sum"),
                                     out_cp=("To Account", "nunique"))
inn = df.groupby("To Account").agg(in_n=("Amount Received", "size"), in_amt=("Amount Received", "sum"),
                                   in_cp=("From Account", "nunique"))
feat = out.join(inn, how="outer").fillna(0)
feat["xbank_out"] = (df["From Bank"] != df["To Bank"]).groupby(df["From Account"]).mean().reindex(feat.index).fillna(0)
feat["flow_ratio"] = feat["out_amt"] / (feat["in_amt"] + 1)
feat["cp_per_tx"] = (feat["out_cp"] + feat["in_cp"]) / (feat["out_n"] + feat["in_n"] + 1)
o = df[["From Account", "Timestamp"]].rename(columns={"From Account": "acct"}).sort_values("Timestamp")
i = df[["To Account", "Timestamp"]].rename(columns={"To Account": "acct", "Timestamp": "t_in"}).sort_values("t_in")
m = pd.merge_asof(o, i, left_on="Timestamp", right_on="t_in", by="acct", direction="backward")
m["hold_h"] = (m["Timestamp"] - m["t_in"]).dt.total_seconds() / 3600
feat["hold_med_h"] = m.groupby("acct")["hold_h"].median().reindex(feat.index).fillna(9999)
feat["active_days"] = df.groupby("From Account")["Timestamp"].agg(lambda s: s.dt.date.nunique()).reindex(feat.index).fillna(0)
feat["bank"] = [bank_of[a] for a in feat.index]
X_cols = ["out_n", "in_n", "out_cp", "in_cp", "xbank_out", "flow_ratio", "cp_per_tx", "hold_med_h", "active_days"]
feat["y"] = feat.index.isin(bad).astype(int)
print(f"features in {time.time() - t0:.0f}s", flush=True)

# supervised score: model trained on the other half of banks (no leakage)
banks = sorted(feat["bank"].unique()); half = set(banks[::2])
score = np.zeros(len(feat))
for train in (half, set(banks) - half):
    tr = feat["bank"].isin(train).values
    clf = HistGradientBoostingClassifier(max_iter=200, random_state=0).fit(
        np.log1p(feat.loc[tr, X_cols].clip(lower=0)), feat.loc[tr, "y"])
    score[~tr] = clf.predict_proba(np.log1p(feat.loc[~tr, X_cols].clip(lower=0)))[:, 1]
feat["sup"] = score


def flag(col, rate):
    """Every bank applies the same consortium-agreed score threshold to its own customers (most of the 30k banks
    are too small for a per-bank top-k)."""
    return set(feat.index[feat[col] >= feat[col].quantile(1 - rate)])


TRUE_PAIRS = sum(len(c) * (len(c) - 1) // 2 for c in clusters)


def pair_scores(groups, overlapping=False):
    """Pairwise clustering scores over laundering-cluster accounts: recall = share of same-cluster account pairs that
    end up in one group; precision = share of grouped pairs that really are in the same cluster."""
    if overlapping:  # agent cases can overlap: count distinct pairs
        pred, tp = set(), 0
        for g in groups:
            m = sorted(g)
            pred.update((a, b) for i, a in enumerate(m) for b in m[i + 1:])
        tp = sum(1 for a, b in pred if a in cluster_of and cluster_of.get(b) == cluster_of[a])
        n_pred = len(pred)
    else:
        n_pred = sum(len(g) * (len(g) - 1) // 2 for g in groups)
        tp = 0
        for g in groups:
            for n in pd.Series([cluster_of[a] for a in g if a in cluster_of]).value_counts():
                tp += n * (n - 1) // 2
    return round(tp / TRUE_PAIRS, 4), (round(tp / n_pred, 3) if n_pred else 0.0)


def link_graph(flagged, cross, drop_hubs):
    sub = df[df["From Account"].isin(flagged) & df["To Account"].isin(flagged)]
    if not cross:
        sub = sub[sub["From Bank"] == sub["To Bank"]]
    g = nx.Graph(); g.add_edges_from(zip(sub["From Account"], sub["To Account"]))
    if drop_hubs:
        g.remove_nodes_from([n for n, d in dict(g.degree()).items() if d > 25])
    return g


def components(g):
    return [set(c) for c in nx.connected_components(g) if len(c) >= 2]


def investigations(g, flagged, max_hops=3, max_questions=20):
    """One case per flagged account in g. Neighbours at the same bank are checked locally (free); each neighbour at
    another bank costs one question. Only accounts their own bank flagged join the case (they are all in g)."""
    groups = set()
    for seed in g.nodes:
        case, q, seen = {seed}, 0, {seed}
        dq = deque([(seed, 0)])
        while dq and q < max_questions:
            a, h = dq.popleft()
            if h >= max_hops:
                continue
            for n in g.neighbors(a):
                if n in seen:
                    continue
                if bank_of[n] != bank_of[seed]:
                    q += 1
                    if q > max_questions:
                        break
                seen.add(n); case.add(n); dq.append((n, h + 1))
        if len(case) >= 3 and len({bank_of[a] for a in case}) >= 2:
            groups.add(frozenset(case))
    return [set(c) for c in groups]


rows = []
for name, col, rate in [("Perfect local flags (ceiling)", None, None), ("Risk model, top 1% flagged", "sup", 0.01),
                        ("Risk model, top 2% flagged", "sup", 0.02), ("Risk model, top 5% flagged", "sup", 0.05)]:
    flagged = bad if col is None else flag(col, rate)
    alone_groups = components(link_graph(flagged, cross=False, drop_hubs=True))
    g = link_graph(flagged, cross=True, drop_hubs=True)
    plain = components(g)
    cases = investigations(g, flagged)
    a_s, _ = recovered(alone_groups); p_s, p_prec = recovered(plain); p_l, _ = recovered(plain, strict=False)
    c_s, c_prec = recovered(cases)
    a_pr, a_pp = pair_scores(alone_groups); p_pr, p_pp = pair_scores(plain); c_pr, c_pp = pair_scores(cases, True)
    row = {"flags": name, "flag_precision": round(len(flagged & bad) / len(flagged), 2),
           "alone": a_s, "plain_strict": p_s, "plain_loose": p_l, "plain_groups": len(plain),
           "agents_strict": c_s, "agent_cases": len(cases), "agent_case_precision": c_prec,
           "shared_accounts_pct": round(100 * len(flagged) / len(feat), 2),
           "alone_pair_recall": a_pr, "alone_pair_precision": a_pp, "plain_pair_recall": p_pr,
           "plain_pair_precision": p_pp, "agents_pair_recall": c_pr, "agents_pair_precision": c_pp}
    rows.append(row)
    print(row, f"t={time.time() - t0:.0f}s", flush=True)

out_path = Path(__file__).resolve().parent.parent / "results" / "ibm_hi_small.json"
out_path.write_text(json.dumps({"clusters_ge3": len(clusters), "dataset": "IBM AMLworld HI-Small", "rows": rows}, indent=2), newline="\n")
print("wrote", out_path)
