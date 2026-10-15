"""Gemini planner vs rule-based order on the same cases (seed-42 world, 20 random flagged starting customers).

    python -m ringbreaker.eval_planner   -> results/planner.json   (needs GOOGLE_API_KEY or Vertex AI)

Coverage = share of the main ring the case found; wrong members = case accounts not in that ring.
"""
import asyncio
import json
import logging
import random
from datetime import datetime, timezone

from . import config
from .bank_agent import BankAgent
from .data import load_world, partition
from .investigation import Investigation
from .masking import mask
from .planner import plan_next
from .policy import Policy


async def main(n_cases: int = 20):
    logging.disable(logging.WARNING)
    w, pol = load_world(), Policy.load()
    ag = {b: BankAgent(partition(w, b), pol) for b in config.BANKS}
    rid = {mask(a): r["ring_id"] for r in w.rings for a in r["accounts"]}
    size = {r["ring_id"]: len(r["accounts"]) for r in w.rings}
    seeds = [(b, a) for b in config.BANKS for a in ag[b].flags]
    random.Random(0).shuffle(seeds)

    async def ask(b, r):
        return ag[b].handle(r)

    rows, sources = {"Rule-based order": [], "Gemini planner": []}, []
    for b, a in seeds[:n_cases]:
        for name, pl in (("Rule-based order", None), ("Gemini planner", plan_next)):
            async def emit(e, n=name):
                if e["type"] == "plan" and n == "Gemini planner":
                    sources.append(e["source"])
            res = await Investigation(ag[b], a, ask, pol, emit, planner=pl, overreach_demo=False).run()
            ids = [rid.get(n["id"]) for n in res["ring"]]
            top = max(set(ids), key=ids.count) if ids else None
            cov = ids.count(top) / size[top] if top else 0.0
            rows[name].append((cov, sum(1 for x in ids if x != top) if ids else 0, res["queries"]))
    out = [{"method": k, "cases": len(v), "coverage": round(sum(x[0] for x in v) / len(v), 2),
            "wrong_members": round(sum(x[1] for x in v) / len(v), 2),
            "questions": round(sum(x[2] for x in v) / len(v), 1)} for k, v in rows.items()]
    live = sum(s == "live" for s in sources)
    doc = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "rows": out,
           "planner_calls": len(sources), "planner_calls_live": live, "models": config.PLANNER_MODELS}
    (config.ROOT / "results" / "planner.json").write_text(json.dumps(doc, indent=2), newline="\n")
    print(json.dumps(doc, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
