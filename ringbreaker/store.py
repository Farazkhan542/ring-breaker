"""Officer decision store: Firestore on Google Cloud (RB_STORE=firestore), SQLite locally."""
import os
import sqlite3
from datetime import datetime, timezone

from . import config

BACKEND = os.environ.get("RB_STORE", "sqlite")


def _sqlite():
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.STATE_DIR / "decisions.db")
    con.execute("create table if not exists decisions (case_id text, bank text, decision text, reason text, ts text)")
    return con


_fs = None


def _firestore():
    global _fs
    if _fs is None:
        from google.cloud import firestore
        _fs = firestore.Client(database=os.environ.get("RB_FIRESTORE_DB", "(default)"))
    return _fs


def add_decision(case_id: str, bank: str, decision: str, reason: str) -> None:
    row = {"case_id": case_id, "bank": bank, "decision": decision, "reason": reason[:500],
           "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if BACKEND == "firestore":
        _firestore().collection("cases").document(case_id).collection("decisions").add(row)
    else:
        with _sqlite() as con:
            con.execute("insert into decisions values (:case_id,:bank,:decision,:reason,:ts)", row)


def list_decisions(case_id: str) -> list[dict]:
    if BACKEND == "firestore":
        docs = _firestore().collection("cases").document(case_id).collection("decisions").stream()
        rows = [d.to_dict() for d in docs]
    else:
        with _sqlite() as con:
            rows = [dict(zip(("bank", "decision", "reason", "ts"), r)) for r in con.execute(
                "select bank, decision, reason, ts from decisions where case_id=?", (case_id,))]
    return sorted(rows, key=lambda r: r["ts"])
