# AI Trading Agent v1

Termux-friendly crypto trading research agent. v1 uses Python standard library only.

## Scope
- OHLCV CSV input
- HH/HL/LH/LL market structure
- conservative BOS detection
- support/resistance + ATR
- Entry/SL/TP + R:R
- simple historical backtest
- NO live order execution

## Termux
```bash
pkg update -y
pkg install -y python git
# clone your GitHub repo, then:
cd ai-trading-agent-v1
python main.py analyze examples/DOGEUSDT_1h.csv
python main.py backtest examples/DOGEUSDT_1h.csv
```

CSV columns: `timestamp,open,high,low,close,volume`.
