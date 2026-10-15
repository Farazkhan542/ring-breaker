"""Case builder / writer and skeptic agents. Code computes every number; Gemini writes and argues."""
import asyncio
from collections import Counter

from .llm import generate

WRITER_INSTRUCTION = """You are the case-writer agent in Ring Breaker, a consortium of bank AML investigator agents.
You receive JSON facts about one cross-bank case. Account IDs are masked pseudonyms; amounts are bands; times are
6-hour windows. Write a joint case file in the style of a suspicious transaction report, in Markdown, with these
sections: Summary, How the money moved, Evidence by bank, Red-flag indicators, Confidence, Recommended action.
Rules: use ONLY the facts given; never invent names, amounts, dates or accounts; copy numbers exactly as given;
say clearly that each bank's compliance officer must approve before anything is filed. Keep it under 300 words."""

SKEPTIC_INSTRUCTION = """You are the skeptic agent in Ring Breaker. Your job is to protect innocent customers.
You receive JSON facts about one cross-bank case. Argue the strongest INNOCENT explanation for this pattern (for
example payroll, family remittance, merchant settlement, a savings club or rotating credit group, business
treasury moves). Then list the specific evidence that would confirm or refute it, and say which facts in the case
are weakest. Use ONLY the facts given; do not invent data. Markdown, under 200 words, headings: Innocent explanation,
Evidence that would settle it, Weak points in the case."""


def case_facts(result: dict, blocked: int) -> dict:
    ring = result["ring"]
    ind_counts = Counter(i for n in ring for i in n["indicators"])
    by_bank = {}
    for n in ring:
        by_bank.setdefault(n["bank"], []).append({"masked_id": n["id"], "indicators": n["indicators"]})
    ids = {n["id"] for n in ring}
    out_deg = Counter(e["src"] for e in result["timeline"])
    in_deg = Counter(e["dst"] for e in result["timeline"])
    closed_loop = all(out_deg[m] and in_deg[m] for m in ids) and len(ids) >= 3
    bands = Counter(e["amount_band"] for e in result["timeline"])
    windows = [e["time_window"][:10] for e in result["timeline"]]
    return {
        "lead_bank": result["lead_bank"],
        "accounts_in_ring": len(ring), "banks_involved": result["banks"], "accounts_by_bank": by_bank,
        "transfers_linking_ring": len(result["timeline"]),
        "amount_bands": dict(bands), "first_day": min(windows) if windows else None,
        "last_day": max(windows) if windows else None,
        "money_returns_to_start": closed_loop,
        "indicator_counts": dict(ind_counts),
        "timeline": [{k: e[k] for k in ("src", "dst", "amount_band", "time_window")} for e in result["timeline"]],
        "cross_bank_questions_asked": result["queries"], "requests_blocked_by_policy": blocked,
    }


def confidence(f: dict) -> dict:
    """Transparent, rule-based score (0-100) with reasons. The LLM explains it but never computes it."""
    score, reasons = 0, []
    if len(f["banks_involved"]) >= 3:
        score += 25; reasons.append("ring spans 3 banks (+25)")
    elif len(f["banks_involved"]) == 2:
        score += 15; reasons.append("ring spans 2 banks (+15)")
    if f["money_returns_to_start"]:
        score += 25; reasons.append("money flows in a closed loop back to where it started (+25)")
    near = f["amount_bands"].get("8k-10k", 0)
    if f["transfers_linking_ring"] and near / f["transfers_linking_ring"] >= 0.5:
        score += 20; reasons.append("most transfers sit just under the 10k reporting threshold (+20)")
    if f["indicator_counts"].get("new account", 0) >= 2:
        score += 15; reasons.append(f"{f['indicator_counts']['new account']} members are new accounts (+15)")
    if f["indicator_counts"].get("rapid pass-through", 0) >= 2:
        score += 15; reasons.append("several members pass money on within 72 hours (+15)")
    return {"score": min(score, 100), "reasons": reasons}


def fallback_case_file(f: dict, conf: dict) -> str:
    banks = ", ".join(f["banks_involved"])
    lines = [
        f"## Summary\n{f['accounts_in_ring']} accounts at {len(f['banks_involved'])} banks ({banks}) are linked by "
        f"{f['transfers_linking_ring']} large transfers between {f['first_day']} and {f['last_day']}. "
        + ("The money returns to where it started, a classic laundering cycle." if f["money_returns_to_start"]
           else "The transfers form a connected chain across banks."),
        "## How the money moved\n" + "\n".join(
            f"- {e['time_window']}: {e['src']} → {e['dst']} ({e['amount_band']})" for e in f["timeline"][:12]),
        "## Evidence by bank\n" + "\n".join(
            f"- **{b}**: " + "; ".join(f"{a['masked_id']} ({', '.join(a['indicators'])})" for a in accts)
            for b, accts in f["accounts_by_bank"].items()),
        "## Red-flag indicators\n" + ", ".join(f"{k} ×{v}" for k, v in f["indicator_counts"].items()),
        f"## Confidence\n{conf['score']}/100: " + "; ".join(conf["reasons"]),
        "## Recommended action\nEach bank's compliance officer reviews their own customers in this ring and "
        "decides whether to file a suspicious transaction report. Nothing is filed automatically.",
    ]
    return "\n\n".join(lines)


def fallback_skeptic(f: dict) -> str:
    return (
        "## Innocent explanation\nThe members could be a rotating savings group or family members pooling money "
        "across banks, passing a similar sum around each cycle.\n\n"
        "## Evidence that would settle it\n- Known relationships between account holders (family, employer)\n"
        "- A stated purpose on the transfers, or regular schedules matching a savings club\n"
        "- Whether the money ends up spent normally, or leaves the system as cash or crypto\n\n"
        "## Weak points in the case\n- Indicators are behavioural only; no member has a confirmed fraud report\n"
        f"- Only {f['transfers_linking_ring']} transfers link the ring, over a short window")


async def write_case(result: dict, blocked: int) -> dict:
    f = case_facts(result, blocked)
    conf = confidence(f)
    facts = {**f, "confidence": conf}
    writer, skeptic = await asyncio.gather(
        generate("case_writer", WRITER_INSTRUCTION, facts, fallback_case_file(f, conf)),
        generate("skeptic", SKEPTIC_INSTRUCTION, facts, fallback_skeptic(f)))
    return {"facts": f, "confidence": conf, "case_file": writer, "skeptic": skeptic}
