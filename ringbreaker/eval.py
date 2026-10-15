"""Evaluation harness: alone vs together, reproducible with fixed seeds.

    python -m ringbreaker.eval            # synthetic worlds (seeds 42, 7, 123, 2026) -> results/metrics.json

For each world: each bank alone links only its own flagged customers; the plain-linking baseline links masked IDs
shared by all banks; the agent investigation opens one case per flagged customer and follows the money over the
policy-checked question protocol (in-process here; over A2A HTTP in the deployed app).
"""
import json
import time
from datetime import datetime, timezone

from . import config
from .bank_agent import BankAgent
from .data import partition, world_from_frames
from .flags import compute_flags
from .investigation import run_local
from .linking import collaborative_groups, score, siloed_groups
from .policy import Policy
from .synth import generate

SEEDS = [42, 7, 123, 2026]


def run_world(seed: int) -> dict:
    tx, acc, rings = generate(seed)
    world = world_from_frames(tx, acc, rings)
    policy = Policy.load()
    views = {b: partition(world, b) for b in config.BANKS}
    flags = {b: compute_flags(views[b]) for b in config.BANKS}
    ring_accounts = {a for r in rings for a in r["accounts"]}
    flagged = {a for b in flags for a in flags[b]}

    alone = set()
    for b in config.BANKS:
        alone |= set(score(siloed_groups(views[b], flags[b]), rings)["rings_found"])

    groups, sharing = collaborative_groups(views, flags)
    base_strict, base_loose = score(groups, rings, strict=True), score(groups, rings, strict=False, cover=0.6)

    agents = {b: BankAgent(views[b], policy, flags[b]) for b in config.BANKS}
    t0, cases, queries = time.time(), set(), 0
    for b in config.BANKS:
        for a in flags[b]:
            res = run_local(agents, b, a, policy)
            queries += res["queries"]
            masked_to_real = {}
            for bb in config.BANKS:
                for m in (n["id"] for n in res["ring"]):
                    real = agents[bb].resolve_own(m)  # resolved only for scoring against ground truth
                    if real:
                        masked_to_real[m] = real
            group = frozenset(masked_to_real[n["id"]] for n in res["ring"])
            if len(group) >= 3 and len({n["bank"] for n in res["ring"]}) >= 2:
                cases.add(group)
    n_cases = sum(len(flags[b]) for b in config.BANKS)
    agent = score([set(g) for g in cases], rings, strict=True)

    return {
        "seed": seed, "rings": len(rings), "transactions": len(tx), "accounts": len(acc),
        "flagged": len(flagged), "flag_precision": round(len(flagged & ring_accounts) / max(len(flagged), 1), 3),
        "flag_recall": round(len(flagged & ring_accounts) / len(ring_accounts), 3),
        "alone": len(alone),
        "baseline_strict": base_strict["n_found"], "baseline_strict_false_alarms": base_strict["false_alarm_groups"],
        "baseline_loose": base_loose["n_found"], "baseline_groups": base_strict["groups"],
        "agents_strict": agent["n_found"], "agents_false_alarms": agent["false_alarm_groups"],
        "agent_case_groups": agent["groups"],
        "masked_accounts_shared_pct": round(100 * sharing["masked_accounts_shared"] / len(acc), 2),
        "records_shared_pct": round(100 * sharing["transfer_records_shared"] / len(tx), 2),
        "avg_questions_per_case": round(queries / max(n_cases, 1), 1),
        "avg_case_ms": round(1000 * (time.time() - t0) / max(n_cases, 1), 1),
    }


TRANSXION_PREVIOUS = [  # experiments/transxion_results*.json, loose rule (any group with >=50% of the cluster)
    {"flags": "Perfect local flags (ceiling)", "precision": "1.00", "alone": 22, "together": 369, "groups": "-",
     "group_precision": "-"},
    {"flags": "Supervised, top 5% per bank", "precision": "0.90", "alone": 2, "together": 32, "groups": 1,
     "group_precision": "1.00"},
    {"flags": "Supervised, top 10% per bank", "precision": "0.65", "alone": 5, "together": 17, "groups": 56,
     "group_precision": "0.75"},
    {"flags": "Supervised, top 15% per bank", "precision": "0.49", "alone": 8, "together": 16, "groups": 105,
     "group_precision": "0.50"},
]


def main():
    rows = [run_world(s) for s in SEEDS]
    for r in rows:
        print(r)
    num = lambda k, label, help="": {"key": k, "label": label, "num": True, "help": help}
    metrics = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "caveat": "Synthetic worlds are easier than real data, and the red-flag rules were tuned once on seed 42.",
        "sections": [
            {"title": "Synthetic three-bank worlds (14 planted rings each)",
             "note": "Rings found under the strict rule. 'Alone' is the best any single bank can do by linking its own "
                     "flagged customers. 'Plain linking' joins all shared masked IDs into groups. 'Agents' opens one "
                     "case per flagged customer and follows the money with policy-checked questions.",
             "columns": [num("seed", "Seed"), num("alone", "Alone", "Rings any single bank finds by itself"),
                         num("baseline_strict", "Plain linking", "Rings found by linking all shared masked IDs"),
                         num("agents_strict", "Agents", "Rings found by the agents' case-by-case investigations"),
                         num("agents_false_alarms", "Agent false alarms", "Case groups that are mostly innocent accounts"),
                         num("flag_precision", "Flag precision", "Share of flagged customers that are ring members"),
                         num("records_shared_pct", "% transactions shared", "Transfer records shared as masked IDs, bands and windows"),
                         num("avg_questions_per_case", "Questions per case")],
             "rows": rows},
            {"title": "TransXion benchmark (30 banks, 3 million transactions): earlier experiment",
             "note": "From our go/no-go experiment, scored with the earlier, looser rule. These numbers are being "
                     "re-scored with the strict rule; the 5% row is one giant group and should not be quoted.",
             "columns": [{"key": "flags", "label": "Local flags"},
                         num("precision", "Flag precision"), num("alone", "Alone", "Clusters any single bank connects"),
                         num("together", "Together", "Clusters connected with shared masked IDs"),
                         num("groups", "Groups"), num("group_precision", "Group precision")],
             "rows": TRANSXION_PREVIOUS},
        ],
    }
    out = config.ROOT / "results"
    out.mkdir(exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), newline="\n")
    print("wrote", out / "metrics.json")


if __name__ == "__main__":
    main()
