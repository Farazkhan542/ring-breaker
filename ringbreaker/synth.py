"""Synthetic three-bank world with planted cross-bank laundering rings (refactored from experiments/generate_data.py).

Columns follow the IBM AML (AMLworld) layout: Timestamp, From Bank, From Account, To Bank, To Account, Amount,
Currency, Payment Format, Is Laundering, Ring ID. Output for a given seed is identical to the original script.
"""
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


def generate(seed: int = 42):
    """Return (transactions, accounts, rings) for one random world."""
    rng = random.Random(seed)
    nrng = np.random.RandomState(seed)
    BANKS = ["BANK_A", "BANK_B", "BANK_C"]
    ACCOUNTS_PER_BANK = 2000
    START = datetime(2026, 7, 1)
    DAYS = 60
    END = START + timedelta(days=DAYS)

    # ---------------- accounts ----------------
    accounts = []  # dicts: id, bank, opened, kind
    for b in BANKS:
        for i in range(ACCOUNTS_PER_BANK):
            age_days = int(nrng.choice([rng.randint(400, 4000), rng.randint(1, 120)], p=[0.93, 0.07]))
            accounts.append({"id": f"{b[-1]}-{i:05d}", "bank": b,
                             "opened": (START - timedelta(days=age_days) + timedelta(days=0)).date().isoformat(),
                             "kind": "person"})
    acc_by_id = {a["id"]: a for a in accounts}
    people = [a["id"] for a in accounts]

    # employers and merchants (legit high fan-out / fan-in noise)
    employers = rng.sample(people, 30)
    merchants = rng.sample([p for p in people if p not in employers], 120)
    for e in employers: acc_by_id[e]["kind"] = "employer"
    for m in merchants: acc_by_id[m]["kind"] = "merchant"
    persons = [p for p in people if acc_by_id[p]["kind"] == "person"]

    rows = []
    def add(ts, src, dst, amount, fmt, laundering=0, ring=""):
        rows.append({"Timestamp": ts.strftime("%Y-%m-%d %H:%M"),
                     "From Bank": acc_by_id[src]["bank"], "From Account": src,
                     "To Bank": acc_by_id[dst]["bank"], "To Account": dst,
                     "Amount": round(float(amount), 2), "Currency": "USD",
                     "Payment Format": fmt, "Is Laundering": laundering, "Ring ID": ring})

    # ---------------- normal traffic ----------------
    # salaries: twice in period
    salaried = rng.sample(persons, int(len(persons) * 0.6))
    employer_of = {p: rng.choice(employers) for p in salaried}
    for month_day in (0, 30):
        for p in salaried:
            ts = START + timedelta(days=month_day + rng.uniform(0, 2), hours=rng.uniform(9, 12))
            add(ts, employer_of[p], p, nrng.lognormal(7.6, 0.4), "ACH")

    # merchant payments (many small payments into merchants -> legit fan-in)
    for _ in range(30000):
        p = rng.choice(persons)
        m = rng.choice(merchants)
        add(START + timedelta(days=rng.uniform(0, DAYS)), p, m, nrng.lognormal(3.6, 0.9), "Card")

    # person-to-person transfers, ~35% cross-bank
    for _ in range(15000):
        p = rng.choice(persons)
        if rng.random() < 0.35:
            q = rng.choice([x for x in rng.sample(persons, 8) if acc_by_id[x]["bank"] != acc_by_id[p]["bank"]] or persons)
        else:
            q = rng.choice([x for x in rng.sample(persons, 8) if acc_by_id[x]["bank"] == acc_by_id[p]["bank"]] or persons)
        if q != p:
            add(START + timedelta(days=rng.uniform(0, DAYS)), p, q, nrng.lognormal(5.0, 1.0), "Wire")

    # legit pass-through noise: remittance-style forwarding (receive pay, forward most to family elsewhere)
    remitters = rng.sample([p for p in salaried], 60)
    for r in remitters:
        fam = rng.choice([x for x in persons if acc_by_id[x]["bank"] != acc_by_id[r]["bank"]])
        for month_day in (1, 31):
            ts = START + timedelta(days=month_day + rng.uniform(0.5, 2.5))
            add(ts, r, fam, nrng.lognormal(7.3, 0.3), "Wire")

    # ---------------- laundering rings ----------------
    used = set(employers) | set(merchants) | set(remitters)

    def pick_mule(bank, new_prob=0.6):
        """Pick an unused account at `bank`; with probability new_prob make it a recently opened account."""
        while True:
            cand = rng.choice([p for p in persons if acc_by_id[p]["bank"] == bank])
            if cand in used:
                continue
            used.add(cand)
            if rng.random() < new_prob:
                acc_by_id[cand]["opened"] = (START - timedelta(days=rng.randint(5, 80))).date().isoformat()
            return cand

    def under_threshold():
        return rng.uniform(8000, 9900)  # just below a 10k reporting threshold (structuring)

    rings = []
    ring_no = 0
    pattern_plan = ["cycle"] * 5 + ["scatter_gather"] * 5 + ["layering"] * 4
    rng.shuffle(pattern_plan)
    for pattern in pattern_plan:
        ring_no += 1
        rid = f"R{ring_no:02d}"
        t0 = START + timedelta(days=rng.uniform(3, DAYS - 12))
        members = []
        if pattern == "cycle":
            k = rng.randint(4, 6)
            banks = [BANKS[i % 3] for i in range(k)]
            rng.shuffle(banks)
            # make sure consecutive accounts are mostly at different banks
            members = [pick_mule(b) for b in banks]
            amt = under_threshold()
            for rep in range(rng.randint(2, 3)):
                ts = t0 + timedelta(days=rep * rng.uniform(3, 6))
                a = amt * rng.uniform(0.95, 1.0)
                for i in range(k):
                    src, dst = members[i], members[(i + 1) % k]
                    ts += timedelta(hours=rng.uniform(3, 30))
                    add(ts, src, dst, a, "Wire", 1, rid)
                    a *= rng.uniform(0.96, 0.99)
        elif pattern == "scatter_gather":
            src = pick_mule(rng.choice(BANKS), 0.2)
            collector = pick_mule(rng.choice(BANKS), 0.5)
            n = rng.randint(4, 6)
            mules = [pick_mule(BANKS[i % 3]) for i in range(n)]
            members = [src] + mules + [collector]
            # source must have funds: an incoming "business payment"
            add(t0 - timedelta(days=1), rng.choice(employers), src, n * 9500, "Wire", 1, rid)
            for m in mules:
                ts = t0 + timedelta(hours=rng.uniform(0, 24))
                a = under_threshold()
                add(ts, src, m, a, "Wire", 1, rid)
                add(ts + timedelta(hours=rng.uniform(4, 40)), m, collector, a * rng.uniform(0.9, 0.97), "Wire", 1, rid)
        else:  # layering chain
            k = rng.randint(4, 6)
            banks = [BANKS[(i + rng.randint(0, 2)) % 3] for i in range(k)]
            for i in range(1, k):
                if banks[i] == banks[i - 1]:
                    banks[i] = BANKS[(BANKS.index(banks[i]) + 1) % 3]
            members = [pick_mule(b) for b in banks]
            add(t0 - timedelta(days=1), rng.choice(employers), members[0], 30000, "Wire", 1, rid)
            ts = t0
            a = under_threshold() * 3
            for i in range(k - 1):
                ts += timedelta(hours=rng.uniform(6, 36))
                chunks = 3
                for c in range(chunks):
                    add(ts + timedelta(minutes=10 * c), members[i], members[i + 1], a / chunks * rng.uniform(0.97, 1.0), "Wire", 1, rid)
                a *= rng.uniform(0.95, 0.98)
        rings.append({"ring_id": rid, "pattern": pattern, "accounts": members,
                      "banks": sorted({acc_by_id[m]["bank"] for m in members})})

    tx = pd.DataFrame(rows).sort_values("Timestamp").reset_index(drop=True)
    acc = pd.DataFrame(list(acc_by_id.values()))
    return tx, acc, rings


def write(out_dir: Path, seed: int = 42) -> None:
    tx, acc, rings = generate(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    tx.to_csv(out_dir / "transactions.csv", index=False, lineterminator=chr(10))
    acc.to_csv(out_dir / "accounts.csv", index=False, lineterminator=chr(10))
    (out_dir / "ground_truth_rings.json").write_text(json.dumps(rings, indent=2), newline=chr(10))


if __name__ == "__main__":
    import sys
    write(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data"), int(sys.argv[2]) if len(sys.argv) > 2 else 42)
