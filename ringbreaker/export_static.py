"""Export a static, hostable version of the demo (Firebase Hosting free plan, no backend).

Records one real investigation from a running Ring Breaker server (the live A2A agents, policy agent and Gemini
calls) plus snapshots of the other tabs, and writes a site that replays that recorded run in the browser.

    python -m ringbreaker.export_static http://127.0.0.1:8090 firebase/public
"""
import json
import shutil
import sys
import time
from pathlib import Path

import httpx

from . import config

NOTICE = ('<p class="notice" role="note"><b>Hosted demo:</b> this page replays a real run recorded from the live '
          'Ring Breaker system (bank agents talking over A2A, the policy agent, and Gemini and Gemma via Google ADK). '
          'Long model waits are shortened. The full backend runs on Cloud Run; source code: '
          '<a href="https://github.com/Farazkhan542/ring-breaker" target="_blank" rel="noopener">GitHub</a>.</p>')


def record_run(base: str) -> list[dict]:
    events, t0 = [], time.time()
    with httpx.stream("GET", f"{base}/api/demo/run", timeout=180) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append({"t": round(time.time() - t0, 2), "ev": json.loads(line[6:])})
    return events


def main(base: str, out: Path) -> None:
    get = lambda p: httpx.get(f"{base}{p}", timeout=60).json()
    banks = get("/api/banks")
    events = record_run(base)
    kinds = [e["ev"]["type"] for e in events]
    assert "done" in kinds and "error" not in kinds, f"recorded run did not finish cleanly: {kinds[-3:]}"
    time.sleep(1)
    snapshots = {"banks": banks, "policy": get("/api/policy"), "metrics": get("/api/metrics"),
                 "audit": get("/api/audit"), "regulator": get("/api/regulator"), "demo_events": events}
    regulator = snapshots["regulator"]
    regulator["source"] = "recorded"
    if out.exists():
        shutil.rmtree(out)
    (out / "data").mkdir(parents=True)
    shutil.copytree(config.ROOT / "web", out / "static")
    index = (out / "static" / "index.html").read_text(encoding="utf-8")
    (out / "static" / "index.html").unlink()
    index = index.replace('<script src="/static/app.js"></script>',
                          '<script>window.RB_STATIC = true;</script>\n<script src="/static/app.js"></script>')
    index = index.replace('<section id="tab-investigate" class="panel-tab">',
                          '<section id="tab-investigate" class="panel-tab">\n  ' + NOTICE, 1)
    (out / "index.html").write_text(index, encoding="utf-8", newline="\n")
    for name, data in snapshots.items():
        (out / "data" / f"{name}.json").write_text(json.dumps(data, default=str), encoding="utf-8", newline="\n")
    done = next(e["ev"] for e in events if e["ev"]["type"] == "done")
    print(f"recorded {len(events)} events in {events[-1]['t']}s ({done['queries']} questions, {done['blocked']} blocked); "
          f"site written to {out}")


if __name__ == "__main__":
    main(sys.argv[1].rstrip("/"), Path(sys.argv[2]))
