import json
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


def direction_is(signal, key, direction):
    value = signal.get(key)
    return isinstance(value, dict) and value.get("direction") == direction


def run_variant(name, candidates, predicate, d1, h4):
    selected = [s for s in candidates if predicate(s)]

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
        "raw_selected": len(selected),
        "unique_signals": len(result["signals"]),
        "trades_simulated": len(result["results"]),
        "wins": result["wins"],
        "losses": result["losses"],
        "partials": result["partials"],
        "timeouts": result["timeouts"],
        "no_entries": result["no_entries"],
        "resolved": result["resolved"],
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

    print("Generating historical MTF candidates...")
    candidates = historical_mtf_events(d1, h4)

    variants = {
        "A_BASELINE_BEARISH": lambda s:
            s.get("direction") == "bearish",

        "B_BEARISH_SWEEP": lambda s:
            s.get("direction") == "bearish"
            and direction_is(s, "sweep", "bearish"),

        "C_BULLISH_SWEEP": lambda s:
            s.get("direction") == "bearish"
            and direction_is(s, "sweep", "bullish"),
    }

    report = {
        "phase": "5B",
        "dataset": {
            "d1_candles": len(d1),
            "h4_candles": len(h4),
            "d1_start": str(d1[0]["timestamp"]),
            "d1_end": str(d1[-1]["timestamp"]),
            "h4_start": str(h4[0]["timestamp"]),
            "h4_end": str(h4[-1]["timestamp"]),
        },
        "parameters": {
            "starting_equity": STARTING_EQUITY,
            "risk_pct": RISK_PCT,
            "min_rr": MIN_RR,
            "fee_rate": FEE_RATE,
            "slippage_bps": SLIPPAGE_BPS,
        },
        "raw_candidates": len(candidates),
        "variants": {},
    }

    print("")
    print("=== PHASE 5B | LONG HISTORY | BTC ===")
    print(f"D1 candles      : {len(d1)}")
    print(f"H4 candles      : {len(h4)}")
    print(f"Raw candidates  : {len(candidates)}")
    print(f"RR              : 1:{MIN_RR}")
    print(f"Risk            : {RISK_PCT * 100:.2f}%")
    print(f"Fee             : {FEE_RATE * 100:.3f}%")
    print(f"Slippage        : {SLIPPAGE_BPS:.1f} bps")
    print("")

    for name, predicate in variants.items():
        print(f"Running {name}...")

        result = run_variant(
            name,
            candidates,
            predicate,
            d1,
            h4,
        )

        report["variants"][name] = result

        print(
            f"  SIG={result['unique_signals']} "
            f"RES={result['resolved']} "
            f"WR={result['win_rate_pct']:.2f}% "
            f"PF={result['profit_factor']:.3f} "
            f"ExpR={result['expectancy_r']:.3f} "
            f"PnL=${result['pnl']:.2f} "
            f"DD=${result['max_drawdown']:.2f}"
        )
        print("")

    output = ROOT / "phase5b_results.json"

    output.write_text(
        json.dumps(
            report,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    print(f"Saved: {output}")
    print("")
    print("Research/backtest only.")
    print("No live execution.")


if __name__ == "__main__":
    main()
