import json
from datetime import timedelta
from pathlib import Path

from trading_agent.backtest_mtf import run_mtf_backtest
from trading_agent.data import load_csv
from trading_agent.mtf import historical_mtf_events


ROOT = Path(__file__).resolve().parents[1]
D1_PATH = ROOT / "examples" / "BTCUSDT_1d_3y.csv"
H4_PATH = ROOT / "examples" / "BTCUSDT_4h_3y.csv"

STARTING_EQUITY = 10_000.0
RISK_PCT = 0.005
MIN_RR = 2.25
FEE_RATE = 0.0004
SLIPPAGE_BPS = 2.0


def bullish_sweep_bearish(signal):
    sweep = signal.get("sweep")
    return (
        signal.get("direction") == "bearish"
        and isinstance(sweep, dict)
        and sweep.get("direction") == "bullish"
    )


def run_period(name, candidates, start, end, d1, h4):
    selected = []

    for s in candidates:
        idx = s.get("index")
        if not isinstance(idx, int) or idx < 0 or idx >= len(h4):
            continue

        ts = h4[idx]["timestamp"]

        if start <= ts < end and bullish_sweep_bearish(s):
            selected.append(s)

    result = run_mtf_backtest(
        d1,
        h4,
        starting_equity=STARTING_EQUITY,
        risk_pct=RISK_PCT,
        min_rr=MIN_RR,
        fee_rate=FEE_RATE,
        slippage_bps=SLIPPAGE_BPS,
        candidates_override=selected,
    )

    return {
        "name": name,
        "signals": len(result["signals"]),
        "resolved": result["resolved"],
        "wins": result["wins"],
        "losses": result["losses"],
        "partials": result["partials"],
        "no_entries": result["no_entries"],
        "win_rate_pct": result["win_rate"],
        "profit_factor": result["profit_factor"],
        "expectancy_r": result["expectancy_r"],
        "pnl": result["net_pnl"],
        "return_pct": result["net_return_pct"],
        "max_drawdown": result["max_drawdown"],
    }


def main():
    d1 = load_csv(str(D1_PATH))
    h4 = load_csv(str(H4_PATH))
    candidates = historical_mtf_events(d1, h4)

    first = h4[0]["timestamp"]
    last = h4[-1]["timestamp"]

    periods = []

    # Calendar-year validation
    for year in range(first.year, last.year + 1):
        start = first.replace(year=year, month=1, day=1)
        end = start.replace(year=year + 1)
        periods.append((f"YEAR_{year}", start, end))

    # Rolling 6-month OOS windows
    cursor = first.replace(month=1, day=1)
    while cursor < last:
        end = cursor + timedelta(days=183)
        if end > first and cursor < last:
            periods.append((f"ROLLING_6M_{cursor.date()}_{end.date()}", cursor, end))
        cursor = end

    report = {
        "phase": "5C",
        "strategy": "BEARISH + BULLISH SWEEP",
        "dataset": {
            "d1_candles": len(d1),
            "h4_candles": len(h4),
            "start": str(first),
            "end": str(last),
        },
        "parameters": {
            "starting_equity": STARTING_EQUITY,
            "risk_pct": RISK_PCT,
            "min_rr": MIN_RR,
            "fee_rate": FEE_RATE,
            "slippage_bps": SLIPPAGE_BPS,
        },
        "results": [],
    }

    print("\n=== PHASE 5C | BTC | BULLISH SWEEP VALIDATION ===")
    print(f"H4 candles : {len(h4)}")
    print(f"RR         : 1:{MIN_RR}")
    print(f"Risk       : {RISK_PCT * 100:.2f}%")
    print("")

    for name, start, end in periods:
        if start >= last:
            continue

        result = run_period(
            name,
            candidates,
            start,
            end,
            d1,
            h4,
        )

        report["results"].append(result)

        print(
            f"{name}: "
            f"SIG={result['signals']} "
            f"RES={result['resolved']} "
            f"WR={result['win_rate_pct']:.2f}% "
            f"PF={result['profit_factor']:.3f} "
            f"ExpR={result['expectancy_r']:.3f} "
            f"PnL=${result['pnl']:.2f} "
            f"DD=${result['max_drawdown']:.2f}"
        )

    output = ROOT / "phase5c_results.json"
    output.write_text(
        json.dumps(report, indent=2, default=str),
        encoding="utf-8",
    )

    print(f"\nSaved: {output}")
    print("Research/backtest only.")
    print("No live execution.")


if __name__ == "__main__":
    main()
