import argparse
from trading_agent.data import load_csv
from trading_agent.analysis import analyze
from trading_agent.backtest import run_backtest

p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd',required=True)
a=sub.add_parser('analyze'); a.add_argument('csv')
b=sub.add_parser('backtest'); b.add_argument('csv')
args=p.parse_args(); candles=load_csv(args.csv)
print(analyze(candles)['report'] if args.cmd=='analyze' else run_backtest(candles)['report'])
