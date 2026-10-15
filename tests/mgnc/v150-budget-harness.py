#!/usr/bin/env python3
"""Exercise formal identity, boundary, completeness and CLI failure gates."""
import contextlib
import copy
import hashlib
import io
import json
import runpy
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
from v150_budget import load_budget, within_budget

checks=0
def check(condition):
    global checks
    assert condition
    checks+=1

limits=dict(wall_median_seconds=5,rss_max_bytes=128*1024**2,
            wall_cutoff_seconds=10,observed_rss_cutoff_bytes=256*1024**2)
runs=[dict(kind=name,correct=True,input_unchanged=True,cutoff=None,
           harness_failure=None,seconds=value,peak_rss_bytes=128*1024**2)
      for name,value in zip(["warmup","run-1","run-2","run-3"],[9,4,5,6])]
check(within_budget(runs,limits))
for change in ["wall","rss","warmup","incomplete","cutoff","monitor","changed","nan"]:
    altered=copy.deepcopy(runs)
    if change=="wall":altered[1]["seconds"]=6
    elif change=="rss":altered[1]["peak_rss_bytes"]+=1
    elif change=="warmup":altered[0]["correct"]=False
    elif change=="incomplete":altered.pop()
    elif change=="cutoff":altered[3]["cutoff"]="wall"
    elif change=="monitor":altered[2]["harness_failure"]="unavailable"
    elif change=="changed":altered[2]["input_unchanged"]=False
    elif change=="nan":altered[2]["seconds"]=float("nan")
    check(not within_budget(altered,limits))

root=Path(__file__).resolve().parents[2]
names=[f"case-{n}" for n in range(116)]+["C0","C1"]
manifest={"cells":[dict(name=n,inventory_sha256="source") for n in names]}
budget=dict(schema=1,status="accepted",accepted_at="2026-10-15",warmups=1,
            recorded_runs=3,compiler_sha256="artifact",
            fixture_manifest_sha256="fixtures",source_inventory_sha256="source",
            seed_archive_sha256="seed",cells={n:dict(limits) for n in names})
kwargs=dict(compiler_sha256="artifact",fixture_sha256="fixtures",
            manifest=manifest,seed_sha256="seed")
check(load_budget(budget,**kwargs)==budget)
for change in ["candidate","fixture","seed","source","missing","extra","nan","negative",
               "fractional-byte","cutoff","provisional","repeat","duplicate"]:
    altered=copy.deepcopy(budget);args=copy.deepcopy(kwargs)
    if change=="candidate":altered["compiler_sha256"]="other"
    elif change=="fixture":altered["fixture_manifest_sha256"]="other"
    elif change=="seed":altered["seed_archive_sha256"]="other"
    elif change=="source":altered["source_inventory_sha256"]="other"
    elif change=="missing":del altered["cells"]["C0"]
    elif change=="extra":altered["cells"]["extra"]=dict(limits)
    elif change=="nan":altered["cells"]["C0"]["wall_median_seconds"]=float("nan")
    elif change=="negative":altered["cells"]["C0"]["rss_max_bytes"]=-1
    elif change=="fractional-byte":altered["cells"]["C0"]["rss_max_bytes"]=1.5
    elif change=="cutoff":altered["cells"]["C0"]["wall_cutoff_seconds"]=4
    elif change=="provisional":altered["status"]="provisional"
    elif change=="repeat":altered["recorded_runs"]=2
    elif change=="duplicate":args["manifest"]["cells"][-1]=args["manifest"]["cells"][0]
    try:load_budget(altered,**args)
    except (ValueError,KeyError):check(True)
    else:raise AssertionError(change)

# Drive the actual CLI with controlled observations, independently of compiler timing.
with tempfile.TemporaryDirectory() as directory:
    directory=Path(directory);fixtures=directory/"fixtures";fixtures.mkdir()
    compiler=directory/"compiler";compiler.write_bytes(b"test-only observer target")
    sha=lambda b:hashlib.sha256(b).hexdigest()
    cases=[]
    for name in names:
        base=fixtures/name;(base/"src").mkdir(parents=True)
        (base/"mognitio.toml").write_text("fixture\n")
        (base/"src/app.mgn").write_text("fixture source\n")
        cases.append(dict(name=name,axis="test",size=1,expected_exit=0,phase=None,
                          manifest_sha256=sha(b"fixture\n"),inventory_sha256="source",
                          inventory=[dict(path="src/app.mgn",sha256=sha(b"fixture source\n"))]))
    fixture_bytes=(json.dumps({"cells":cases})+"\n").encode()
    (fixtures/"manifest.json").write_bytes(fixture_bytes)
    budget.update(compiler_sha256=sha(compiler.read_bytes()),
                  fixture_manifest_sha256=sha(fixture_bytes),
                  seed_archive_sha256=json.loads((root/"verification/v1.5.0-seed2.json").read_text())["sha256"])
    policy=directory/"budget.json";policy.write_text(json.dumps(budget))
    for scenario in ["pass","budget-failure","warmup-failure","warmup-late","recorded-late","partial","wrong-identity"]:
        output=directory/scenario;observed=[]
        def observe(command,destination,**options):
            observed.append(options)
            destination.mkdir(parents=True)
            (destination/"stdout").write_bytes(b"")
            (destination/"stderr").write_bytes(b"")
            fail=scenario=="warmup-failure"
            seconds=6 if scenario=="budget-failure" else 5
            if ((scenario=="warmup-late" and destination.name=="warmup")
                    or (scenario=="recorded-late" and destination.name=="run-1")):seconds=11
            return dict(exit=1 if fail else 0,signal=None,seconds=seconds,
                        peak_rss_bytes=limits["rss_max_bytes"],cutoff=None,harness_failure=None)
        candidate=copy.deepcopy(budget)
        if scenario=="wrong-identity":candidate["compiler_sha256"]="other"
        policy.write_text(json.dumps(candidate))
        argv=["v150-measure.py","--compiler",str(compiler),"--fixtures",str(fixtures),
              "--output",str(output),"--formal-budget",str(policy)]
        if scenario=="partial":argv+=["--only","C0"]
        with patch.object(sys,"argv",argv),patch("v150_measurelib.observe",observe),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            try:runpy.run_path(str(root/"tests/mgnc/v150-measure.py"),run_name="__main__")
            except SystemExit as error:exit_code=error.code
            except ValueError:exit_code=1
            else:raise AssertionError("runner did not exit")
        check(exit_code==(0 if scenario=="pass" else 2 if scenario=="partial" else 1))
        if scenario in ["partial","wrong-identity"]:
            check(not observed and not (output/"results.json").exists())
            continue
        result=json.loads((output/"results.json").read_text())
        check(result["stage"]=="formal" and result["passed"]==(scenario=="pass"))
        check(result["budget_sha256"]==sha(policy.read_bytes()))
        check(len(observed)==(118 if scenario=="warmup-failure" else 472))
        check(all(x==dict(timeout=10,rss_limit=256*1024**2) for x in observed))
        if scenario=="warmup-failure":
            check(all(not c["completed"] and len(c["not_run"])==3 and "wall_median_seconds" not in c for c in result["cells"]))
        elif scenario in ["budget-failure","warmup-late","recorded-late"]:
            check(result["all_selected_completed"] and not any(c["budget_passed"] for c in result["cells"]))
print("V150_FORMAL_BUDGET_HARNESS_OK checks="+str(checks))
