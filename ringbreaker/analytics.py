"""BigQuery sink and regulator view.

Every cross-bank message (from the policy agent's audit log), every finished case and every evaluation result is
written to BigQuery, and the Regulator tab reads summaries back. Rows are sent with batch load jobs from a
background thread, never during an investigation (load jobs are free and work in the BigQuery sandbox).

Enabled when RB_BQ_DATASET and a project (GOOGLE_CLOUD_PROJECT) are set; otherwise the regulator view is computed
from this server's memory, so the app works the same without BigQuery.

    python -m ringbreaker.analytics setup         # create dataset, tables and views
    python -m ringbreaker.analytics export-eval   # load results/metrics.json rows into eval_results
"""
import json
import logging
import os
import sys
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

from . import config

log = logging.getLogger(__name__)

DATASET = os.environ.get("RB_BQ_DATASET", "")
PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
LOCATION = os.environ.get("RB_BQ_LOCATION", "asia-southeast1")

SCHEMAS = {
    "audit_log": [("ts", "TIMESTAMP"), ("case_id", "STRING"), ("from_bank", "STRING"), ("to_bank", "STRING"),
                  ("kind", "STRING"), ("query_type", "STRING"), ("allowed", "BOOL"), ("rule_id", "STRING"),
                  ("detail", "STRING"), ("status", "STRING"), ("masked_ids", "INT64"), ("records", "INT64"),
                  ("payload", "STRING")],
    "cases": [("ts", "TIMESTAMP"), ("case_id", "STRING"), ("lead_bank", "STRING"), ("ring_size", "INT64"),
              ("banks", "STRING"), ("questions", "INT64"), ("blocked", "INT64"), ("seconds", "FLOAT64"),
              ("confidence", "INT64"), ("planner_source", "STRING"), ("writer_model", "STRING"),
              ("skeptic_model", "STRING")],
    "eval_results": [("generated", "STRING"), ("section", "STRING"), ("row", "STRING")],
}

VIEWS = {
    "v_bank_activity": """
        SELECT IF(kind = 'request', to_bank, from_bank) AS bank,
               COUNTIF(kind = 'request' AND allowed) AS questions_received,
               COUNTIF(kind = 'response' AND status = 'ok') AS answers_sent,
               COUNTIF(kind = 'response' AND status = 'withheld') AS answers_withheld,
               SUM(IF(kind = 'response', masked_ids, 0)) AS masked_ids_shared,
               SUM(IF(kind = 'response', records, 0)) AS records_shared
        FROM `{p}.{d}.audit_log` WHERE kind IN ('request', 'response') GROUP BY bank""",
    "v_blocked_by_rule": """
        SELECT rule_id, ANY_VALUE(detail) AS example, COUNT(*) AS blocked
        FROM `{p}.{d}.audit_log` WHERE NOT allowed GROUP BY rule_id""",
    "v_cases_daily": """
        SELECT DATE(ts) AS day, COUNT(*) AS cases, AVG(ring_size) AS avg_ring_size,
               SUM(questions) AS questions, SUM(blocked) AS blocked, AVG(seconds) AS avg_seconds
        FROM `{p}.{d}.cases` GROUP BY day""",
}


def enabled() -> bool:
    return bool(DATASET and PROJECT)


_client = None


def client():
    global _client
    if _client is None:
        from google.cloud import bigquery
        _client = bigquery.Client(project=PROJECT, location=LOCATION)
    return _client


def setup() -> None:
    """Create the dataset, tables and views if missing."""
    from google.cloud import bigquery
    c = client()
    ds = bigquery.Dataset(f"{PROJECT}.{DATASET}")
    ds.location = LOCATION
    c.create_dataset(ds, exists_ok=True)
    for name, cols in SCHEMAS.items():
        schema = [bigquery.SchemaField(n, t) for n, t in cols]
        c.create_table(bigquery.Table(f"{PROJECT}.{DATASET}.{name}", schema=schema), exists_ok=True)
    for name, sql in VIEWS.items():
        view = bigquery.Table(f"{PROJECT}.{DATASET}.{name}")
        view.view_query = sql.format(p=PROJECT, d=DATASET)
        c.delete_table(view, not_found_ok=True)
        c.create_table(view)


# ---------------- writing ----------------
_buffer: dict[str, list] = defaultdict(list)
_lock = threading.Lock()


def _audit_row(e: dict) -> dict:
    p = e.get("payload") or {}
    ids = set()
    if p.get("masked_id") and p.get("status") == "ok":
        ids.add(p["masked_id"])
    for c in p.get("counterparties") or []:
        ids.add(c.get("masked_id"))
    return {"ts": e["ts"], "case_id": e["case_id"], "from_bank": e["from"], "to_bank": e["to"], "kind": e["kind"],
            "query_type": p.get("type"), "allowed": bool(e["allowed"]), "rule_id": e["rule_id"],
            "detail": e.get("detail", "")[:500], "status": p.get("status"), "masked_ids": len(ids),
            "records": len(p.get("counterparties") or []), "payload": json.dumps(p, default=str)[:4000]}


def record_audit(entry: dict) -> None:
    if enabled():
        with _lock:
            _buffer["audit_log"].append(_audit_row(entry))


def record_case(row: dict) -> None:
    if enabled():
        with _lock:
            _buffer["cases"].append(row)


def _load(table: str, rows: list) -> None:
    from google.cloud import bigquery
    cfg = bigquery.LoadJobConfig(schema=[bigquery.SchemaField(n, t) for n, t in SCHEMAS[table]],
                                 write_disposition="WRITE_APPEND")
    client().load_table_from_json(rows, f"{PROJECT}.{DATASET}.{table}", job_config=cfg).result(timeout=120)


def flush(background: bool = True) -> None:
    """Send buffered rows with one load job per table."""
    if not enabled():
        return
    with _lock:
        batches = {t: rows[:] for t, rows in _buffer.items() if rows}
        _buffer.clear()

    def work():
        for table, rows in batches.items():
            try:
                _load(table, rows)
            except Exception as e:  # never break the app over analytics
                log.warning("BigQuery load into %s failed (%d rows): %s", table, len(rows), str(e)[:200])
    if background:
        threading.Thread(target=work, daemon=True).start()
    else:
        work()


def export_eval(path=None) -> int:
    path = path or config.ROOT / "results" / "metrics.json"
    m = json.loads(open(path, encoding="utf-8").read())
    rows = [{"generated": m["generated"], "section": s["title"], "row": json.dumps(r, default=str)}
            for s in m["sections"] for r in s["rows"]]
    _load("eval_results", rows)
    return len(rows)


# ---------------- reading (Regulator tab) ----------------
_cache = {"at": 0.0, "data": None}


def _from_memory(audit: list, cases: list) -> dict:
    by_bank = defaultdict(Counter)
    blocked = Counter()
    for e in audit:
        r = _audit_row(e)
        if r["kind"] == "request":
            if r["allowed"]:
                by_bank[r["to_bank"]]["questions_received"] += 1
            else:
                blocked[r["rule_id"]] += 1
        elif r["kind"] == "response":
            b = by_bank[r["from_bank"]]
            b["answers_sent" if r["status"] == "ok" else "answers_withheld"] += 1
            b["masked_ids_shared"] += r["masked_ids"]
            b["records_shared"] += r["records"]
    return {"by_bank": [{"bank": k, **{f: v.get(f, 0) for f in ("questions_received", "answers_sent",
                                                                 "answers_withheld", "masked_ids_shared",
                                                                 "records_shared")}}
                        for k, v in sorted(by_bank.items())],
            "blocked_by_rule": [{"rule_id": k, "blocked": v} for k, v in blocked.most_common()],
            "cases": [{k: c.get(k) for k in ("ts", "case_id", "lead_bank", "ring_size", "questions", "blocked",
                                             "seconds", "confidence")} for c in cases[-10:][::-1]]}


def regulator_view(audit: list, cases: list) -> dict:
    """Summaries from BigQuery when enabled (cached 30 s); otherwise from this server's memory."""
    if enabled():
        if _cache["data"] and time.time() - _cache["at"] < 30:
            return _cache["data"]
        try:
            c = client()
            q = lambda sql: [dict(r) for r in c.query(sql.format(p=PROJECT, d=DATASET)).result(timeout=20)]
            data = {
                "source": "bigquery", "dataset": f"{PROJECT}.{DATASET}",
                "by_bank": q("SELECT * FROM `{p}.{d}.v_bank_activity` ORDER BY bank"),
                "blocked_by_rule": q("SELECT rule_id, blocked FROM `{p}.{d}.v_blocked_by_rule` ORDER BY blocked DESC"),
                "cases": q("SELECT ts, case_id, lead_bank, ring_size, questions, blocked, seconds, confidence "
                           "FROM `{p}.{d}.cases` ORDER BY ts DESC LIMIT 10"),
            }
            for row in data["cases"]:
                row["ts"] = row["ts"].isoformat() if hasattr(row["ts"], "isoformat") else row["ts"]
            _cache.update(at=time.time(), data=data)
            return data
        except Exception as e:
            log.warning("BigQuery read failed, using memory: %s", str(e)[:200])
    return {"source": "memory", **_from_memory(audit, cases)}


def case_row(result: dict, case: dict, seconds: float, blocked: int, planner_source: str) -> dict:
    return {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "case_id": result["case_id"],
            "lead_bank": result["lead_bank"], "ring_size": len(result["ring"]), "banks": ",".join(result["banks"]),
            "questions": result["queries"], "blocked": blocked, "seconds": round(seconds, 1),
            "confidence": case["confidence"]["score"], "planner_source": planner_source,
            "writer_model": case["case_file"].get("model"), "skeptic_model": case["skeptic"].get("model")}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if not enabled():
        sys.exit("Set RB_BQ_DATASET and GOOGLE_CLOUD_PROJECT first.")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "setup"
    if cmd == "setup":
        setup()
        print(f"dataset {PROJECT}.{DATASET} ready ({LOCATION})")
    elif cmd == "export-eval":
        print("loaded", export_eval(), "evaluation rows")
