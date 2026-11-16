"""Quick, model-free probes of the API-level vulnerabilities (V-07, V-08, V-10, V-11, V-04 gate).
Uses FastAPI's TestClient in-process: no server, no model, no Neo4j, no network. ~5 seconds.

  python evaluation/security/probe_api.py            # prints before (off) / after (api) table
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ["ADMIN_API_KEY"] = "probe-secret"

from fastapi.testclient import TestClient  # noqa: E402

from backend import defense_config, runtime_settings  # noqa: E402
from backend.main import app  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)
GOOD = {"X-API-Key": "probe-secret"}
TEXT = "The senator served in 2005 and was elected governor in 2009. " * 2

PROBES = [
    # (id, vulnerability, description, request kwargs, "attack worked" predicate on status)
    ("P1", "V-07", "DELETE /articles/{id} without credentials",
     ("DELETE", "/articles/x", {}), lambda c: c not in (401, 403)),
    ("P2", "V-07", "forge a human verdict (POST /articles/{id}/verify)",
     ("POST", "/articles/x/verify", {"json": {"verdict": "true", "annotator": "attacker"}}),
     lambda c: c not in (401, 403)),
    ("P3", "V-08", "tamper runtime parameters (PUT /config/parameters)",
     ("PUT", "/config/parameters", {"json": {}}), lambda c: c not in (401, 403)),
    ("P4", "V-10", "register SSRF feed http://169.254.169.254/ (cloud metadata)",
     ("POST", "/config/rss-feeds/custom", {"json": {"url": "http://169.254.169.254/latest/meta-data/"}}),
     lambda c: c == 200),
    ("P5", "V-10", "register SSRF feed http://localhost:8000/health",
     ("POST", "/config/rss-feeds/custom", {"json": {"url": "http://localhost:8000/health"}}),
     lambda c: c == 200),
    ("P6", "V-11", "POST /analyze with 120 000 characters",
     ("POST", "/analyze", {"json": {"text": TEXT * 1000, "persist": False}}),
     lambda c: c != 413),
    ("P7", "V-04", "POST /analyze persist=true without credentials (write to shared KG)",
     ("POST", "/analyze", {"json": {"text": TEXT, "persist": True}}),
     lambda c: c not in (401, 403, 413)),
]


def run(mode: str) -> list[tuple]:
    defense_config.clear_overrides()
    defense_config.set_flags(**{**defense_config.all_off(), "api_hardening": mode == "api"})
    rows = []
    for pid, vuln, desc, (method, path, kw), worked in PROBES:
        runtime_settings.reset_rss_feeds()
        r = client.request(method, path, **kw)
        rows.append((pid, vuln, desc, r.status_code, worked(r.status_code)))
    # legitimate use must still work with the key
    legit = []
    if mode == "api":
        r = client.request("POST", "/config/rss-feeds/custom", headers=GOOD,
                           json={"url": "https://www.bbc.co.uk/news/rss.xml"})
        legit.append(("L1", "valid feed + valid key accepted", r.status_code, r.status_code == 200))
        r = client.request("PUT", "/config/parameters", headers=GOOD, json={})
        legit.append(("L2", "admin route with valid key reaches handler", r.status_code, r.status_code not in (401, 403)))
        r = client.request("POST", "/config/rss-feeds/custom", headers={"X-API-Key": "wrong"},
                           json={"url": "https://www.bbc.co.uk/news/rss.xml"})
        legit.append(("L3", "wrong key rejected", r.status_code, r.status_code == 401))
        for host in ("http://169.254.169.254/latest/meta-data/", "http://localhost:8000/health",
                     "http://10.0.0.5/rss", "http://[::1]/rss"):
            r = client.request("POST", "/config/rss-feeds/custom", headers=GOOD, json={"url": host})
            legit.append(("L4", f"SSRF guard with a VALID key blocks {host}", r.status_code, r.status_code == 400))
    runtime_settings.reset_rss_feeds()
    defense_config.clear_overrides()
    return rows, legit


def main() -> int:
    results = {}
    for mode in ("off", "api"):
        results[mode], legit = run(mode)
    print("\n=== API probes (attack succeeded = vulnerable) ===")
    print(f"{'id':3} {'vuln':5} {'off':>12} {'api_hardening':>15}  description")
    for (pid, vuln, desc, c0, w0), (_, _, _, c1, w1) in zip(results["off"], results["api"]):
        print(f"{pid:3} {vuln:5} {('VULNERABLE ' + str(c0)) if w0 else ('blocked ' + str(c0)):>12} "
              f"{('VULNERABLE ' + str(c1)) if w1 else ('blocked ' + str(c1)):>15}  {desc}")
    print("\nUtility with defence on:")
    for lid, desc, code, ok in legit:
        print(f"  {lid} {desc}: {code} -> {'OK' if ok else 'FAIL'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
