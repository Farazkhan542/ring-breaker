"""Objective, COSMIC-style red-flag indicators, computed by a bank for its OWN customers from its OWN view only.

Ported from experiments/go_no_go.py; logic and thresholds unchanged.
"""
import pandas as pd

from .config import LARGE
from .data import BankView

H72 = pd.Timedelta(hours=72)
H48 = pd.Timedelta(hours=48)

INDICATOR_HELP = {
    "rapid pass-through": "70%+ of large incoming money (5k+ total) was sent on as large transfers within 72 hours",
    "rapid fan-in": "large transfers from 3+ different senders, mostly at other banks, within 72 hours",
    "rapid fan-out": "large transfers to 3+ different receivers within 48 hours",
    "new account": "account opened less than 90 days before the period",
    "amounts just under 10k": "2+ large transfers between 8,000 and 9,999 (possible structuring below a reporting threshold)",
    "mostly cross-bank": "70%+ of large transfers go to or come from other banks",
}
BEHAVIOUR = {"rapid pass-through", "rapid fan-in", "rapid fan-out"}


def indicators_for(view: BankView, account: str, inc: pd.DataFrame, out: pd.DataFrame) -> list[str]:
    """Indicators for one own account, given its incoming and outgoing transactions in this bank's view."""
    bank = view.bank
    li, lo = inc[inc["Amount"] >= LARGE], out[out["Amount"] >= LARGE]
    found = []
    if len(li) and len(lo):
        fwd = 0.0
        for t, amt in zip(li["Timestamp"], li["Amount"]):
            w = lo[(lo["Timestamp"] > t) & (lo["Timestamp"] <= t + H72)]["Amount"].sum()
            fwd += min(w, amt)
        if li["Amount"].sum() >= 5000 and fwd / li["Amount"].sum() >= 0.7:
            found.append("rapid pass-through")
    if len(li) >= 3:
        s = li.sort_values("Timestamp")
        for t in s["Timestamp"]:
            w = s[(s["Timestamp"] >= t) & (s["Timestamp"] <= t + H72)]
            if w["From Account"].nunique() >= 3 and (w["From Bank"] != bank).mean() >= 0.5:
                found.append("rapid fan-in")
                break
    if len(lo) >= 3:
        s = lo.sort_values("Timestamp")
        for t in s["Timestamp"]:
            w = s[(s["Timestamp"] >= t) & (s["Timestamp"] <= t + H48)]
            if w["To Account"].nunique() >= 3:
                found.append("rapid fan-out")
                break
    if not found:
        return []
    if (view.start - pd.Timestamp(view.accounts.loc[account, "opened"])).days < 90:
        found.append("new account")
    big = pd.concat([li, lo])
    if ((big["Amount"] >= 8000) & (big["Amount"] < 10000)).sum() >= 2:
        found.append("amounts just under 10k")
    if len(big) and (big["From Bank"] != big["To Bank"]).mean() >= 0.7:
        found.append("mostly cross-bank")
    return found


def compute_flags(view: BankView) -> dict[str, list[str]]:
    """All own customers with a behaviour indicator plus at least one other indicator."""
    tx = view.tx
    inc = dict(tuple(tx[tx["To Bank"] == view.bank].groupby("To Account")))
    out = dict(tuple(tx[tx["From Bank"] == view.bank].groupby("From Account")))
    empty = tx.iloc[0:0]
    flags = {}
    # Only accounts with a large transfer can show a behaviour indicator; skip the rest for speed.
    large = tx[tx["Amount"] >= LARGE]
    candidates = (set(large["To Account"]) | set(large["From Account"])) & set(view.accounts.index)
    for a in sorted(candidates):
        ind = indicators_for(view, a, inc.get(a, empty), out.get(a, empty))
        if len(ind) >= 2:
            flags[a] = ind
    return flags
