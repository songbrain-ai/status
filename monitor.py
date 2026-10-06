"""Songbrain uptime monitor — runs on GitHub Actions every 5 minutes.

Checks the public endpoints from outside our own infrastructure, appends the
result to history/<YYYY-MM>.json (daily counters per component) and rebuilds
summary.json, which https://www.songbrain.ai/status renders. Standard library
only. Uptime counts "degraded" as up (the service answers) but marks the day.
"""
from __future__ import annotations

import datetime as dt
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
HIST = ROOT / "history"
UA = {"User-Agent": "SongbrainStatusMonitor/1.0 (+https://www.songbrain.ai/status)"}

COMPONENTS = [
    ("api", "API"),
    ("pipeline", "Analysis pipeline"),
    ("webhooks", "Webhooks"),
    ("website", "Website & docs"),
    ("console", "Developer console"),
]


def fetch(url: str, timeout: int = 15):
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            body = r.read(200_000)
            return r.status, body, int((time.perf_counter() - t0) * 1000)
    except urllib.error.HTTPError as e:
        return e.code, b"", int((time.perf_counter() - t0) * 1000)
    except Exception:
        return None, b"", int((time.perf_counter() - t0) * 1000)


def check() -> dict:
    out = {}
    code, body, ms = fetch("https://api.songbrain.ai/v1/status")
    if code == 200:
        try:
            st = json.loads(body)
            comps = st.get("components") or {}
            out["api"] = "operational"
            out["pipeline"] = comps.get("pipeline", "operational")
            out["webhooks"] = comps.get("webhooks", "operational")
        except Exception:
            out.update(api="degraded", pipeline="degraded", webhooks="degraded")
    else:
        # one retry: a single dropped packet is not an outage
        time.sleep(10)
        code2, _, ms = fetch("https://api.songbrain.ai/v1/examples")
        state = "degraded" if code2 == 200 else "down"
        out.update(api=state, pipeline=state, webhooks=state)
    out["_api_ms"] = ms
    code, _, _ = fetch("https://www.songbrain.ai/api-access")
    out["website"] = "operational" if code == 200 else "down"
    code, _, _ = fetch("https://app.songbrain.ai/login")
    out["console"] = "operational" if code == 200 else "down"
    return out


def record(res: dict, now: dt.datetime) -> None:
    HIST.mkdir(exist_ok=True)
    f = HIST / f"{now:%Y-%m}.json"
    data = json.loads(f.read_text()) if f.exists() else {}
    day = data.setdefault(f"{now:%Y-%m-%d}", {})
    for cid, _ in COMPONENTS:
        c = day.setdefault(cid, {"checks": 0, "operational": 0, "degraded": 0, "down": 0})
        c["checks"] += 1
        c[res.get(cid, "down")] = c.get(res.get(cid, "down"), 0) + 1
    lat = day.setdefault("_api_ms", [])
    lat.append(res.get("_api_ms", 0))
    del lat[:-300]
    f.write_text(json.dumps(data, separators=(",", ":"), sort_keys=True))

    # incidents: a component down in two checks in a row opens one; the next
    # non-down check closes it.
    inc_f = ROOT / "incidents.json"
    incs = json.loads(inc_f.read_text()) if inc_f.exists() else {"open": {}, "last": {}, "list": []}
    stamp = now.replace(microsecond=0).isoformat() + "Z"
    for cid, name in COMPONENTS:
        state = res.get(cid, "down")
        prev = incs["last"].get(cid)
        if state == "down" and prev == "down" and cid not in incs["open"]:
            incs["open"][cid] = {"component": cid, "name": name, "started": incs.get("last_at", stamp)}
        if state != "down" and cid in incs["open"]:
            item = incs["open"].pop(cid)
            item["resolved"] = stamp
            incs["list"].insert(0, item)
        incs["last"][cid] = state
    incs["last_at"] = stamp
    incs["list"] = incs["list"][:30]
    inc_f.write_text(json.dumps(incs, indent=1))


def summarize(now: dt.datetime, res: dict) -> None:
    days = {}
    for f in sorted(HIST.glob("*.json")):
        days.update(json.loads(f.read_text()))
    start = (now - dt.timedelta(days=89)).date()
    comps = []
    for cid, name in COMPONENTS:
        series, up_sum, chk_sum = [], 0, 0
        for i in range(90):
            d = (start + dt.timedelta(days=i)).isoformat()
            c = (days.get(d) or {}).get(cid)
            if not c or not c.get("checks"):
                series.append({"date": d, "uptime": None, "checks": 0})
                continue
            up = c.get("operational", 0) + c.get("degraded", 0)
            up_sum += up
            chk_sum += c["checks"]
            series.append({"date": d, "uptime": round(100.0 * up / c["checks"], 2), "checks": c["checks"],
                           "degraded": c.get("degraded", 0)})
        comps.append({"id": cid, "name": name, "current": res.get(cid, "down"),
                      "uptime_90d": round(100.0 * up_sum / chk_sum, 3) if chk_sum else None, "days": series})
    incs = json.loads((ROOT / "incidents.json").read_text())
    summary = {
        "updated": now.replace(microsecond=0).isoformat() + "Z",
        "interval_min": 5,
        "components": comps,
        "open_incidents": list(incs["open"].values()),
        "incidents": incs["list"],
    }
    (ROOT / "summary.json").write_text(json.dumps(summary, separators=(",", ":")))


if __name__ == "__main__":
    now = dt.datetime.utcnow()
    res = check()
    record(res, now)
    summarize(now, res)
    print(json.dumps(res))
