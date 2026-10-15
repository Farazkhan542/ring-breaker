"""Policy agent: checks every cross-bank request and response against policy.yaml and writes the audit log."""
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

import yaml

from . import config

RAW_ID = re.compile(r"\b[ABC]-\d{5}\b")  # raw account-number format of the synthetic banks


@dataclass
class Decision:
    allowed: bool
    rule_id: str
    rule_text: str
    detail: str = ""


@dataclass
class Policy:
    rules: dict
    audit: list = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @classmethod
    def load(cls, path=config.POLICY_FILE) -> "Policy":
        doc = yaml.safe_load(open(path, encoding="utf-8"))
        return cls(rules={r["id"]: r for r in doc["rules"]})

    def _r(self, rid: str) -> dict:
        return self.rules[rid]

    def _deny(self, rid: str, detail: str) -> Decision:
        return Decision(False, rid, self._r(rid)["text"], detail)

    def _allow(self, rid: str, detail: str = "") -> Decision:
        return Decision(True, rid, self._r(rid)["text"], detail)

    # ---- checks ----
    def check_case_open(self, indicators: list[str]) -> Decision:
        need = self._r("R1-case-trigger")["min_indicators_to_open_case"]
        if len(indicators) >= need:
            return self._allow("R1-case-trigger", f"subject shows {len(indicators)} indicators: {', '.join(indicators)}")
        return self._deny("R1-case-trigger", f"subject shows only {len(indicators)} indicator(s)")

    def check_request(self, req: dict, queries_so_far: int) -> Decision:
        if req.get("type") not in self._r("R3-allowed-questions")["allowed_query_types"]:
            return self._deny("R3-allowed-questions", f"question type '{req.get('type')}' is not allowed")
        bad = [f for f in req.get("fields", []) if f in self._r("R5-forbidden-fields")["forbidden_fields"]]
        if bad:
            return self._deny("R5-forbidden-fields", f"asked for forbidden field(s): {', '.join(bad)}")
        unknown = [f for f in req.get("fields", []) if f not in self._r("R4-allowed-fields")["allowed_fields"]]
        if unknown:
            return self._deny("R4-allowed-fields", f"field(s) not on the allowed list: {', '.join(unknown)}")
        lim = self._r("R6-limits")
        if req.get("hop", 0) > lim["max_hops_per_case"]:
            return self._deny("R6-limits", f"hop {req['hop']} exceeds {lim['max_hops_per_case']}")
        if queries_so_far >= lim["max_queries_per_case"]:
            return self._deny("R6-limits", f"case already asked {queries_so_far} questions")
        if RAW_ID.search(str(req)):
            return self._deny("R5-forbidden-fields", "request contains a raw account number")
        return self._allow("R3-allowed-questions", f"'{req['type']}' about a masked ID")

    def check_share(self, indicators: list[str] | None) -> Decision:
        """Responder side: may this bank share anything about its own customer?"""
        need = self._r("R2-share-only-if-flagged")["min_indicators_to_share"]
        if indicators and len(indicators) >= need:
            return self._allow("R2-share-only-if-flagged", f"customer flagged locally ({len(indicators)} indicators)")
        return self._deny("R2-share-only-if-flagged", "customer not flagged locally, so nothing is shared")

    def check_response(self, resp: dict) -> Decision:
        allowed = set(self._r("R4-allowed-fields")["allowed_fields"])

        def keys(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    yield k
                    yield from keys(v)
            elif isinstance(o, list):
                for v in o:
                    yield from keys(v)
        extra = sorted({k for k in keys(resp)} - allowed)
        if extra:
            return self._deny("R4-allowed-fields", f"answer contains non-allowed field(s): {', '.join(extra)}")
        if RAW_ID.search(str(resp)):
            return self._deny("R5-forbidden-fields", "answer contains a raw account number")
        return self._allow("R4-allowed-fields", "answer contains only allowed fields")

    # ---- audit ----
    def log(self, case_id: str, frm: str, to: str, kind: str, payload: dict, decision: Decision) -> dict:
        entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "case_id": case_id, "from": frm,
                 "to": to, "kind": kind, "payload": payload, "allowed": decision.allowed,
                 "rule_id": decision.rule_id, "rule_text": decision.rule_text, "detail": decision.detail}
        with self._lock:
            self.audit.append(entry)
            del self.audit[:-20000]  # bounded in memory; production writes to Cloud Logging / BigQuery
        return entry
