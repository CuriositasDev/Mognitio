#!/usr/bin/env python3
"""Reject late reaping and validate each run's deadline independently of medians."""
import argparse
import copy
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
from v150_budget import within_budget
from v150_measurelib import observe

parser=argparse.ArgumentParser()
parser.add_argument("--evidence",type=Path)
args=parser.parse_args()
checks=[]
observations=[]
def check(name,passed):
    checks.append(dict(name=name,passed=bool(passed)))

limits=dict(wall_median_seconds=.05,rss_max_bytes=512*1024**2,
            wall_cutoff_seconds=.1,observed_rss_cutoff_bytes=1024*1024**2)
runs=[dict(kind=name,correct=True,input_unchanged=True,cutoff=None,harness_failure=None,
           seconds=.01,peak_rss_bytes=1024)
      for name in ["warmup","run-1","run-2","run-3"]]
check("baseline",within_budget(runs,limits))
for position in range(4):
    equal=copy.deepcopy(runs);equal[position]["seconds"]=.1
    check("inclusive-boundary-"+str(position),within_budget(equal,limits))
    for label,value in [("over",.100001),("nan",float("nan")),("infinite",float("inf")),
                        ("negative",-.01),("bool",True),("missing",None)]:
        altered=copy.deepcopy(runs);altered[position]["seconds"]=value
        check(label+"-seconds-"+str(position),not within_budget(altered,limits))

# Use real children and real wait4 status/RSS. Delay delivery of the reap result
# at both exits from the monitor loop; never kill a child that was already reaped.
with tempfile.TemporaryDirectory() as directory:
    directory=Path(directory)
    real_wait4=os.wait4
    for route,target in [("initial-reap",1),("rss-exit-reap",2)]:
        calls=0
        def delayed_wait4(pid,flags):
            global calls
            calls+=1
            if calls<target:
                return (0,0,None)
            result=real_wait4(pid,0)
            time.sleep(.15)
            return result
        def no_rss(path,*args,**kwargs):
            return "State: R (running)\n"
        with patch("v150_measurelib.os.wait4",delayed_wait4),patch.object(Path,"read_text",no_rss),patch("v150_measurelib.os.killpg",side_effect=AssertionError("already reaped")):
            observed=observe([sys.executable,"-c","import sys,time;time.sleep(.12);print('late');print('diagnostic',file=sys.stderr)"],directory/route,timeout=.1)
        observations.append(dict(route=route,**observed))
        check(route+"-exit-preserved",observed["exit"]==0 and observed["signal"] is None)
        check(route+"-no-harness-failure",observed["harness_failure"] is None)
        check(route+"-elapsed-preserved",observed["seconds"]>.1)
        check(route+"-wall-cutoff",observed["cutoff"]=="wall")
        check(route+"-rss-preserved",observed["peak_rss_bytes"]==observed["peak_rss_raw"]*1024>0)
        check(route+"-streams-preserved",(directory/route/"stdout").read_bytes()==b"late\n" and (directory/route/"stderr").read_bytes()==b"diagnostic\n")
        for position in [0,1]:
            altered=copy.deepcopy(runs)
            # Recheck the late timing even if an old observer omitted the flag.
            altered[position].update(observed,cutoff=None,correct=True)
            check(route+"-unflagged-rejected-"+str(position),not within_budget(altered,limits))
result=dict(checks=checks,observations=observations,passed=all(c["passed"] for c in checks))
if args.evidence:args.evidence.write_text(json.dumps(result,indent=2)+"\n")
for item in checks:
    if not item["passed"]:print("FAIL "+item["name"])
print("V150_WALL_CUTOFF checks="+str(len(checks))+" failures="+str(sum(not c["passed"] for c in checks)))
raise SystemExit(0 if result["passed"] else 1)
