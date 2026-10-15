"""Cross-bank investigation: the lead bank's agent follows the money hop by hop, asking other banks' agents narrow
questions over A2A. Every question and answer passes the policy agent and is written to the audit log.

The lead bank never sees other banks' raw data: it only holds its own partition plus the masked answers it receives.
"""
import asyncio
import itertools
from collections import deque
from typing import Awaitable, Callable

import networkx as nx

from .bank_agent import BankAgent
from .masking import mask
from .policy import Policy

Emit = Callable[[dict], Awaitable[None]]
BAND_PRIORITY = {"8k-10k": 0, "10k-20k": 1, "5k-8k": 2, "20k-50k": 3, "3k-5k": 4}
_case_counter = itertools.count(1)


class Investigation:
    def __init__(self, lead: BankAgent, seed_account: str, ask: Callable[[str, dict], Awaitable[dict]],
                 policy: Policy, emit: Emit, case_id: str | None = None, overreach_demo: bool = True):
        self.lead, self.seed, self.ask, self.policy, self.emit = lead, seed_account, ask, policy, emit
        self.case_id = case_id or f"CASE-{next(_case_counter):04d}"
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
    async def run(self) -> dict:
        lead, seed = self.lead, self.seed
        ind = lead.flags.get(seed, [])
        d = self.policy.check_case_open(ind)
        self.policy.log(self.case_id, lead.bank, "consortium", "case_open", {"subject": mask(seed)}, d)
        await self.emit({"type": "case_open", "case_id": self.case_id, "bank": lead.bank, "subject": mask(seed),
                         "indicators": ind, "allowed": d.allowed, "rule_id": d.rule_id, "rule_text": d.rule_text})
        if not d.allowed:
            return self.result()

        queue = deque([(mask(seed), lead.bank, 0)])
        seen = set()
        while queue:
            m, bank, hop = queue.popleft()
            if m in seen:
                continue
            seen.add(m)
            if bank == lead.bank:  # own customer: checked locally, nothing leaves the bank
                acct = lead.resolve_own(m)
                flags = lead.flags.get(acct)
                self.nodes[m] = {"bank": bank, "flagged": bool(flags), "indicators": flags or [], "hop": hop}
                await self.emit({"type": "local_check", "bank": bank, "masked_id": m, "flagged": bool(flags),
                                 "indicators": flags or [], "hop": hop})
                if not flags or hop >= self.max_hops:
                    continue
                cps = [{"direction": e["direction"], "masked_id": e["counterparty"], "bank_code": e["bank_code"],
                        "amount_band": e["amount_band"], "time_window": e["time_window"]}
                       for e in lead.local_graph(acct)]
                reporter = bank
            else:
                status = await self._ask(bank, {"type": "flag_status", "subject": m, "hop": hop,
                                                "fields": ["flagged", "indicators"]})
                if not status or status.get("status") != "ok":
                    self.nodes[m] = {"bank": bank, "flagged": False, "indicators": [], "hop": hop,
                                     "withheld": True}
                    continue
                self.nodes[m] = {"bank": bank, "flagged": True, "indicators": status["indicators"], "hop": hop}
                if self.overreach_demo:  # the one deliberately non-compliant request, to show the policy agent
                    self.overreach_demo = False
                    await self.emit({"type": "note", "text": "The report drafter asks for the customer's name and "
                                                             "balance to fill in the case file."})
                    await self._ask(bank, {"type": "flag_status", "subject": m, "hop": hop,
                                           "fields": ["name", "balance"]})
                if hop >= self.max_hops:
                    continue
                linked = await self._ask(bank, {"type": "linked_counterparties", "subject": m, "hop": hop,
                                                "fields": ["masked_id", "bank_code", "direction", "amount_band",
                                                           "time_window"]})
                if not linked or linked.get("status") != "ok":
                    continue
                cps, reporter = linked["counterparties"], bank
            for c in cps:
                self._add_edge(m, c["masked_id"], c["direction"], c["amount_band"], c["time_window"], reporter)
            # follow likely laundering transfers first (bands near the 10k threshold), then the rest
            for c in sorted(cps, key=lambda c: BAND_PRIORITY.get(c["amount_band"], 9)):
                if c["masked_id"] not in seen:
                    queue.append((c["masked_id"], c["bank_code"], hop + 1))
            await self.emit({"type": "graph", **self.graph_payload()})
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
