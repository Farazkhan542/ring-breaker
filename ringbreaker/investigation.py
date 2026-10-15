"""Cross-bank investigation: the lead bank's agent follows the money hop by hop, asking other banks' agents narrow
questions over A2A. Every question and answer passes the policy agent and is written to the audit log.

The lead bank never sees other banks' raw data: it only holds its own partition plus the masked answers it receives.
"""
import asyncio
import secrets
from datetime import datetime, timezone
from typing import Awaitable, Callable

import networkx as nx

from . import planner as planner_mod
from .bank_agent import BankAgent
from .masking import mask
from .policy import Policy

Emit = Callable[[dict], Awaitable[None]]


class Investigation:
    def __init__(self, lead: BankAgent, seed_account: str, ask: Callable[[str, dict], Awaitable[dict]],
                 policy: Policy, emit: Emit, case_id: str | None = None, overreach_demo: bool = True,
                 planner: Callable | None = None):
        self.lead, self.seed, self.ask, self.policy, self.emit = lead, seed_account, ask, policy, emit
        self.planner = planner  # None: rule-based order (evaluation harness); planner.plan_next: Gemini
        self.case_id = case_id or f"CASE-{datetime.now(timezone.utc):%m%d}-{secrets.token_hex(3).upper()}"
        self.nodes: dict[str, dict] = {}   # masked_id -> {bank, flagged, indicators, hop}
        self.edges: dict[tuple, dict] = {}  # (src, dst, window, band) -> edge
        self.queries = 0
        self.overreach_demo = overreach_demo
        self.max_hops = policy.rules["R6-limits"]["max_hops_per_case"]

    # ---------- helpers ----------
    def _add_edge(self, me: str, cp: str, direction: str, band: str, window: str, reported_by: str):
        src, dst = (me, cp) if direction == "out" else (cp, me)
        self.edges.setdefault((src, dst, window, band), {"src": src, "dst": dst, "amount_band": band,
                                                         "time_window": window, "reported_by": reported_by})

    async def _ask(self, bank: str, req: dict) -> dict | None:
        req = {**req, "case_id": self.case_id, "from_bank": self.lead.bank}
        d = self.policy.check_request(req, self.queries)
        entry = self.policy.log(self.case_id, self.lead.bank, bank, "request", req, d)
        await self.emit({"type": "a2a_request", **entry})
        if not d.allowed:
            return None
        self.queries += 1
        resp = await self.ask(bank, req)
        d2 = self.policy.check_response(resp)
        entry = self.policy.log(self.case_id, bank, self.lead.bank, "response", resp, d2)
        await self.emit({"type": "a2a_response", **entry})
        return resp if d2.allowed else None

    # ---------- main loop ----------
    async def _expand(self, m: str, bank: str, hop: int) -> list[dict] | None:
        """Learn about one account. Own customers are checked locally (nothing leaves the bank); other banks' are
        asked over A2A. Returns its large-transfer counterparties if it is flagged and within the hop limit."""
        if bank == self.lead.bank:
            acct = self.lead.resolve_own(m)
            flags = self.lead.flags.get(acct)
            self.nodes[m] = {"bank": bank, "flagged": bool(flags), "indicators": flags or [], "hop": hop}
            await self.emit({"type": "local_check", "bank": bank, "masked_id": m, "flagged": bool(flags),
                             "indicators": flags or [], "hop": hop})
            if not flags or hop >= self.max_hops:
                return None
            return [{"direction": e["direction"], "masked_id": e["counterparty"], "bank_code": e["bank_code"],
                     "amount_band": e["amount_band"], "time_window": e["time_window"]}
                    for e in self.lead.local_graph(acct)]
        status = await self._ask(bank, {"type": "flag_status", "subject": m, "hop": hop,
                                        "fields": ["flagged", "indicators"]})
        if not status or status.get("status") != "ok":
            self.nodes[m] = {"bank": bank, "flagged": False, "indicators": [], "hop": hop, "withheld": True}
            return None
        self.nodes[m] = {"bank": bank, "flagged": True, "indicators": status["indicators"], "hop": hop}
        if self.overreach_demo:  # the one deliberately non-compliant request, to show the policy agent at work
            self.overreach_demo = False
            await self.emit({"type": "note", "text": "The report drafter asks for the customer's name and balance "
                                                     "to fill in the case file."})
            await self._ask(bank, {"type": "flag_status", "subject": m, "hop": hop, "fields": ["name", "balance"]})
        if hop >= self.max_hops:
            return None
        linked = await self._ask(bank, {"type": "linked_counterparties", "subject": m, "hop": hop,
                                        "fields": ["masked_id", "bank_code", "direction", "amount_band",
                                                   "time_window"]})
        return linked["counterparties"] if linked and linked.get("status") == "ok" else None

    def _known(self) -> list[dict]:
        return [{"masked_id": m, "bank": n["bank"], "flagged": n["flagged"], "indicators": n["indicators"],
                 "hop": n["hop"]} for m, n in self.nodes.items()]

    async def run(self) -> dict:
        lead, seed = self.lead, self.seed
        ind = lead.flags.get(seed, [])
        d = self.policy.check_case_open(ind)
        self.policy.log(self.case_id, lead.bank, "consortium", "case_open", {"subject": mask(seed)}, d)
        await self.emit({"type": "case_open", "case_id": self.case_id, "bank": lead.bank, "subject": mask(seed),
                         "indicators": ind, "allowed": d.allowed, "rule_id": d.rule_id, "rule_text": d.rule_text})
        if not d.allowed:
            return self.result()

        frontier: dict[str, dict] = {}  # masked_id -> lead {masked_id, bank_code, hop, direction, band, window, via}
        done: set[str] = set()

        async def visit(m: str, bank: str, hop: int):
            done.add(m)
            frontier.pop(m, None)
            cps = await self._expand(m, bank, hop)
            if cps is None:
                return
            for c in cps:
                self._add_edge(m, c["masked_id"], c["direction"], c["amount_band"], c["time_window"], bank)
                if c["masked_id"] not in done and c["masked_id"] not in frontier:
                    frontier[c["masked_id"]] = {**c, "hop": hop + 1, "linked_to": m}
            await self.emit({"type": "graph", **self.graph_payload()})

        await visit(mask(seed), lead.bank, 0)
        limit = self.policy.rules["R6-limits"]["max_queries_per_case"]
        while frontier and self.queries < limit:
            # own-bank leads cost nothing to check: do them first, locally
            own = [c for c in frontier.values() if c["bank_code"] == lead.bank]
            if own:
                for c in own:
                    await visit(c["masked_id"], lead.bank, c["hop"])
                continue
            leads = sorted(frontier.values(), key=lambda c: (c["hop"], c["time_window"]))
            if self.planner is None:
                plan = {**planner_mod.heuristic_plan(leads, 3), "source": "rules", "model": None}
            else:
                await self.emit({"type": "thinking", "text": f"Planner is weighing {len(leads)} lead(s)."})
                plan = await self.planner(self._known(), leads, 3, limit - self.queries)
            await self.emit({"type": "plan", "leads": len(leads), "ask": plan["ask"], "drop": plan["drop"],
                             "reason": plan["reason"], "source": plan["source"], "model": plan["model"]})
            for m in plan["drop"]:
                done.add(m)
                frontier.pop(m, None)
            for m in plan["ask"]:
                if m in frontier and self.queries < limit:
                    c = frontier[m]
                    await visit(m, c["bank_code"], c["hop"])
            if not plan["ask"] and not plan["drop"]:
                break
        return self.result()

    # ---------- case builder (deterministic part) ----------
    def ring(self) -> list[str]:
        """Connected flagged accounts around the seed (both ends flagged by their own bank)."""
        g = nx.Graph()
        flagged = {m for m, n in self.nodes.items() if n["flagged"]}
        g.add_nodes_from(flagged)
        for e in self.edges.values():
            if e["src"] in flagged and e["dst"] in flagged:
                g.add_edge(e["src"], e["dst"])
        seed = mask(self.seed)
        return sorted(nx.node_connected_component(g, seed)) if seed in g else []

    def graph_payload(self) -> dict:
        ring = set(self.ring())
        return {"nodes": [{"id": m, **n, "in_ring": m in ring} for m, n in self.nodes.items()],
                "edges": [e for e in self.edges.values() if e["src"] in self.nodes and e["dst"] in self.nodes]}

    def result(self) -> dict:
        ring = self.ring()
        ring_set = set(ring)
        edges = sorted([e for e in self.edges.values() if e["src"] in ring_set and e["dst"] in ring_set],
                       key=lambda e: e["time_window"])
        return {"case_id": self.case_id, "lead_bank": self.lead.bank, "seed": mask(self.seed),
                "ring": [{"id": m, **self.nodes[m]} for m in ring],
                "banks": sorted({self.nodes[m]["bank"] for m in ring}),
                "timeline": edges, "queries": self.queries,
                "nodes_checked": len(self.nodes), **self.graph_payload()}


async def run_investigation(*args, **kwargs) -> dict:
    return await Investigation(*args, **kwargs).run()


def run_local(agents: dict[str, BankAgent], seed_bank: str, seed_account: str, policy: Policy,
              overreach_demo: bool = False) -> dict:
    """Run without HTTP (bank agents called in-process) - used by the evaluation harness and tests."""
    async def ask(bank, req):
        return agents[bank].handle(req)

    async def emit(_):
        return None
    return asyncio.run(run_investigation(agents[seed_bank], seed_account, ask, policy, emit,
                                         overreach_demo=overreach_demo))
