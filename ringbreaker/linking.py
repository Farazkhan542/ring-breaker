"""Plain linking baselines (ported from experiments/go_no_go.py) and ring scoring.

Siloed: a bank links only its own flagged customers.
Collaborative baseline: banks share masked IDs of flagged customers plus their large transfers (masked IDs only);
the consortium links accounts that both ends' own banks flagged independently.
"""
import networkx as nx

from .config import LARGE
from .data import BankView
from .masking import mask


def siloed_groups(view: BankView, flags: dict) -> list[set]:
    own = set(flags)
    big = view.tx[view.tx["Amount"] >= LARGE]
    g = nx.Graph()
    for s, t in zip(big["From Account"], big["To Account"]):
        if s in own and t in own:
            g.add_edge(s, t)
    return [set(c) for c in nx.connected_components(g) if len(c) >= 3]


def collaborative_groups(views: dict[str, BankView], flags: dict[str, dict]):
    """Returns (groups as sets of real IDs for scoring, sharing stats). Real IDs are resolved only for scoring."""
    shared_ids = {mask(a): (b, a) for b in views for a in flags[b]}
    edges = []
    for b, view in views.items():
        own = set(flags[b])
        big = view.tx[view.tx["Amount"] >= LARGE]
        for fb, fa, ta in zip(big["From Bank"], big["From Account"], big["To Account"]):
            mine = fa if fb == b else ta
            if mine in own:
                edges.append((mask(fa), mask(ta), b))
    g = nx.Graph()
    for s, t, _ in edges:
        if s in shared_ids and t in shared_ids:
            g.add_edge(s, t)
    comps = [c for c in nx.connected_components(g) if len(c) >= 3 and len({shared_ids[m][0] for m in c}) >= 2]
    groups = [{shared_ids[m][1] for m in c} for c in comps]
    return groups, {"masked_accounts_shared": len(shared_ids), "transfer_records_shared": len(edges)}


def score(groups: list[set], rings: list, strict: bool = True, cover: float = 0.5) -> dict:
    """A ring is recovered if one group holds >= cover of its accounts. Strict mode also requires that ring to make
    up >= 50% of that group, so one giant blob cannot take credit for every ring inside it."""
    found, false_alarms = set(), 0
    for g in groups:
        hit = False
        for r in rings:
            members = set(r["accounts"])
            overlap = len(g & members)
            if overlap / len(members) >= cover and (not strict or overlap / len(g) >= 0.5):
                found.add(r["ring_id"])
                hit = True
        if not hit and not any(len(g & set(r["accounts"])) / len(g) >= 0.5 for r in rings):
            false_alarms += 1
    return {"rings_found": sorted(found), "n_found": len(found), "false_alarm_groups": false_alarms,
            "groups": len(groups)}
