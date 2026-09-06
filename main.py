import argparse

from trading_agent.data import load_csv
from trading_agent.analysis import analyze, analyze_mtf_report
from trading_agent.backtest import run_backtest


p = argparse.ArgumentParser()
sub = p.add_subparsers(dest="cmd", required=True)

a = sub.add_parser("analyze")
a.add_argument("csv")

m = sub.add_parser("analyze-mtf")
m.add_argument("d1_csv")
m.add_argument("h4_csv")
m.add_argument("--min-rr", type=float, default=2.0)

b = sub.add_parser("backtest")
b.add_argument("csv")

args = p.parse_args()

if args.cmd == "analyze":
    candles = load_csv(args.csv)
    print(analyze(candles)["report"])

elif args.cmd == "analyze-mtf":
    d1 = load_csv(args.d1_csv)
    h4 = load_csv(args.h4_csv)
    print(analyze_mtf_report(d1, h4, args.min_rr)["report"])

else:
    candles = load_csv(args.csv)
    print(run_backtest(candles)["report"])
