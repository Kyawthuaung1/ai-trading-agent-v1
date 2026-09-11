import json
from pathlib import Path
from datetime import datetime, timezone

from trading_agent.backtest_mtf import (
    atr,
    deduplicate_candidates,
    simulate_trade,
)
from trading_agent.mtf import historical_mtf_events


DATA_DIR = Path("examples")

D1_FILE = DATA_DIR / "BTCUSDT_1d_3y.csv"
H4_FILE = DATA_DIR / "BTCUSDT_4h_3y.csv"

STARTING_EQUITY = 10000.0
RISK_PCT = 0.005
MIN_RR = 2.25
FEE_RATE = 0.0004
SLIPPAGE_BPS = 2.0


def load_csv(path):
    import csv

    rows = []

    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(
                {
                    "timestamp": row.get("timestamp")
                    or row.get("time")
                    or row.get("datetime"),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                }
            )

    return rows


def parse_dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def build_trade_mode(signal, candles, mode):
    """
    Build a trade using one of four entry mechanisms.

    A = OB midpoint
    B = OB near edge / first-touch edge
    C = zone touch + bearish rejection
    D = zone touch + simple structure confirmation

    For C/D the original signal is transformed into a later trigger candle.
    No future information after the trigger candle is used.
    """

    direction = signal["direction"]
    original_index = signal["index"]
    ob = signal["ob"]

    if direction == "bearish":
        midpoint = (ob["low"] + ob["high"]) / 2.0
        edge = ob["low"]
    else:
        midpoint = (ob["low"] + ob["high"]) / 2.0
        edge = ob["high"]

    trigger_index = original_index

    if mode in ("C", "D"):
        trigger_index = None

        # Search only after the original signal.
        # Limit search to the same 30-bar horizon used by simulation.
        for i in range(original_index + 1, min(len(candles), original_index + 31)):
            c = candles[i]

            zone_touch = (
                c["low"] <= ob["high"]
                and c["high"] >= ob["low"]
            )

            if not zone_touch:
                continue

            bearish_rejection = (
                direction == "bearish"
                and c["close"] < c["open"]
            )

            bullish_rejection = (
                direction == "bullish"
                and c["close"] > c["open"]
            )

            if mode == "C":
                if bearish_rejection or bullish_rejection:
                    trigger_index = i
                    break

            elif mode == "D":
                if i == 0:
                    continue

                prev = candles[i - 1]

                if direction == "bearish":
                    structure_confirmed = (
                        bearish_rejection
                        and c["close"] < prev["low"]
                    )
                else:
                    structure_confirmed = (
                        bullish_rejection
                        and c["close"] > prev["high"]
                    )

                if structure_confirmed:
                    trigger_index = i
                    break

        if trigger_index is None:
            return None

    a = atr(candles[: trigger_index + 1])

    if a <= 0:
        return None

    if mode == "A":
        entry = midpoint
    elif mode == "B":
        entry = edge
    elif mode in ("C", "D"):
        entry = edge
    else:
        raise ValueError(f"Unknown mode: {mode}")

    if direction == "bullish":
        stop = ob["low"] - a * 0.25
        risk = entry - stop

        if risk <= 0:
            return None

        tp1 = entry + risk
        tp2 = entry + risk * MIN_RR
        tp3 = entry + risk * 3.0

    else:
        stop = ob["high"] + a * 0.25
        risk = stop - entry

        if risk <= 0:
            return None

        tp1 = entry - risk
        tp2 = entry - risk * MIN_RR
        tp3 = entry - risk * 3.0

    return {
        "direction": direction,
        "index": trigger_index,
        "entry": entry,
        "stop": stop,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "risk": risk,
        "signal_index": original_index,
        "entry_mode": mode,
    }


def filter_candidates(candidates):
    """
    Phase 5C strategy:
    bearish + bullish sweep and bullish + bearish sweep.
    Keep the same signal family; Phase 5D changes entry only.
    """

    selected = []

    for s in candidates:
        direction = s.get("direction")

        sweep = str(
            s.get("sweep")
            or s.get("liquidity_sweep")
            or ""
        ).lower()

        if direction == "bearish":
            if "bull" in sweep:
                selected.append(s)

        elif direction == "bullish":
            if "bear" in sweep:
                selected.append(s)

    return deduplicate_candidates(selected, min_gap=6)


def run_period(candidates, candles, start_dt=None, end_dt=None):
    selected = []

    for s in candidates:
        idx = s["index"]

        if idx < 0 or idx >= len(candles):
            continue

        ts = parse_dt(candles[idx]["timestamp"])

        if start_dt and ts < start_dt:
            continue

        if end_dt and ts >= end_dt:
            continue

        selected.append(s)

    return selected


def evaluate_variant(
    name,
    candidates,
    candles,
    start_dt=None,
    end_dt=None,
):
    period_candidates = run_period(
        candidates,
        candles,
        start_dt,
        end_dt,
    )

    transformed = []

    for signal in period_candidates:
        trade = build_trade_mode(signal, candles, name)

        if trade is not None:
            transformed.append(trade)

    transformed.sort(key=lambda x: x["index"])

    # Keep setup clusters from becoming multiple trades.
    unique = []

    last_index = -999999

    for trade in transformed:
        if trade["index"] - last_index < 6:
            continue

        unique.append(trade)
        last_index = trade["index"]

    equity = STARTING_EQUITY
    wins = 0
    losses = 0
    partials = 0
    no_entries = 0
    resolved = 0
    total_pnl = 0.0

    peak_equity = equity
    max_drawdown = 0.0

    for trade in unique:
        result = simulate_trade(
            trade,
            candles,
            starting_equity=equity,
            risk_pct=RISK_PCT,
            fee_rate=FEE_RATE,
            slippage_bps=SLIPPAGE_BPS,
        )

        if result is None:
            continue

        outcome = str(result.get("result", "")).upper()

        pnl = float(
            result.get("pnl")
            or result.get("net_pnl")
            or 0.0
        )

        total_pnl += pnl
        equity += pnl

        if outcome in ("WIN", "TP3", "FULL_WIN"):
            wins += 1
            resolved += 1
        elif outcome in ("LOSS", "SL"):
            losses += 1
            resolved += 1
        elif outcome in ("PARTIAL", "PARTIAL_WIN", "BE"):
            partials += 1
            resolved += 1
        elif outcome in ("NO_ENTRY", "NO ENTRY"):
            no_entries += 1
        else:
            # Preserve engine behavior while counting unknown outcomes
            # as unresolved rather than inventing a classification.
            pass

        peak_equity = max(peak_equity, equity)
        dd = peak_equity - equity
        max_drawdown = max(max_drawdown, dd)

    profit = 0.0
    loss_abs = 0.0

    # Re-run outcome accounting for PF / expectancy.
    equity2 = STARTING_EQUITY
    r_values = []

    for trade in unique:
        result = simulate_trade(
            trade,
            candles,
            starting_equity=equity2,
            risk_pct=RISK_PCT,
            fee_rate=FEE_RATE,
            slippage_bps=SLIPPAGE_BPS,
        )

        if result is None:
            continue

        pnl = float(
            result.get("pnl")
            or result.get("net_pnl")
            or 0.0
        )

        outcome = str(result.get("result", "")).upper()

        if outcome not in ("NO_ENTRY", "NO ENTRY"):
            equity2 += pnl

        if pnl > 0:
            profit += pnl
        elif pnl < 0:
            loss_abs += abs(pnl)

        risk_cash = max(
            1e-12,
            trade["risk"] * (
                STARTING_EQUITY * RISK_PCT
            ) / trade["risk"],
        )

        # More directly use fixed risk allocation.
        risk_cash = STARTING_EQUITY * RISK_PCT

        if outcome not in ("NO_ENTRY", "NO ENTRY"):
            r_values.append(pnl / risk_cash)

    pf = profit / loss_abs if loss_abs > 0 else None
    expectancy_r = (
        sum(r_values) / len(r_values)
        if r_values
        else 0.0
    )

    win_rate = (
        wins / resolved * 100.0
        if resolved > 0
        else 0.0
    )

    return {
        "name": name,
        "signals": len(period_candidates),
        "unique_triggers": len(unique),
        "resolved": resolved,
        "wins": wins,
        "losses": losses,
        "partials": partials,
        "no_entries": no_entries,
        "win_rate_pct": win_rate,
        "profit_factor": pf,
        "expectancy_r": expectancy_r,
        "pnl": total_pnl,
        "return_pct": (
            total_pnl / STARTING_EQUITY * 100.0
        ),
        "max_drawdown": max_drawdown,
    }


def main():
    d1 = load_csv(D1_FILE)
    h4 = load_csv(H4_FILE)

    candidates = historical_mtf_events(d1, h4)
    candidates = filter_candidates(candidates)

    modes = ["A", "B", "C", "D"]

    results = {
        "phase": "5D",
        "strategy": "BEARISH + BULLISH SWEEP",
        "purpose": "ENTRY MODEL LAB",
        "dataset": {
            "d1_candles": len(d1),
            "h4_candles": len(h4),
            "start": h4[0]["timestamp"],
            "end": h4[-1]["timestamp"],
        },
        "parameters": {
            "starting_equity": STARTING_EQUITY,
            "risk_pct": RISK_PCT,
            "min_rr": MIN_RR,
            "fee_rate": FEE_RATE,
            "slippage_bps": SLIPPAGE_BPS,
        },
        "entry_models": {
            "A": "OB midpoint",
            "B": "OB first-touch near edge",
            "C": "OB touch + rejection",
            "D": "OB touch + structure confirmation",
        },
        "full_history": {},
        "yearly": {},
        "rolling_6m": {},
    }

    # Full history
    for mode in modes:
        results["full_history"][mode] = evaluate_variant(
            mode,
            candidates,
            h4,
        )

    # Calendar years
    years = sorted(
        {
            parse_dt(h4[0]["timestamp"]).year,
            parse_dt(h4[-1]["timestamp"]).year,
        }
        | {
            parse_dt(c["timestamp"]).year
            for c in h4
        }
    )

    for year in years:
        start = datetime(year, 1, 1, tzinfo=timezone.utc)
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)

        results["yearly"][str(year)] = {}

        for mode in modes:
            results["yearly"][str(year)][mode] = evaluate_variant(
                mode,
                candidates,
                h4,
                start,
                end,
            )

    # Sequential 6-month windows, matching Phase 5C style.
    first = parse_dt(h4[0]["timestamp"])
    last = parse_dt(h4[-1]["timestamp"])

    cursor = datetime(
        first.year,
        1 if first.month <= 6 else 7,
        1,
        tzinfo=timezone.utc,
    )

    while cursor <= last:
        if cursor.month == 1:
            end = datetime(
                cursor.year,
                7,
                1,
                tzinfo=timezone.utc,
            )
        else:
            end = datetime(
                cursor.year + 1,
                1,
                1,
                tzinfo=timezone.utc,
            )

        label = (
            f"{cursor.date()}_{end.date()}"
        )

        results["rolling_6m"][label] = {}

        for mode in modes:
            results["rolling_6m"][label][mode] = evaluate_variant(
                mode,
                candidates,
                h4,
                cursor,
                end,
            )

        cursor = end

    with open("phase5d_results.json", "w", encoding="utf-8") as f:
        json.dump(
            results,
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
