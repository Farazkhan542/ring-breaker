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


def transxion_section() -> dict:
    num = lambda k, label, help="": {"key": k, "label": label, "num": True, "help": help}
    path = config.ROOT / "results" / "transxion.json"
    if not path.exists():
        return {"title": "TransXion benchmark (30 banks, 3 million transactions): earlier experiment",
                "note": "Scored with the earlier, looser rule; being re-scored. The 5% row is one giant group.",
                "columns": [{"key": "flags", "label": "Local flags"}, num("precision", "Flag precision"),
                            num("alone", "Alone"), num("together", "Together"), num("groups", "Groups"),
                            num("group_precision", "Group precision")],
                "rows": TRANSXION_PREVIOUS}
    d = json.loads(path.read_text())
    return {"title": f"TransXion benchmark (30 banks, 3 million transactions, {d['clusters_ge3']} laundering clusters)",
            "note": "A hard result, reported as measured. Under the strict rule almost no clusters are recovered by any "
                    "method, even with perfect flags: in TransXion, laundering accounts of different rings also trade "
                    "with each other normally, so linking flagged accounts through all their transfers merges rings. "
                    "Our earlier '369 of 369' and '32 vs 2' figures came from a loose rule that credited giant mixed "
                    "groups (last column). Pair scores: recall = share of same-ring account pairs linked; precision = "
                    "share of linked pairs truly in the same ring. Next step: link through suspicious transfers, not "
                    "just suspicious accounts. Reproduce with experiments/transxion_rescore.py.",
            "columns": [{"key": "flags", "label": "Local flags"},
                        num("flag_precision", "Flag precision", "Share of flagged accounts involved in laundering"),
                        num("alone", "Alone", "Clusters recovered (strict) by banks linking only their own customers"),
                        num("plain_strict", "Together", "Clusters recovered (strict) by linking shared masked IDs"),
                        num("agents_strict", "Agent cases", "Clusters recovered (strict) by case-by-case investigations"),
                        num("alone_pair_recall", "Pair recall alone"),
                        num("plain_pair_recall", "Pair recall together"),
                        num("plain_pair_precision", "Pair precision together"),
                        num("plain_loose", "Together, old loose rule", "Our earlier rule, for comparison only")],
            "rows": d["rows"]}


def ibm_section() -> dict | None:
    path = config.ROOT / "results" / "ibm_hi_small.json"
    if not path.exists():
        return None
    d = json.loads(path.read_text())
    num = lambda k, label, help="": {"key": k, "label": label, "num": True, "help": help}
    return {"title": f"IBM AMLworld HI-Small (5 million transactions, 30,470 banks, {d['clusters_ge3']} labelled "
                     "laundering rings)",
            "note": "Public benchmark from IBM Research (NeurIPS 2023). Ground truth is IBM's list of laundering "
                    "attempts (cycle, scatter-gather, stack, fan-in/out, bipartite, random); 366 of 370 span two or more "
                    "banks. Strict rule. Every bank applies the same risk-model threshold, trained on the other half of "
                    "the banks (no leakage). Agent cases follow money from each flagged account, at most 3 hops and 20 "
                    "questions. Reproduce with experiments/ibm_eval.py.",
            "columns": [{"key": "flags", "label": "Local flags"},
                        num("flag_precision", "Flag precision", "Share of flagged accounts involved in laundering"),
                        num("alone", "Alone", "Rings recovered by banks linking only their own customers"),
                        num("plain_strict", "Together", "Rings recovered by linking shared masked IDs"),
                        num("agents_strict", "Agent cases", "Rings recovered by case-by-case investigations"),
                        num("agent_case_precision", "Case precision", "Share of agent cases that are mostly laundering"),
                        num("alone_pair_recall", "Pair recall alone"), num("plain_pair_recall", "Pair recall together"),
                        num("agents_pair_recall", "Pair recall agents"),
                        num("agents_pair_precision", "Pair precision agents")],
            "rows": d["rows"]}


def planner_section() -> dict | None:
    path = config.ROOT / "results" / "planner.json"
    if not path.exists():
        return None
    d = json.loads(path.read_text())
    num = lambda k, label, help="": {"key": k, "label": label, "num": True, "help": help}
    return {"title": "Gemini planner vs rule-based order (synthetic, seed 42)",
            "note": f"Same {d['rows'][0]['cases']} starting customers. The planner decides which cross-bank leads to "
                    f"follow and which to drop ({d['planner_calls_live']} of {d['planner_calls']} planner calls "
                    "answered live by Gemini). Fewer questions means less data leaves each bank. Reproduce with "
                    "python -m ringbreaker.eval_planner (results vary slightly between runs).",
            "columns": [{"key": "method", "label": "Method"},
                        num("coverage", "Ring coverage", "Share of the main ring the case found"),
                        num("wrong_members", "Wrong members per case", "Accounts in the case that are not in that ring"),
                        num("questions", "Cross-bank questions per case")],
            "rows": d["rows"]}


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
            *([planner_section()] if planner_section() else []),
            *([ibm_section()] if ibm_section() else []),
            transxion_section(),
        ],
    }
    out = config.ROOT / "results"
    out.mkdir(exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), newline="\n")
    print("wrote", out / "metrics.json")


if __name__ == "__main__":
    main()
