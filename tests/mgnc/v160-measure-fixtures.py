#!/usr/bin/env python3
"""Freeze measurement cells from the complete scale matrix and whole corpora."""
import argparse, hashlib, json
from pathlib import Path

def sha(data): return hashlib.sha256(data).hexdigest()
def project(root):
    paths = [Path("mognitio.toml")] + sorted(p.relative_to(root) for p in (root/"src").rglob("*.mgn"))
    return [dict(path=p.as_posix(), bytes=(root/p).stat().st_size, sha256=sha((root/p).read_bytes())) for p in paths]
def generate(scale, c0, c1):
    cases = json.loads((scale/"manifest.json").read_text())
    assert len(cases)==34 and len({c["name"] for c in cases})==34
    inputs = {}; cells = []
    for name, root in [("C0", c0), ("C1", c1)]:
        inputs[name] = project(root)
        if name=="C0":
            source=[row for row in inputs[name] if row["path"].endswith(".mgn")]
            assert len(source)==102 and sum(row["bytes"] for row in source)==1076892,"C0 scope changed"
            inventory="".join(row["sha256"]+"  compiler/mgnc/"+row["path"]+"\n" for row in source)
            assert sha(inventory.encode())=="d01b7bacc62b585761b24cde0bcee94186e1343a7e425da26b9d42e9bb58bbee","C0 inventory changed"
            assert inputs[name][0]["sha256"]=="aa004c27dd46461893d674154416d45aabbb4c73502b4b91d1a12fa46e303ba2","C0 manifest changed"
        for verb in ["check", "lower"]:
            cells.append(dict(name=name+"-"+verb, input=name, operation=verb, exit=0, phase=None))
    for case in cases:
        name = case["name"]; rows = project(scale/name)
        assert {r["path"]:r for r in rows} == {r["path"]:r for r in case["inventory"]}
        inputs[name] = rows
        lower_negative = case["negative"] and case["axis"]!="closures"
        cells.append(dict(name=name+"-lower", input=name, operation="lower",
                          exit=1 if lower_negative else 0, phase="type" if lower_negative else None))
        cells.append(dict(name=name+"-build", input=name, operation="build", exit=case["build_status"],
                          phase=("unsupported" if case["axis"]=="closures" else "type") if case["negative"] else None))
        if case["negative"]: continue
        base = dict(input=name, operation="run", exit=case["run_status"],
                    stdout_sha256=case["stdout_sha256"], stdout_bytes=case["stdout_bytes"],
                    stderr_hex=case["stderr_hex"])
        arguments = case.get("arguments", [[]])
        for index,args in enumerate(arguments):
            cells.append(dict(base, name=name+"-run-"+str(index), arguments=args))
    assert len(cells)==103 and len({c["name"] for c in cells})==103
    return dict(schema=1, scale_manifest_sha256=sha((scale/"manifest.json").read_bytes()),
                inputs=inputs, cells=cells)
def main():
    p=argparse.ArgumentParser()
    for name in ["scale","c0","c1","output"]: p.add_argument("--"+name,type=Path,required=True)
    a=p.parse_args()
    data=generate(a.scale,a.c0,a.c1)
    with a.output.open("x") as out: out.write(json.dumps(data,indent=2)+"\n")
    print("V160_MEASUREMENT_CELLS",len(data["cells"]),sha(a.output.read_bytes()))
if __name__=="__main__": main()
