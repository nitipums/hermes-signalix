#!/usr/bin/env python3
import argparse
import json
from intraday_evaluator import evaluate

p=argparse.ArgumentParser()
p.add_argument('--mode', choices=('active','act_prepare','monitor'), required=True)
p.add_argument('--interval', choices=('60m',), required=True)
a=p.parse_args()
print(json.dumps(evaluate(a.mode,a.interval), default=str))
