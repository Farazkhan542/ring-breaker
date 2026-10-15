"""Orchestrator API (single Cloud Run service): hosts each bank agent's A2A endpoint, runs the demo scenario, and
serves the web UI. Bank agents are reached over real A2A HTTP calls, even though they share this container."""
import asyncio
import json
import logging
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .a2a_client import A2APeers
from .bank_agent import BankAgent, a2a_routes
from .casefile import write_case
from .data import load_world, partition
from .flags import INDICATOR_HELP
from .linking import siloed_groups
from .llm import llm_available
from .masking import mask
from .policy import Policy

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ringbreaker")

# Demo scenario: seed-42 world, case opened by BANK_C about its flagged customer C-00717 (ring R11, a 6-account
# cycle across 3 banks that no bank can see alone). Chosen by running the investigation from every ring member.
DEMO_BANK, DEMO_ACCOUNT = "BANK_C", "C-00717"
STEP_DELAY = float(__import__("os").environ.get("RB_STEP_DELAY", "0.35"))

STATE: dict = {}


def _db():
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.STATE_DIR / "decisions.db")
    con.execute("create table if not exists decisions (case_id text, bank text, decision text, reason text, ts text)")
    return con


@asynccontextmanager
async def lifespan(app: FastAPI):
    t0 = time.time()
    world = load_world()
    policy = Policy.load()
    agents = {b: BankAgent(partition(world, b), policy) for b in config.BANKS}
    STATE.update(world=world, policy=policy, agents=agents, peers=A2APeers(config.A2A_BASE_URL, config.BANKS))
    log.info("bank agents ready in %.1fs (LLM available: %s, model %s)", time.time() - t0, llm_available(),
             config.MODEL_ID)
    yield
    await STATE["peers"].close()


app = FastAPI(title="Ring Breaker", lifespan=lifespan)


def _mount_a2a():
    # Routes need agents, which load at startup; mount lazily-built routes via a sub-app per bank.
    from starlette.applications import Starlette
    from starlette.routing import Mount

    for b in config.BANKS:
        prefix = f"/a2a/{b.lower()}"

        class _Lazy:
            def __init__(self, bank, prefix):
                self.bank, self.prefix, self.app = bank, prefix, None

            async def __call__(self, scope, receive, send):
                if self.app is None:
                    self.app = Starlette(routes=a2a_routes(STATE["agents"][self.bank], "/",
                                                           f"{config.A2A_BASE_URL}{self.prefix}/"))
                await self.app(scope, receive, send)
        app.router.routes.append(Mount(prefix, app=_Lazy(b, prefix)))


_mount_a2a()


@app.get("/healthz")
def healthz():
    return {"ok": True, "agents_loaded": "agents" in STATE, "llm": llm_available(), "model": config.MODEL_ID}


@app.get("/api/banks")
def banks():
    """Each bank's own view: its flagged customers and what it can link alone. Raw IDs here stay inside each bank."""
    world, agents = STATE["world"], STATE["agents"]
    demo_ring = next(r for r in world.rings if DEMO_ACCOUNT in r["accounts"])
    out = []
    for b, ag in agents.items():
        groups = siloed_groups(ag.view, ag.flags)
        ring_here = [a for a in demo_ring["accounts"] if a in ag.view.accounts.index]
        flagged_here = [a for a in ring_here if a in ag.flags]
        sees_ring = any(len(g & set(demo_ring["accounts"])) >= 3 for g in groups)
        out.append({
            "bank": b, "customers": int(len(ag.view.accounts)), "transactions_visible": int(len(ag.view.tx)),
            "flagged": [{"account": a, "masked_id": mask(a), "indicators": ind,
                         "in_demo_case": a in ring_here} for a, ind in ag.flags.items()],
            "case_customers_flagged": len(flagged_here),
            "alone_finds_case_ring": sees_ring,
            "alone_summary": (f"{b} alone: {len(flagged_here)} suspicious customer(s) of its own, sending money to "
                              "other banks. No ring visible." if not sees_ring else f"{b} alone: ring visible"),
        })
    return {"banks": out, "indicator_help": INDICATOR_HELP}


async def _demo_events():
    policy, agents, peers = STATE["policy"], STATE["agents"], STATE["peers"]
    q: asyncio.Queue = asyncio.Queue()

    async def emit(ev):
        await q.put(ev)
        await asyncio.sleep(STEP_DELAY)

    async def work():
        from .investigation import Investigation
        t0 = time.time()
        try:
            await emit({"type": "phase", "text": f"{DEMO_BANK}'s agent opens a case about its own flagged customer."})
            inv = Investigation(agents[DEMO_BANK], DEMO_ACCOUNT, peers.ask, policy, emit)
            result = await inv.run()
            STATE.setdefault("cases", {})[result["case_id"]] = result
            blocked = sum(1 for e in policy.audit if e["case_id"] == result["case_id"] and not e["allowed"])
            await emit({"type": "ring", **result})
            await emit({"type": "phase", "text": "Case-writer and skeptic agents (Gemini) are drafting the case file."})
            case = await write_case(result, blocked)
            STATE["cases"][result["case_id"]]["case"] = case
            await q.put({"type": "case_file", "case_id": result["case_id"], **case})
            shared = [e for e in policy.audit if e["case_id"] == result["case_id"]]
            await q.put({"type": "done", "case_id": result["case_id"], "seconds": round(time.time() - t0, 1),
                         "queries": result["queries"], "blocked": blocked, "audit_entries": len(shared)})
        except Exception as e:
            log.exception("demo failed")
            await q.put({"type": "error", "text": str(e)})
        finally:
            await q.put(None)

    task = asyncio.create_task(work())
    try:
        while (ev := await q.get()) is not None:
            yield f"data: {json.dumps(ev, default=str)}\n\n"
    finally:
        task.cancel()


@app.get("/api/demo/run")
async def demo_run():
    return StreamingResponse(_demo_events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class DecisionIn(BaseModel):
    bank: str
    decision: str  # approve | reject | more_evidence
    reason: str = ""


@app.post("/api/cases/{case_id}/decisions")
def decide(case_id: str, d: DecisionIn):
    if d.bank not in config.BANKS or d.decision not in ("approve", "reject", "more_evidence"):
        raise HTTPException(400, "bad bank or decision")
    with _db() as con:
        con.execute("insert into decisions values (?,?,?,?,?)",
                    (case_id, d.bank, d.decision, d.reason[:500], datetime.now(timezone.utc).isoformat()))
    return decisions(case_id)


@app.get("/api/cases/{case_id}/decisions")
def decisions(case_id: str):
    with _db() as con:
        rows = con.execute("select bank, decision, reason, ts from decisions where case_id=? order by ts",
                           (case_id,)).fetchall()
    latest = {}
    for bank, dec, reason, ts in rows:
        latest[bank] = {"decision": dec, "reason": reason, "ts": ts}
    return {"case_id": case_id, "decisions": latest, "history": len(rows)}


@app.get("/api/audit")
def audit(case_id: str | None = None):
    entries = [e for e in STATE["policy"].audit if case_id is None or e["case_id"] == case_id]
    return {"entries": entries[-500:]}


@app.get("/api/policy")
def policy():
    return {"rules": list(STATE["policy"].rules.values())}


@app.get("/api/metrics")
def metrics():
    path = config.ROOT / "results" / "metrics.json"
    if not path.exists():
        return JSONResponse({"error": "run python -m ringbreaker.eval first"}, status_code=404)
    return json.loads(path.read_text())


WEB = config.ROOT / "web"


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")
