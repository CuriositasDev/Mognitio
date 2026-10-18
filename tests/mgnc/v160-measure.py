#!/usr/bin/env python3
"""Measure frozen lower/build/runtime cells without adopting budgets implicitly."""
import argparse, hashlib, importlib.util, json, os, platform, resource, stat, statistics
from pathlib import Path
from v160_measurelib import observe
from v160_budget import load_budget, within_budget
from v160_elf import elf

def sha(data): return hashlib.sha256(data).hexdigest()
def main():
    p=argparse.ArgumentParser()
    for name in ["compiler","scale","c0","c1","manifest","seed-receipt","output"]:
        p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--only",action="append");p.add_argument("--formal-budget",type=Path)
    a=p.parse_args()
    if a.formal_budget and a.only:p.error("formal measurement cannot select partial cells")
    here=Path(__file__).resolve().parent
    spec=importlib.util.spec_from_file_location("fixtures",here/"v160-measure-fixtures.py")
    fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
    raw=a.manifest.read_bytes();manifest=json.loads(raw)
    if manifest!=fixture.generate(a.scale,a.c0,a.c1):p.error("frozen measurement manifest does not match inputs")
    names={c["name"] for c in manifest["cells"]}
    if a.only and not set(a.only)<=names:p.error("unknown measurement cell")
    seed=json.loads(a.seed_receipt.read_text())
    seed=seed.get("seed",seed)
    identity=dict(compiler_sha256=sha(a.compiler.read_bytes()),measurement_manifest_sha256=sha(raw),
                  seed_archive_sha256=seed["sha256"],
                  source_inventory_sha256=sha(json.dumps(manifest["inputs"]["C1"],sort_keys=True).encode()))
    budget=load_budget(json.loads(a.formal_budget.read_text()),identity,manifest) if a.formal_budget else None
    a.output.mkdir(exist_ok=False)
    roots={key:(a.c0 if key=="C0" else a.c1 if key=="C1" else a.scale/key) for key in manifest["inputs"]}
    report=dict(schema=1,stage="formal" if budget else "preliminary-only",identity=identity,
                warmups=1,recorded_runs=3,sample_interval_seconds=.01,
                preliminary_wall_seconds=900,preliminary_observed_rss_bytes=4096*1024**2,
                formal_budget_sha256=sha(a.formal_budget.read_bytes()) if budget else None,
                cells=[dict(name=c["name"],status="NotRun",runs=[]) for c in manifest["cells"]])
    def save():(a.output/"results.json").write_text(json.dumps(report,indent=2)+"\n")
    def verify(key):
        root=roots[key];rows=manifest["inputs"][key]
        expected={r["path"] for r in rows}
        actual={"mognitio.toml"}|{str(x.relative_to(root)) for x in (root/"src").rglob("*.mgn")}
        assert expected==actual,"source membership changed"
        state={}
        for row in rows:
            path=root/row["path"];data=path.read_bytes();s=path.stat()
            assert len(data)==row["bytes"] and sha(data)==row["sha256"],"source bytes changed"
            state[row["path"]]=(s.st_mode,s.st_mtime_ns,s.st_size,s.st_dev,s.st_ino)
        return state
    def environment():
        cpu=Path("/proc/cpuinfo").read_text()
        return dict(cpu=next(x.split(":",1)[1].strip() for x in cpu.splitlines() if x.startswith("model name")),
                    meminfo=Path("/proc/meminfo").read_text(),kernel=platform.release(),
                    os_release=Path("/etc/os-release").read_text(),machine=platform.machine(),uid=os.getuid(),
                    python=platform.python_version(),loadavg=Path("/proc/loadavg").read_text(),
                    limits={name:list(resource.getrlimit(getattr(resource,name))) for name in ["RLIMIT_AS","RLIMIT_CPU","RLIMIT_NOFILE"]},
                    governors={str(f):f.read_text().strip() for f in Path("/sys/devices/system/cpu").glob("cpu*/cpufreq/scaling_governor")})
    initial=environment()
    assert initial["uid"]!=0 and initial["machine"]=="x86_64" and 'VERSION_ID="26.04"' in initial["os_release"]
    assert "i9-10850K" in initial["cpu"]
    report["environment"]=initial;artifacts={};artifact_hashes={};save()
    data=a.output/"runtime-input";data.mkdir()
    (data/"valid").write_bytes("四😀\0".encode());(data/"invalid").write_bytes(b"\xff")
    selected=[c for c in manifest["cells"] if not a.only or c["name"] in a.only]
    selected_names={c["name"] for c in selected}
    for cell,row in zip(manifest["cells"],report["cells"]):
        if cell["name"] not in selected_names:continue
        key=cell["input"];operation=cell["operation"];before=verify(key)
        row["status"]="Running";row["operation"]=operation;save()
        if operation=="run" and key not in artifacts:
            row.update(status="NotRun",reason="successful measured build is required before native runs");save();continue
        for index in range(4):
            kind="warmup" if index==0 else "run-"+str(index)
            folder=a.output/cell["name"]/kind;image=folder/"program"
            assert sha(a.compiler.read_bytes())==identity["compiler_sha256"],"compiler changed"
            assert a.manifest.read_bytes()==raw,"measurement manifest changed"
            current=environment()
            args=[]
            if operation=="run":
                args=list(cell["arguments"])
                if key=="io-resource":
                    count,mode=args
                    args=[count,str({"success":data/"valid","decode":data/"invalid","read":Path("/proc/self/mem")}[mode]),mode]
                command=[artifacts[key],*args]
                assert sha(Path(command[0]).read_bytes())==artifact_hashes[key]
            else:
                command=[a.compiler,operation,roots[key]/"mognitio.toml"]
                if operation=="build":command+=["-o",image]
            limits=budget["cells"][cell["name"]] if budget else {}
            previous_umask=os.umask(0o022)
            try:result=observe(command,folder,timeout=limits.get("wall_cutoff_seconds",900),
                               rss_limit=limits.get("observed_rss_cutoff_bytes",4096*1024**2),interval=.01)
            finally:os.umask(previous_umask)
            stdout=(folder/"stdout").read_bytes();stderr=(folder/"stderr").read_bytes()
            correct=result["exit"]==cell["exit"] and result["signal"] is None and result["cutoff"] is None and result["harness_failure"] is None
            if operation=="run":
                correct=correct and sha(stdout)==cell["stdout_sha256"] and len(stdout)==cell["stdout_bytes"] and stderr.hex()==cell["stderr_hex"]
            else:
                correct=correct and not stdout and (not stderr if cell["exit"]==0 else (("mgnc: "+cell["phase"]+":").encode() in stderr and b" [" in stderr))
            input_failure=None;artifact_failure=None
            try:
                unchanged=verify(key)==before
                assert sha(a.compiler.read_bytes())==identity["compiler_sha256"]
                assert a.manifest.read_bytes()==raw
            except (AssertionError,OSError) as error:
                unchanged=False;input_failure=type(error).__name__+": "+str(error)
            try:
                if operation=="build":
                    if cell["exit"]==0 and correct:
                        elf(image.read_bytes());assert stat.S_IMODE(image.stat().st_mode)==0o755
                        digest=sha(image.read_bytes())
                        assert key not in artifact_hashes or artifact_hashes[key]==digest,"nondeterministic artifact"
                        artifacts[key]=image;artifact_hashes[key]=digest;result["artifact_sha256"]=digest
                    elif cell["exit"]!=0:assert not image.exists(),"negative build published output"
            except (AssertionError,OSError) as error:
                artifact_failure=type(error).__name__+": "+str(error)
            correct=bool(correct and unchanged and artifact_failure is None)
            row["runs"].append(dict(kind=kind,command=list(map(str,command)),environment=current,
                                    correct=correct,input_unchanged=unchanged,input_failure=input_failure,artifact_failure=artifact_failure,**result));save()
            print(cell["name"],kind,"correct="+str(correct),"seconds="+str(round(result["seconds"],3)),flush=True)
            if not correct:break
        passed=len(row["runs"])==4 and all(x["correct"] for x in row["runs"])
        if passed:
            measured=row["runs"][1:];row.update(wall_median_seconds=statistics.median(x["seconds"] for x in measured),rss_max_bytes=max(x["peak_rss_bytes"] for x in measured))
        if budget:passed=passed and within_budget(row["runs"],limits)
        row["status"]="Passed" if passed else "Failed"
        if operation=="build" and not passed:artifacts.pop(key,None)
        save()
    report["all_selected_passed"]=all(row["status"]=="Passed" for row in report["cells"] if row["name"] in selected_names)
    report["complete"]=not a.only and all(row["status"]=="Passed" for row in report["cells"])
    save()
    print("V160_MEASURED complete="+str(report["complete"]),flush=True)
    return 0 if report["all_selected_passed"] else 1
if __name__=="__main__":raise SystemExit(main())
