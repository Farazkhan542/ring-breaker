"""Bank agent: one per bank, holding ONLY that bank's partition. Exposes deterministic tools and an A2A endpoint
that answers narrow, policy-checked questions about the bank's own customers."""
import logging

from a2a.helpers import get_data_parts, new_data_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue_v2 import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentProvider, AgentSkill

from .config import LARGE
from .data import BankView
from .flags import compute_flags
from .masking import amount_band, mask, time_window
from .policy import Policy

log = logging.getLogger(__name__)


class BankAgent:
    def __init__(self, view: BankView, policy: Policy, flags: dict | None = None):
        self.bank = view.bank
        self.view = view
        self.policy = policy
        self.flags = flags if flags is not None else compute_flags(view)
        # The bank can reverse pseudonyms of its OWN customers only.
        self._own_by_mask = {mask(a): a for a in view.accounts.index}

    # ---------------- local tools ----------------
    def list_flagged_customers(self) -> list[dict]:
        return [{"account": a, "masked_id": mask(a), "indicators": ind} for a, ind in self.flags.items()]

    def local_graph(self, account: str) -> list[dict]:
        """Large transfers touching an own customer. Counterparties at other banks appear masked."""
        tx = self.view.tx
        big = tx[(tx["Amount"] >= LARGE) & ((tx["From Account"] == account) | (tx["To Account"] == account))]
        out = []
        for _, r in big.sort_values("Timestamp").iterrows():
            outgoing = r["From Account"] == account
            cp, cp_bank = (r["To Account"], r["To Bank"]) if outgoing else (r["From Account"], r["From Bank"])
            out.append({"direction": "out" if outgoing else "in", "counterparty": mask(cp), "bank_code": cp_bank,
                        "own_counterparty": cp if cp_bank == self.bank else None,
                        "amount": float(r["Amount"]), "amount_band": amount_band(r["Amount"]),
                        "time_window": time_window(r["Timestamp"]), "ts": r["Timestamp"].isoformat()})
        return out

    def resolve_own(self, masked_id: str) -> str | None:
        return self._own_by_mask.get(masked_id)

    # ---------------- A2A answers ----------------
    def answer_query(self, q: dict) -> dict:
        """Answer a narrow question about an own customer. Returns masked IDs, bands, windows and indicators only."""
        subject = q.get("subject", "")
        acct = self.resolve_own(subject)
        if acct is None:
            return {"status": "unknown", "masked_id": subject, "bank_code": self.bank,
                    "reason": "not a customer of this bank"}
        share = self.policy.check_share(self.flags.get(acct))
        if not share.allowed:
            return {"status": "withheld", "masked_id": subject, "bank_code": self.bank, "reason": share.detail}
        if q["type"] == "flag_status":
            return {"status": "ok", "masked_id": subject, "bank_code": self.bank, "flagged": True,
                    "indicators": self.flags[acct]}
        if q["type"] == "linked_counterparties":
            cps = [{k: e[k] for k in ("direction", "amount_band", "time_window", "bank_code")} |
                   {"masked_id": e["counterparty"]} for e in self.local_graph(acct)]
            return {"status": "ok", "masked_id": subject, "bank_code": self.bank, "counterparties": cps}
        return {"status": "withheld", "masked_id": subject, "bank_code": self.bank, "reason": "unsupported question"}

    def handle(self, q: dict) -> dict:
        """Full responder path: answer, then the policy agent checks the outgoing answer before it leaves."""
        resp = self.answer_query(q)
        check = self.policy.check_response(resp)
        if not check.allowed:  # defence in depth: never release a non-compliant answer
            resp = {"status": "withheld", "masked_id": q.get("subject", ""), "bank_code": self.bank,
                    "reason": f"blocked by {check.rule_id}: {check.detail}"}
        return resp


class BankA2AExecutor(AgentExecutor):
    """A2A executor: reads one structured question from the message's data part and replies with one data message."""

    def __init__(self, agent: BankAgent):
        self.agent = agent

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        parts = get_data_parts(context.message.parts) if context.message else []
        q = parts[0] if parts else {}
        resp = self.agent.handle(q)
        await event_queue.enqueue_event(new_data_message(resp, context_id=context.context_id))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        return None


def agent_card(bank: str, url: str) -> AgentCard:
    return AgentCard(
        name=f"Ring Breaker {bank} investigator",
        description=f"{bank}'s AML investigator agent. Answers narrow, policy-checked questions about {bank}'s own "
                    "customers using masked IDs only.",
        supported_interfaces=[AgentInterface(url=url, protocol_binding="JSONRPC", protocol_version="1.0")],
        provider=AgentProvider(organization="Ring Breaker consortium (demo)", url="https://github.com"),
        version="0.1.0",
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["application/json"],
        default_output_modes=["application/json"],
        skills=[
            AgentSkill(id="flag_status", name="Flag status",
                       description="Is this masked account your customer, flagged by your own rules, and why?",
                       tags=["aml", "red-flags"]),
            AgentSkill(id="linked_counterparties", name="Linked counterparties",
                       description="Masked counterparties of large transfers to or from a flagged customer, with "
                                   "amount bands and 6-hour time windows.", tags=["aml", "graph"]),
        ],
    )


def a2a_routes(agent: BankAgent, prefix: str, public_url: str) -> list:
    """Starlette routes for this bank's A2A JSON-RPC endpoint and agent card, mounted under `prefix`."""
    card = agent_card(agent.bank, public_url)
    handler = DefaultRequestHandler(agent_executor=BankA2AExecutor(agent), task_store=InMemoryTaskStore(),
                                    agent_card=card)
    return [*create_agent_card_routes(card, card_url=f"{prefix.rstrip('/')}/.well-known/agent-card.json"),
            *create_jsonrpc_routes(handler, prefix)]
