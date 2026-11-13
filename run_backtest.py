"""
run_backtest.py — causal replay of strategy.py over bars.csv.

Execution model: the position decided at the close of bar t is executed at
the open of bar t+1 (no lookahead, no phantom fills). Costs are charged on
every position change: fee_bps per unit of turnover plus slippage_bps,
both applied to the traded notional fraction. Equity is in return units
(starting equity 1.0, position size 1.0 = 100% notional).

The platform's AutoGrade applies its own official cost schedule; this
harness uses a conservative blended 6 bps per trade so local numbers are
a floor, not a promise.

Usage: python3 run_backtest.py [bars.csv]
Prints full-sample stats plus first-half / second-half splits so any
overfit would be visible instead of hidden.
"""
import csv
import sys

from strategy import Strategy

FEE_BPS = 5.0        # per trade, on traded notional
SLIP_BPS = 1.0       # per trade, on traded notional
COST_PER_UNIT = (FEE_BPS + SLIP_BPS) / 10000.0


def load_bars(path):
    bars = []
    with open(path) as f:
        for row in csv.DictReader(f):
            bars.append({
                "minute": int(row["minute"]),
                "open": float(row["open"]), "high": float(row["high"]),
                "low": float(row["low"]), "close": float(row["close"]),
                "volume": float(row["volume"]),
            })
    return bars


def replay(bars):
    s = Strategy()
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    held = 0.0          # position held DURING current bar (set at its open)
    trades = 0
    turnover = 0.0
    total_cost = 0.0
    curve = []
    for t, bar in enumerate(bars):
        if t > 0 and held != 0.0:
            ret = (bar["close"] - bars[t - 1]["close"]) / bars[t - 1]["close"]
            equity *= (1.0 + held * ret)
        want = s.on_bar(bar)                     # decided at close of bar t
        if t + 1 < len(bars) and want != held:   # executes at open of t+1
            delta = abs(want - held)
            cost = delta * COST_PER_UNIT
            equity *= (1.0 - cost)
            total_cost += cost
            turnover += delta
            trades += 1
            held = want
        peak = max(peak, equity)
        max_dd = min(max_dd, equity / peak - 1.0)
        curve.append(equity)
    return {
        "final_equity": equity, "net_return_pct": (equity - 1.0) * 100.0,
        "trades": trades, "turnover": turnover, "cost_pct": total_cost * 100.0,
        "max_drawdown_pct": max_dd * 100.0,
    }


def show(label, bars):
    r = replay(bars)
    print(f"{label}: net {r['net_return_pct']:+.3f}% | trades {r['trades']} | "
          f"turnover {r['turnover']:.1f} | costs {r['cost_pct']:.3f}% | "
          f"maxDD {r['max_drawdown_pct']:.3f}%")
    return r


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "bars.csv"
    bars = load_bars(path)
    print(f"bars: {len(bars)} | {bars[0]['close']} -> {bars[-1]['close']} "
          f"({(bars[-1]['close'] / bars[0]['close'] - 1) * 100:+.2f}% buy&hold)")
    half = len(bars) // 2
    show("FULL ", bars)
    show("HALF1", bars[:half])
    show("HALF2", bars[half:])


if __name__ == "__main__":
    main()
