#!/usr/bin/env python3
"""Verify implementation evidence without adopting final performance budgets."""
import argparse,hashlib,json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument("--evidence",type=Path,required=True);p.add_argument("--compiler",type=Path,required=True);a=p.parse_args()
def sha(data):return hashlib.sha256(data).hexdigest()
def read(name):return json.loads((a.evidence/name).read_text())
identity=read("external/identity.json");artifact=sha(a.compiler.read_bytes())
assert artifact==identity["compiler_sha256"]
files=[{"path":x.relative_to(ROOT).as_posix(),"bytes":x.stat().st_size,"sha256":sha(x.read_bytes())} for x in sorted((ROOT/"compiler/mgnc/src").rglob("*.mgn"))]
assert files==identity["inventory"]
assert sha("".join(x["sha256"]+"  "+x["path"]+"\n" for x in files).encode())==identity["inventory_sha256"]
assert identity["seed_receipt"]==json.loads((ROOT/"verification/v1.5.0-seed2.json").read_text())
export=read("export.json")
for item in export["files"]:
 data=(a.evidence/item["path"]).read_bytes()
 assert sha(data)==item["published_sha256"] and len(data)==item["bytes"],item["path"]
counts={"classification":20,"v150-conformance":139,"v150-boundaries":41,"v150-catalog":65,"native":85,"v150-inherited":55,"v150-project-faults":14,"parse_compatibility":4,"parse_driver":21,"parse-faults":3,"parse-mutations":6}
for name,count in counts.items():
 record=read("external/"+name+".json")
 assert record["compiler_sha256"]==artifact and len(record["records"])==count,name
 assert all(row.get("passed",True) for row in record["records"]),name
assert read("external/native.json")["checks"]==90
for name,count in [("parse_cases",169),("v150-review",63)]:
 record=read("external/"+name+".json")
 assert record["compiler_sha256"]==artifact and record["passed"]==record["total"]==count
for name in ["corpus-C0-r2","corpus-C1"]:
 record=read("external/"+name+".json")
 assert record["compiler_sha256"]==artifact and record["passed"] and record["exit"]==0
 assert record["cutoff"] is None and record["harness_failure"] is None
 assert all(s["bytes"]==0 for s in record["streams"].values())
 if name.endswith("C1"):assert record["inventory_sha256"]==identity["inventory_sha256"]
mutations=read("external/mutations-final.json")
assert mutations["compiler_sha256"]==artifact and mutations["passed"] and len(mutations["records"])==7
assert all(row["passed"] for row in mutations["records"])
for corpus in ["C0","C1"]:
 record=read("internal/coverage-"+corpus+".json")
 assert record["passed"] and record["membership_matches"] and record["exit"]==0 and record["completed_bodies"]>0
 assert record["source_files"]==(57 if corpus=="C0" else len(files))
for row in read("internal/runner.json"):assert row["exit"]==0,row
order=read("internal/classification-order.json")
assert order["reverse_prediction"] and order["force_full_classification"] and order["exit"]==0
assert order["observations"]["passed"] and len(order["observations"]["records"])==20
for version in ["24.04.5","26.04.1"]:
 record=read("isolation/"+version+".json")
 assert record["compiler_sha256"]==artifact and record["passed"] and record["generation"]["passed"]
 assert {r["corpus"] for r in record["records"]}=={"C0","C1"}
 assert all(r["passed"] and r["exec_count_including_sandbox"]==2 and r["input_unchanged"] and r["output_directory_unchanged"] for r in record["records"])
native=read("external/native-measure.json")
assert native["fixture_manifest_sha256"]==sha((a.evidence/"external/native-fixtures.json").read_bytes())
assert native["compiler_sha256"]==artifact and native["warmups"]==1 and native["repeats"]==5 and len(native["cells"])==21
for cell in native["cells"]:
 samples=cell["samples"];measured=[r for r in samples if not r["warmup"]]
 assert cell["pass"] and len(samples)==6 and len(measured)==5 and all(r["correct"] and not r["timeout"] for r in samples)
 assert statistics.median(r["wall_seconds"] for r in measured)<=30
 assert max(r["peak_rss_bytes"] for r in measured)<=256*1024**2
parse=read("external/parse-measure.json");manifest=read("external/parse-fixtures.json")
assert parse["manifest_sha256"]==sha((a.evidence/"external/parse-fixtures.json").read_bytes())
assert parse["compiler_sha256"]==artifact and parse["passed"] and not parse["preflight"]
assert len(parse["records"])==6*len(manifest["cases"])
assert {r["name"]:r["sha256"] for r in manifest["cases"] if r["group"]=="C1"}=={r["path"]:r["sha256"] for r in files}
for case in manifest["cases"]:
 rows=[r for r in parse["records"] if (r["group"],r["name"])==(case["group"],case["name"])]
 measured=[r for r in rows if not r["warmup"]]
 assert len(rows)==6 and len(measured)==5 and all(r["passed"] for r in rows)
 assert statistics.median(r["seconds"] for r in measured)<=30 and max(r["rss_mib"] for r in measured)<=512
for group in ["C0","C1"]:
 rounds=[sum(r["seconds"] for r in parse["records"] if r["group"]==group and r["iteration"]==i) for i in range(1,6)]
 assert statistics.median(rounds)<=120
profile=read("external/preliminary/results.json");fixtures=read("external/semantic-fixtures.json")
assert profile["fixture_manifest_sha256"]==sha((a.evidence/"external/semantic-fixtures.json").read_bytes())
assert profile["compiler_sha256"]==artifact and profile["stage"]=="preliminary-only" and profile["formal_budget_adopted"] is False
assert profile.get("all_selected_completed",False) and profile.get("full_profile_selected",False),"preliminary profile incomplete"
assert len(profile["cells"])==len(fixtures["cells"])==118
assert next(c for c in fixtures["cells"] if c["name"]=="C1")["inventory_sha256"]==identity["inventory_sha256"]
assert {c["name"] for c in profile["cells"]}=={c["name"] for c in fixtures["cells"]}
streams={row["path"]:row for row in read("external/preliminary/streams.json")["streams"]}
assert len(streams)==118*4*2
for cell in profile["cells"]:
 assert cell["completed"] and len(cell["runs"])==4
 assert [r["kind"] for r in cell["runs"]]==["warmup","run-1","run-2","run-3"]
 for run in cell["runs"]:
  assert run["correct"] and run["input_unchanged"] and run["cutoff"] is None and run["harness_failure"] is None
  assert run["peak_rss_bytes"]==run["peak_rss_raw"]*1024
  for name,meta in run["streams"].items():
   stream=streams[cell["name"]+"/"+run["kind"]+"/"+name];data=bytes.fromhex(stream["hex"])
   assert len(data)==meta["bytes"]==stream["bytes"] and sha(data)==meta["sha256"]==stream["sha256"]
 assert cell["wall_median_seconds"]==statistics.median(r["seconds"] for r in cell["runs"][1:])
 assert cell["rss_max_bytes"]==max(r["peak_rss_bytes"] for r in cell["runs"][1:])
print("V150_IMPLEMENTATION_EVIDENCE_OK source_files="+str(len(files))+" native_samples=126 preliminary_samples=472 formal_budget_adopted=false")
