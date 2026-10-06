#!/usr/bin/env python3
"""Phase 6A reproducibility gate; research/backtest only."""
from __future__ import annotations
import hashlib, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D1 = ROOT / "examples" / "BTCUSDT_1d_3y.csv"
H4 = ROOT / "examples" / "BTCUSDT_4h_3y.csv"
OUT = ROOT / "phase6a_reproducibility_report.json"

BASELINE = {
    "risk_pct": 0.005,
    "fee_rate": 0.0004,
    "slippage_bps": 2.0,
    "min_rr": 2.25,
    "max_bars": 30,
}

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def fingerprint(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    return {
        "rows": max(0, len(lines) - 1),
        "sha256": sha256(path),
        "header": lines[0] if lines else "",
        "first_row": lines[1] if len(lines) > 1 else "",
        "last_row": lines[-1] if len(lines) > 1 else "",
    }

def main():
    required = [
        D1, H4,
        ROOT / "scripts/phase5b_long_history.py",
        ROOT / "trading_agent/backtest_mtf.py",
        ROOT / "trading_agent/mtf.py",
        ROOT / "trading_agent/strategy.py",
    ]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.exists()]
    report = {
        "phase": "6A",
        "status": "PASS",
        "frozen_baseline": BASELINE,
        "datasets": {},
        "missing": missing,
        "compileall": None,
        "phase5b": None,
    }

    if missing:
        report["status"] = "FAIL"
        report["reason"] = "required reproducibility inputs are missing"
        OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 1

    report["datasets"] = {"d1": fingerprint(D1), "h4": fingerprint(H4)}

    c = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", "trading_agent", "scripts"],
        cwd=ROOT, text=True, capture_output=True
    )
    report["compileall"] = {"returncode": c.returncode, "stderr": c.stderr[-4000:]}
    if c.returncode:
        report["status"] = "FAIL"
        report["reason"] = "compileall failed"

    if report["status"] == "PASS":
        r = subprocess.run(
            [sys.executable, "scripts/phase5b_long_history.py"],
            cwd=ROOT, text=True, capture_output=True
        )
        report["phase5b"] = {
            "returncode": r.returncode,
            "stdout_tail": r.stdout[-6000:],
            "stderr_tail": r.stderr[-4000:],
        }
        if r.returncode:
            report["status"] = "FAIL"
            report["reason"] = "Phase 5B smoke test failed"

    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
