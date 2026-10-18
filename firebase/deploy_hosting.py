"""Deploy firebase/public to Firebase Hosting through the Hosting REST API (no Firebase CLI needed).

Uses a Google OAuth access token (for example `gcloud auth print-access-token`) passed in RB_TOKEN.

    RB_TOKEN=... python firebase/deploy_hosting.py <project-id> firebase/public
"""
import gzip
import hashlib
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
HOST = "https://firebasehosting.googleapis.com/v1beta1"


def call(method, url, **kw):
    r = httpx.request(method, url, headers=H, timeout=120, **kw)
    if r.status_code >= 400:
        raise SystemExit(f"{method} {url} -> {r.status_code}: {r.text[:600]}")
    return r.json() if r.content else {}


def wait(op_name):
    for _ in range(60):
        op = call("GET", f"{FB}/{op_name}")
        if op.get("done"):
            if "error" in op:
                raise SystemExit(f"operation failed: {op['error']}")
            return op
        time.sleep(3)
    raise SystemExit("operation timed out")


# 1. Make the Google Cloud project a Firebase project (free Spark plan; no billing needed).
proj = httpx.get(f"{FB}/projects/{PROJECT}", headers=H, timeout=60)
if proj.status_code == 404 or (proj.status_code == 403 and "not found" in proj.text.lower()):
    print("adding Firebase to", PROJECT)
    wait(call("POST", f"{FB}/projects/{PROJECT}:addFirebase", json={})["name"])
elif proj.status_code >= 400:
    raise SystemExit(f"GET project -> {proj.status_code}: {proj.text[:600]}")

# 2. The default Hosting site.
sites = call("GET", f"{HOST}/projects/{PROJECT}/sites").get("sites", [])
site = next((s for s in sites if s.get("type") == "DEFAULT_SITE"), sites[0] if sites else None)
if not site:
    site = call("POST", f"{HOST}/projects/{PROJECT}/sites?siteId={PROJECT}", json={})
site_name = site["name"].split("/sites/")[-1]
print("site:", site_name, site.get("defaultUrl"))

# 3. New version, with files, then finalize and release.
version = call("POST", f"{HOST}/sites/{site_name}/versions", json={"config": {
    "headers": [{"glob": "/data/**", "headers": {"Cache-Control": "no-cache"}}]}})
vname = version["name"]
blobs, files = {}, {}
for f in sorted(p for p in PUBLIC.rglob("*") if p.is_file()):
    gz = gzip.compress(f.read_bytes(), mtime=0)
    digest = hashlib.sha256(gz).hexdigest()
    files["/" + f.relative_to(PUBLIC).as_posix()] = digest
    blobs[digest] = gz
pop = call("POST", f"{HOST}/{vname}:populateFiles", json={"files": files})
for digest in pop.get("uploadRequiredHashes", []):
    r = httpx.post(f"{pop['uploadUrl']}/{digest}", content=blobs[digest], timeout=120,
                   headers={"Authorization": H["Authorization"], "X-Goog-User-Project": PROJECT,
                            "Content-Type": "application/octet-stream"})
    if r.status_code >= 400:
        raise SystemExit(f"upload {digest} -> {r.status_code}: {r.text[:300]}")
print(f"uploaded {len(pop.get('uploadRequiredHashes', []))} of {len(files)} files")
call("PATCH", f"{HOST}/{vname}?update_mask=status", json={"status": "FINALIZED"})
call("POST", f"{HOST}/sites/{site_name}/releases?versionName={vname}", json={})
print("released:", site.get("defaultUrl") or f"https://{site_name}.web.app")
