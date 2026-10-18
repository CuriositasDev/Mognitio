#!/usr/bin/env python3
"""Check budget identity, complete coverage and numerical boundary rejection."""
import copy
from v160_budget import load_budget, within_budget
names=["cell-"+str(i) for i in range(103)]
manifest={"cells":[{"name":name} for name in names]}
identity=dict(compiler_sha256="compiler",measurement_manifest_sha256="fixtures",
              seed_archive_sha256="seed",source_inventory_sha256="source")
limit=dict(wall_median_seconds=5,rss_max_bytes=128*1024**2,
           wall_cutoff_seconds=10,observed_rss_cutoff_bytes=256*1024**2)
record=dict(schema=1,status="accepted",accepted_at="2026-10-18",warmups=1,recorded_runs=3,
            cells={name:dict(limit) for name in names},**identity)
assert load_budget(record,identity,manifest)==record
checks=1
for mutation in ["identity","missing","extra","pending","date","nan","negative","fraction","cutoff","runs","duplicate"]:
    changed=copy.deepcopy(record);m=copy.deepcopy(manifest)
    if mutation=="identity":changed["compiler_sha256"]="different"
    elif mutation=="missing":del changed["cells"][names[-1]]
    elif mutation=="extra":changed["cells"]["extra"]=dict(limit)
    elif mutation=="pending":changed["status"]="provisional"
    elif mutation=="date":changed.pop("accepted_at")
    elif mutation=="nan":changed["cells"][names[0]]["wall_median_seconds"]=float("nan")
    elif mutation=="negative":changed["cells"][names[0]]["rss_max_bytes"]=-1
    elif mutation=="fraction":changed["cells"][names[0]]["rss_max_bytes"]=1.5
    elif mutation=="cutoff":changed["cells"][names[0]]["wall_cutoff_seconds"]=4
    elif mutation=="runs":changed["recorded_runs"]=2
    elif mutation=="duplicate":m["cells"][-1]=m["cells"][0]
    try:load_budget(changed,identity,m)
    except ValueError:pass
    else:raise AssertionError(mutation)
    checks+=1
runs=[dict(kind=kind,seconds=seconds,peak_rss_bytes=128*1024**2,
           correct=True,input_unchanged=True,cutoff=None,harness_failure=None)
      for kind,seconds in zip(["warmup","run-1","run-2","run-3"],[9,4,5,6])]
assert within_budget(runs,limit);checks+=1
for mutation in ["warmup","incomplete","rss","median","late","monitor"]:
    changed=copy.deepcopy(runs)
    if mutation=="warmup":changed[0]["correct"]=False
    elif mutation=="incomplete":changed.pop()
    elif mutation=="rss":changed[1]["peak_rss_bytes"]+=1
    elif mutation=="median":changed[1]["seconds"]=6
    elif mutation=="late":changed[0]["seconds"]=11
    elif mutation=="monitor":changed[1]["harness_failure"]="residue"
    assert not within_budget(changed,limit),mutation;checks+=1
print("V160_BUDGET_HARNESS_OK checks="+str(checks))
