"""Test de charge GA-OPERATIONS : requetes concurrentes, latences p50/p95.

Usage : python tools/load_test.py --users 30 --seconds 15
Resultat : data/load_test_report.json + resume console.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

import httpx

ADMIN = ("admin", "GAt Admin#2026")
ENDPOINTS = ["/api/health", "/api/dashboard/summary", "/api/alerts?limit=20", "/api/events?limit=20"]


async def worker(client: httpx.AsyncClient, token: str, deadline: float, latencies: list) -> None:
    paths = [p for p in ENDPOINTS if p != "/api/health"] or ["/api/health"]
    i = 0
    while time.monotonic() < deadline:
        start = time.monotonic()
        try:
            response = await client.get(paths[i % len(paths)],
                                        headers={"Authorization": f"Bearer {token}"})
            _ = response.status_code
        except httpx.HTTPError:
            pass
        latencies.append(time.monotonic() - start)
        i += 1
        await asyncio.sleep(0.02)


async def run(users: int, seconds: int, base_url: str) -> dict:
    latencies: list[float] = []
    errors = 0
    async with httpx.AsyncClient(base_url=base_url, timeout=10) as client:
        try:
            response = await client.post("/api/auth/login", json={"username": ADMIN[0], "password": ADMIN[1]})
            token = response.json()["token"]
        except (httpx.HTTPError, KeyError):
            return {"erreur": f"connexion impossible sur {base_url} — lancer 'python -m ga.cli serve'"}
        deadline = time.monotonic() + seconds
        started = time.monotonic()
        results = await asyncio.gather(
            *[worker(client, token, deadline, latencies) for _ in range(users)],
            return_exceptions=True)
        errors = sum(1 for r in results if isinstance(r, Exception))
    latencies.sort()
    report = {
        "url": base_url, "utilisateurs": users, "duree_s": seconds,
        "requetes": len(latencies), "erreurs": errors,
        "debit_rps": round(len(latencies) / seconds, 1),
        "latence_p50_ms": round(statistics.median(latencies) * 1000, 1) if latencies else None,
        "latence_p95_ms": round(latencies[int(len(latencies) * 0.95)] * 1000, 1) if len(latencies) > 20 else None,
        "latence_max_ms": round(max(latencies) * 1000, 1) if latencies else None,
    }
    Path("data").mkdir(exist_ok=True)
    Path("data/load_test_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=int, default=30)
    parser.add_argument("--seconds", type=int, default=15)
    parser.add_argument("--url", default="http://localhost:8000")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.users, args.seconds, args.url)), indent=2))
