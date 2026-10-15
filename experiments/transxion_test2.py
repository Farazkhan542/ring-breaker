# Part C: supervised flags without leakage. Model trained on banks in one half, scores the other half (and vice versa),
# mimicking "a model trained on other institutions' past cases". Hubs removed when linking to avoid one giant blob.
import runpy, numpy as np, networkx as nx, json
from sklearn.ensemble import HistGradientBoostingClassifier
ns = runpy.run_path("transxion_test.py", run_name="not_main")  # reuses feat, df, clusters, helpers (prints again)
feat, bad, clusters, df = ns["feat"], ns["bad"], ns["clusters"], ns["df"]
recovered, precision, X_cols = ns["recovered"], ns["precision"], ns["X_cols"]
feat["y"] = feat.index.isin(bad).astype(int)
banks = sorted(feat["bank"].unique()); half = set(banks[::2])
score = np.zeros(len(feat))
for train_banks in (half, set(banks) - half):
    tr = feat["bank"].isin(train_banks).values
    clf = HistGradientBoostingClassifier(max_iter=200, random_state=0).fit(np.log1p(feat.loc[tr, X_cols].clip(lower=0)), feat.loc[tr, "y"])
    score[~tr] = clf.predict_proba(np.log1p(feat.loc[~tr, X_cols].clip(lower=0)))[:, 1]
feat["score"] = score
def link(flagged, cross):
    sub = df[df["From Account"].isin(flagged) & df["To Account"].isin(flagged)]
    if not cross: sub = sub[sub["From Bank"] == sub["To Bank"]]
    g = nx.Graph(); g.add_edges_from(zip(sub["From Account"], sub["To Account"]))
    g.remove_nodes_from([n for n, d in dict(g.degree()).items() if d > 25])  # drop hubs
    return [set(c) for c in nx.connected_components(g) if len(c) >= 2]
out = {}
for rate in (0.05, 0.10, 0.15):
    flagged = set()
    for b, part in feat.groupby("bank"):
        k = int(len(part) * rate); flagged |= set(part.sort_values("score", ascending=False).index[:k])
    s, c = link(flagged, False), link(flagged, True)
    out[rate] = {"flag_precision": round(len(flagged & bad)/len(flagged), 3), "laundering_accounts_flagged": round(len(flagged & bad)/len(bad), 3),
                 "siloed_recovered": recovered(s, clusters), "collab_recovered": recovered(c, clusters),
                 "collab_groups": len(c), "collab_group_precision": round(precision(c), 3)}
    print(f"C supervised top {rate:.0%}/bank:", out[rate])
json.dump(out, open("transxion_results_supervised.json", "w"), indent=2)
