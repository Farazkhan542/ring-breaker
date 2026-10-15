"""Investigation planner (Gemini via ADK) and bank-side explainer (Gemma via ADK).

The planner decides which leads the lead bank's agent follows next and which it drops, with a reason shown to the
officer. Code validates every choice: the planner can only pick from real candidate leads, and the policy agent
still checks every question it causes.
"""
from . import config
from .flags import INDICATOR_HELP
from .llm import generate

BAND_PRIORITY = {"8k-10k": 0, "10k-20k": 1, "5k-8k": 2, "20k-50k": 3, "3k-5k": 4}

PLANNER_INSTRUCTION = """You are the investigation planner for one bank's anti-money-laundering agent in Ring Breaker.
The bank is following money across other banks to find a laundering ring. Other banks answer only narrow questions
about masked account IDs, and every question uses up a limited budget.
You receive JSON: what the case knows so far, and candidate leads (masked accounts at other banks linked to the case
by a large transfer, with amount band, 6-hour time window and direction).
Decide which leads to ask about NOW (at most `max_ask`), in priority order, and which to drop for good.
Prioritise transfers just under the 10k reporting threshold, transfers close in time to the case's other suspicious
transfers, and money forwarded onward quickly. Drop leads that look like ordinary activity (for example a single
incoming transfer from an account that looks like an employer or merchant, or transfers far outside the case's
time span). When unsure, keep a lead rather than drop it. Use ONLY lead IDs from the input.
Reply with JSON only: {"ask": [ids], "drop": [ids], "reason": "one or two plain-English sentences for the officer"}"""

EXPLAINER_INSTRUCTION = """You are a bank's own AML assistant, running inside the bank. In 2-3 plain-English
sentences, explain to the bank's investigator why this customer was flagged, using ONLY the indicators and their
definitions given. Do not invent amounts, dates or names. Say that the flag alone is not proof of wrongdoing."""


def heuristic_plan(candidates: list[dict], max_ask: int) -> dict:
    order = sorted(candidates, key=lambda c: (BAND_PRIORITY.get(c["amount_band"], 9), c["time_window"]))
    return {"ask": [c["masked_id"] for c in order[:max_ask]], "drop": [],
            "reason": "Following transfers closest to the 10k reporting threshold first."}


async def plan_next(case_known: list[dict], candidates: list[dict], max_ask: int, questions_left: int) -> dict:
    facts = {"case_so_far": case_known, "candidate_leads": candidates, "max_ask": max_ask,
             "questions_left": questions_left}
    res = await generate("planner", PLANNER_INSTRUCTION, facts, heuristic_plan(candidates, max_ask),
                         models=config.PLANNER_MODELS, json_mode=True, timeout=8, budget=12)
    plan, valid = res["data"] or {}, {c["masked_id"] for c in candidates}
    ask = [m for m in plan.get("ask", []) if m in valid][:max_ask]
    drop = [m for m in plan.get("drop", []) if m in valid and m not in ask]
    if not ask and not drop:  # unusable answer: fall back to the rule-based order
        return {**heuristic_plan(candidates, max_ask), "source": "fallback", "model": None}
    return {"ask": ask, "drop": drop, "reason": str(plan.get("reason", ""))[:400], "source": res["source"],
            "model": res["model"]}


def fallback_explanation(indicators: list[str]) -> str:
    parts = "; ".join(f"{i}: {INDICATOR_HELP.get(i, '')}" for i in indicators)
    return f"Flagged because of {len(indicators)} objective indicators ({parts}). A flag is a reason to look closer, not proof."


async def explain_flag(bank: str, indicators: list[str]) -> dict:
    facts = {"bank": bank, "indicators": [{"name": i, "definition": INDICATOR_HELP.get(i, "")} for i in indicators]}
    return await generate("bank_explainer", EXPLAINER_INSTRUCTION, facts, fallback_explanation(indicators),
                          models=config.BANK_MODELS, timeout=12, budget=20, cache_first=True)
