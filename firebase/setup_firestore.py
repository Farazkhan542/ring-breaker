"""Register the Firebase web app and publish Firestore security rules (Firebase Management and Rules REST APIs).

Writes firebase/public/data/firebase-config.json (a Firebase web config is public by design; access is governed by
the rules below). Uses a Google OAuth access token in RB_TOKEN.

    RB_TOKEN=... python firebase/setup_firestore.py <project-id> firebase/public
"""
import json
import os
import sys
import time
from pathlib import Path

import httpx

PROJECT, PUBLIC = sys.argv[1], Path(sys.argv[2])
H = {"Authorization": f"Bearer {os.environ['RB_TOKEN']}", "X-Goog-User-Project": PROJECT,
     "Content-Type": "application/json"}
FB = "https://firebase.googleapis.com/v1beta1"
RULES_API = "https://firebaserules.googleapis.com/v1"

# Officer decisions only: create and read, fixed fields and values, nothing else in the database.
RULES = """rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /decisions/{id} {
      allow read: if true;
      allow create: if request.resource.data.keys().hasOnly(['case_id', 'bank', 'decision', 'reason', 'ts'])
        && request.resource.data.bank in ['BANK_A', 'BANK_B', 'BANK_C']
        && request.resource.data.decision in ['approve', 'reject', 'more_evidence']
        && request.resource.data.case_id is string && request.resource.data.case_id.size() <= 40
        && request.resource.data.reason is string && request.resource.data.reason.size() <= 500
        && request.resource.data.ts == request.time;
      allow update, delete: if false;
    }
    match /{document=**} {
      allow read, write: if false;
    }
  }
}
"""


def call(method, url, **kw):
    r = httpx.request(method, url, headers=H, timeout=120, **kw)
    if r.status_code >= 400:
        raise SystemExit(f"{method} {url} -> {r.status_code}: {r.text[:600]}")
    return r.json() if r.content else {}


apps = call("GET", f"{FB}/projects/{PROJECT}/webApps").get("apps", [])
app = next((a for a in apps if a.get("displayName") == "Ring Breaker web"), None)
if not app:
    op = call("POST", f"{FB}/projects/{PROJECT}/webApps", json={"displayName": "Ring Breaker web"})
    for _ in range(40):
        op = call("GET", f"{FB}/{op['name']}")
        if op.get("done"):
            break
        time.sleep(3)
    app = op["response"]
cfg = call("GET", f"{FB}/projects/{PROJECT}/webApps/{app['appId']}/config")
(PUBLIC / "data").mkdir(parents=True, exist_ok=True)
(PUBLIC / "data" / "firebase-config.json").write_text(json.dumps(cfg, indent=1), encoding="utf-8")
print("web app:", app["appId"])

ruleset = call("POST", f"{RULES_API}/projects/{PROJECT}/rulesets",
               json={"source": {"files": [{"name": "firestore.rules", "content": RULES}]}})
release = f"projects/{PROJECT}/releases/cloud.firestore"
body = {"release": {"name": release, "rulesetName": ruleset["name"]}}
r = httpx.patch(f"{RULES_API}/{release}", headers=H, json=body, timeout=60)
if r.status_code == 404:
    call("POST", f"{RULES_API}/projects/{PROJECT}/releases", json=body["release"])
elif r.status_code >= 400:
    raise SystemExit(f"rules release -> {r.status_code}: {r.text[:400]}")
print("rules released:", ruleset["name"])
