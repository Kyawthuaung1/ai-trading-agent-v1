from .mtf import historical_mtf_events


def atr(c, period=14):
    if len(c) < period + 1:
        return 0.0

    trs = []

    for i in range(1, len(c)):
        high = c[i]["high"]
        low = c[i]["low"]
        prev_close = c[i - 1]["close"]

        trs.append(
            max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close),
            )
        )

    return sum(trs[-period:]) / period


def deduplicate_candidates(candidates, min_gap=6):
    result = []
    last_index = -999999

    for signal in sorted(candidates, key=lambda x: x["index"]):
        if signal["index"] - last_index < min_gap:
            continue

        result.append(signal)
        last_index = signal["index"]

    return result


def build_trade(signal, candles, min_rr=2.0):
    ob = signal.get("order_block")

    if not ob:
        return None

    direction = signal["direction"]
    index = signal["index"]

    if index >= len(candles) - 1:
        return None

    # Use the OB midpoint as a limit entry.
    entry = (ob["low"] + ob["high"]) / 2.0

    a = atr(candles[: index + 1])

    if a <= 0:
        a = abs(ob["high"] - ob["low"])

    if a <= 0:
        return None

    if direction == "bullish":
        stop = ob["low"] - a * 0.25
        risk = entry - stop

        if risk <= 0:
            return None

        tp1 = entry + risk * 1.0
        tp2 = entry + risk * min_rr
        tp3 = entry + risk * 3.0

    else:
        stop = ob["high"] + a * 0.25
        risk = stop - entry

        if risk <= 0:
            return None

        tp1 = entry - risk * 1.0
        tp2 = entry - risk * min_rr
        tp3 = entry - risk * 3.0

    return {
        "direction": direction,
        "entry": entry,
        "stop": stop,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "risk": risk,
        "signal_index": index,
    }


def execution_price(price, direction, slippage_bps):
    """
    Approximate execution slippage.

    Long:
      buy  -> slightly higher
      sell -> slightly lower

    Short:
      sell -> slightly lower
      buy  -> slightly higher
    """

    slip = price * slippage_bps / 10000.0

    if direction == "bullish":
        return price + slip

    return price - slip


def fee(notional, fee_rate):
    return notional * fee_rate


def simulate_trade(
    candles,
    trade,
    starting_equity,
    risk_pct=0.005,
    fee_rate=0.0004,
    slippage_bps=2.0,
    max_bars=30,
):
    """
    Realistic-ish multi-target simulation.

    Position allocation:
      TP1 = 50%
      TP2 = 30%
      TP3 = 20%

    After TP1:
      remaining stop -> breakeven.

    Conservative same-candle rule:
      If SL and a TP are both touched on the same candle,
      SL is assumed to happen first.

    Returns R-multiple and dollar P&L.
    """

    start = trade["signal_index"] + 1
    end = min(len(candles), start + max_bars)

    direction = trade["direction"]

    entry = trade["entry"]
    stop = trade["stop"]

    tp1 = trade["tp1"]
    tp2 = trade["tp2"]
    tp3 = trade["tp3"]

    initial_risk_price = trade["risk"]

    if initial_risk_price <= 0:
        return {
            "result": "INVALID",
            "r_multiple": 0.0,
            "pnl": 0.0,
            "exit_index": start,
            "targets_hit": [],
        }

    # 0.5% equity risk.
    risk_amount = starting_equity * risk_pct

    # Position size in base asset.
    position_size = risk_amount / initial_risk_price

    # 50 / 30 / 20 allocation.
    allocations = {
        "TP1": 0.50,
        "TP2": 0.30,
        "TP3": 0.20,
    }

    entered = False
    targets_hit = []

    remaining = 1.0
    current_stop = stop

    gross_pnl = 0.0
    total_fees = 0.0
    total_slippage = 0.0

    entry_price_actual = None

    for i in range(start, end):
        candle = candles[i]

        high = candle["high"]
        low = candle["low"]

        # --------------------------------------------------
        # ENTRY
        # --------------------------------------------------

        if not entered:
            if low <= entry <= high:
                entered = True

                entry_price_actual = execution_price(
                    entry,
                    "bullish" if direction == "bullish" else "bearish",
                    slippage_bps,
                )

                entry_notional = position_size * entry_price_actual

                entry_fee = fee(entry_notional, fee_rate)
                total_fees += entry_fee

                total_slippage += abs(
                    entry_price_actual - entry
                ) * position_size

            else:
                continue

        # --------------------------------------------------
        # STOP
        # --------------------------------------------------

        if direction == "bullish":
            hit_stop = low <= current_stop
        else:
            hit_stop = high >= current_stop

        # Conservative assumption:
        # if stop and target happen in same candle,
        # stop happens first.
        if hit_stop:
            exit_price = execution_price(
                current_stop,
                "bullish" if direction == "bearish" else "bearish",
                slippage_bps,
            )

            close_size = position_size * remaining

            if direction == "bullish":
                pnl = (exit_price - entry_price_actual) * close_size
            else:
                pnl = (entry_price_actual - exit_price) * close_size

            gross_pnl += pnl

            exit_notional = close_size * exit_price
            total_fees += fee(exit_notional, fee_rate)

            total_slippage += abs(
                exit_price - current_stop
            ) * close_size

            net_pnl = gross_pnl - total_fees

            r_multiple = net_pnl / risk_amount

            if targets_hit:
                result = "PARTIAL"
            else:
                result = "LOSS"

            return {
                "result": result,
                "r_multiple": r_multiple,
                "pnl": net_pnl,
                "gross_pnl": gross_pnl,
                "fees": total_fees,
                "slippage_cost": total_slippage,
                "exit_index": i,
                "targets_hit": targets_hit,
                "position_size": position_size,
            }

        # --------------------------------------------------
        # TP1
        # --------------------------------------------------

        if "TP1" not in targets_hit:
            hit = (
                high >= tp1
                if direction == "bullish"
                else low <= tp1
            )

            if hit:
                close_size = position_size * allocations["TP1"]

                exit_price = execution_price(
                    tp1,
                    "bullish" if direction == "bearish" else "bearish",
                    slippage_bps,
                )

                if direction == "bullish":
                    pnl = (
                        exit_price - entry_price_actual
                    ) * close_size
                else:
                    pnl = (
                        entry_price_actual - exit_price
                    ) * close_size

                gross_pnl += pnl

                exit_notional = close_size * exit_price
                total_fees += fee(exit_notional, fee_rate)

                total_slippage += abs(
                    exit_price - tp1
                ) * close_size

                targets_hit.append("TP1")
                remaining -= allocations["TP1"]

                # Move remaining position to breakeven.
                current_stop = entry_price_actual

        # --------------------------------------------------
        # TP2
        # --------------------------------------------------

        if "TP2" not in targets_hit:
            hit = (
                high >= tp2
                if direction == "bullish"
                else low <= tp2
            )

            if hit:
                close_size = position_size * allocations["TP2"]

                exit_price = execution_price(
                    tp2,
                    "bullish" if direction == "bearish" else "bearish",
                    slippage_bps,
                )

                if direction == "bullish":
                    pnl = (
                        exit_price - entry_price_actual
                    ) * close_size
                else:
                    pnl = (
                        entry_price_actual - exit_price
                    ) * close_size

                gross_pnl += pnl

                exit_notional = close_size * exit_price
                total_fees += fee(exit_notional, fee_rate)

                total_slippage += abs(
                    exit_price - tp2
                ) * close_size

                targets_hit.append("TP2")
                remaining -= allocations["TP2"]

        # --------------------------------------------------
        # TP3
        # --------------------------------------------------

        if "TP3" not in targets_hit:
            hit = (
                high >= tp3
                if direction == "bullish"
                else low <= tp3
            )

            if hit:
                close_size = position_size * allocations["TP3"]

                exit_price = execution_price(
                    tp3,
                    "bullish" if direction == "bearish" else "bearish",
                    slippage_bps,
                )

                if direction == "bullish":
                    pnl = (
                        exit_price - entry_price_actual
                    ) * close_size
                else:
                    pnl = (
                        entry_price_actual - exit_price
                    ) * close_size

                gross_pnl += pnl

                exit_notional = close_size * exit_price
                total_fees += fee(exit_notional, fee_rate)

                total_slippage += abs(
                    exit_price - tp3
                ) * close_size

                targets_hit.append("TP3")
                remaining -= allocations["TP3"]

                net_pnl = gross_pnl - total_fees
                r_multiple = net_pnl / risk_amount

                return {
                    "result": "WIN",
                    "r_multiple": r_multiple,
                    "pnl": net_pnl,
                    "gross_pnl": gross_pnl,
                    "fees": total_fees,
                    "slippage_cost": total_slippage,
                    "exit_index": i,
                    "targets_hit": targets_hit,
                    "position_size": position_size,
                }

        # If all position closed somehow.
        if remaining <= 0.000001:
            net_pnl = gross_pnl - total_fees
            r_multiple = net_pnl / risk_amount

            return {
                "result": "WIN",
                "r_multiple": r_multiple,
                "pnl": net_pnl,
                "gross_pnl": gross_pnl,
                "fees": total_fees,
                "slippage_cost": total_slippage,
                "exit_index": i,
                "targets_hit": targets_hit,
                "position_size": position_size,
            }

    # ------------------------------------------------------
    # TIMEOUT
    # ------------------------------------------------------

    if not entered:
        return {
            "result": "NO_ENTRY",
            "r_multiple": 0.0,
            "pnl": 0.0,
            "gross_pnl": 0.0,
            "fees": 0.0,
            "slippage_cost": 0.0,
            "exit_index": end - 1,
            "targets_hit": [],
            "position_size": position_size,
        }

    # Close remaining position at final candle close.
    final_close = candles[end - 1]["close"]

    exit_price = execution_price(
        final_close,
        "bullish" if direction == "bearish" else "bearish",
        slippage_bps,
    )

    close_size = position_size * remaining

    if direction == "bullish":
        pnl = (
            exit_price - entry_price_actual
        ) * close_size
    else:
        pnl = (
            entry_price_actual - exit_price
        ) * close_size

    gross_pnl += pnl

    exit_notional = close_size * exit_price
    total_fees += fee(exit_notional, fee_rate)

    total_slippage += abs(
        exit_price - final_close
    ) * close_size

    net_pnl = gross_pnl - total_fees
    r_multiple = net_pnl / risk_amount

    if targets_hit:
        result = "PARTIAL"
    else:
        result = "TIMEOUT"

    return {
        "result": result,
        "r_multiple": r_multiple,
        "pnl": net_pnl,
        "gross_pnl": gross_pnl,
        "fees": total_fees,
        "slippage_cost": total_slippage,
        "exit_index": end - 1,
        "targets_hit": targets_hit,
        "position_size": position_size,
    }


def calculate_max_drawdown(equity_curve):
    if not equity_curve:
        return 0.0

    peak = equity_curve[0]
    max_dd = 0.0

    for equity in equity_curve:
        if equity > peak:
            peak = equity

        drawdown = peak - equity

        if drawdown > max_dd:
            max_dd = drawdown

    return max_dd


def run_mtf_backtest(
    d1,
    h4,
    starting_equity=10000.0,
    risk_pct=0.005,
    min_rr=2.0,
    fee_rate=0.0004,
    slippage_bps=2.0,
):
    candidates = historical_mtf_events(d1, h4)

    signals = deduplicate_candidates(
        candidates,
        min_gap=6,
    )

    results = []

    equity = starting_equity
    equity_curve = [equity]

    wins = 0
    losses = 0
    partials = 0
    timeouts = 0
    no_entries = 0

    total_fees = 0.0
    total_gross_pnl = 0.0
    total_net_pnl = 0.0

    r_values = []

    for signal in signals:
        trade = build_trade(
            signal,
            h4,
            min_rr=min_rr,
        )

        if not trade:
            continue

        outcome = simulate_trade(
            h4,
            trade,
            starting_equity=equity,
            risk_pct=risk_pct,
            fee_rate=fee_rate,
            slippage_bps=slippage_bps,
        )

        results.append(
            {
                "signal": signal,
                "trade": trade,
                "outcome": outcome,
            }
        )

        result = outcome["result"]

        if result == "WIN":
            wins += 1

        elif result == "LOSS":
            losses += 1

        elif result == "PARTIAL":
            partials += 1

        elif result == "TIMEOUT":
            timeouts += 1

        elif result == "NO_ENTRY":
            no_entries += 1

        pnl = outcome.get("pnl", 0.0)

        equity += pnl
        equity_curve.append(equity)

        total_fees += outcome.get("fees", 0.0)
        total_gross_pnl += outcome.get("gross_pnl", 0.0)
        total_net_pnl += pnl

        if result != "NO_ENTRY":
            r_values.append(
                outcome.get("r_multiple", 0.0)
            )

    resolved = wins + losses + partials + timeouts

    profitable = sum(
        1 for r in results
        if r["outcome"].get("pnl", 0.0) > 0
    )

    losing = sum(
        1 for r in results
        if r["outcome"].get("pnl", 0.0) < 0
    )

    resolved_profit_results = [
        r["outcome"].get("pnl", 0.0)
        for r in results
        if r["outcome"]["result"] != "NO_ENTRY"
    ]

    gross_profit = sum(
        x for x in resolved_profit_results
        if x > 0
    )

    gross_loss = abs(
        sum(
            x for x in resolved_profit_results
            if x < 0
        )
    )

    profit_factor = (
        gross_profit / gross_loss
        if gross_loss > 0
        else float("inf")
    )

    expectancy_r = (
        sum(r_values) / len(r_values)
        if r_values
        else 0.0
    )

    win_rate = (
        wins / resolved * 100
        if resolved
        else 0.0
    )

    max_drawdown = calculate_max_drawdown(
        equity_curve
    )

    net_return_pct = (
        (equity - starting_equity)
        / starting_equity
        * 100
    )

    lines = [
        "=== MTF SMC BACKTEST | PHASE 4D ===",
        "",
        f"Starting equity: ${starting_equity:,.2f}",
        f"Final equity: ${equity:,.2f}",
        f"Net P&L: ${total_net_pnl:,.2f}",
        f"Net return: {net_return_pct:.2f}%",
        "",
        f"Risk/trade: {risk_pct * 100:.2f}%",
        f"Fee rate: {fee_rate * 100:.3f}%",
        f"Slippage: {slippage_bps:.1f} bps",
        f"Minimum RR: 1:{min_rr:.1f}",
        "",
        f"Raw candidates: {len(candidates)}",
        f"Unique signals: {len(signals)}",
        f"Trades simulated: {len(results)}",
        "",
        f"Wins: {wins}",
        f"Losses: {losses}",
        f"Partial/timeout: {partials + timeouts}",
        f"Timeouts: {timeouts}",
        f"No entry: {no_entries}",
        f"Resolved: {resolved}",
        f"Profitable trades: {profitable}",
        f"Losing trades: {losing}",
        "",
        f"Win rate: {win_rate:.2f}%",
        f"Profit factor: {profit_factor:.2f}",
        f"Expectancy: {expectancy_r:.3f} R",
        f"Max drawdown: ${max_drawdown:,.2f}",
        f"Total gross P&L: ${total_gross_pnl:,.2f}",
        f"Total fees: ${total_fees:,.2f}",
        "",
        "Recent trades:",
    ]

    for item in results[:15]:
        signal = item["signal"]
        trade = item["trade"]
        outcome = item["outcome"]

        lines.append(
            f"index={signal['index']} "
            f"direction={signal['direction']} "
            f"event={signal['event']['event']} "
            f"entry={trade['entry']:.2f} "
            f"SL={trade['stop']:.2f} "
            f"TP1={trade['tp1']:.2f} "
            f"TP2={trade['tp2']:.2f} "
            f"TP3={trade['tp3']:.2f} "
            f"result={outcome['result']} "
            f"R={outcome.get('r_multiple', 0.0):.3f} "
            f"P&L=${outcome.get('pnl', 0.0):.2f} "
            f"hit={','.join(outcome.get('targets_hit', [])) or '-'}"
        )

    lines.extend(
        [
            "",
            "Research/backtest only.",
            "No live execution.",
            "Historical results do not guarantee future performance.",
        ]
    )

    return {
        "candidates": candidates,
        "signals": signals,
        "results": results,
        "wins": wins,
        "losses": losses,
        "partials": partials,
        "timeouts": timeouts,
        "no_entries": no_entries,
        "resolved": resolved,
        "win_rate": win_rate,
        "starting_equity": starting_equity,
        "final_equity": equity,
        "net_pnl": total_net_pnl,
        "net_return_pct": net_return_pct,
        "profit_factor": profit_factor,
        "expectancy_r": expectancy_r,
        "max_drawdown": max_drawdown,
        "total_fees": total_fees,
        "equity_curve": equity_curve,
        "report": "\n".join(lines),
    }
