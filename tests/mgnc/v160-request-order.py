#!/usr/bin/env python3
"""Vary actual concrete requests on one immutable SemanticProject."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("--seed",type=Path,required=True);p.add_argument("--output",type=Path,required=True);p.add_argument("--expect-unstable",action="store_true");a=p.parse_args();a.output.mkdir()
root=Path(__file__).resolve().parents[2];fixtures=root/"tests/mgnc/fixtures/v160-request-order"
project=a.output/"compiler";shutil.copytree(root/"compiler/mgnc",project)
shutil.copyfile(root/"tests/mgnc/harnesses/v160-request-order.mgn",project/"src/mgnc.mgn")
probe=a.output/"probe";r=subprocess.run([a.seed,"build",project/"mognitio.toml","-o",probe],capture_output=True,timeout=900)
(a.output/"build.stdout").write_bytes(r.stdout);(a.output/"build.stderr").write_bytes(r.stderr)
assert (r.returncode,r.stdout,r.stderr)==(0,b"",b""),r
rows=[]
for case in json.loads((fixtures/"manifest.json").read_text()):
 source=fixtures/(case["name"]+".mgn");assert hashlib.sha256(source.read_bytes()).hexdigest()==case["sha256"]
 out=a.output/case["name"];out.mkdir()
 r=subprocess.run([probe,source,out],capture_output=True,timeout=300)
 (out/"stdout").write_bytes(r.stdout);(out/"stderr").write_bytes(r.stderr)
 assert r.returncode==0 and r.stderr==b"" and r.stdout in [b"V160_REQUEST_ORDER_EXPANSION_OK types=0\n",b"V160_REQUEST_ORDER_EXPANSION_OK types=1\n"],r
 interned=r.stdout.endswith(b"types=1\n")
 images=[]
 for variant in ["forward","reverse"]:
  image=out/variant;data=image.read_bytes();images.append(data);r=subprocess.run([image],capture_output=True,timeout=30)
  assert (r.returncode,r.stdout,r.stderr)==(case["exit"],b"",b""),r
 equal=images[0]==images[1]
 rows.append(dict(name=case["name"],source_sha256=case["sha256"],actual_request_order_changed=True,type_interning_order_changed=interned,artifact_sha256=[hashlib.sha256(x).hexdigest() for x in images],bytes_equal=equal,runtime_exit=case["exit"]))
 (a.output/"results.json").write_text(json.dumps(dict(expected_unstable=a.expect_unstable,records=rows),indent=2)+"\n")
 assert equal!=a.expect_unstable,(case["name"],equal)
 print(case["name"],"bytes_equal",equal,flush=True)
assert any(row["type_interning_order_changed"] for row in rows),"fixtures did not vary type interning"
print("V160_REQUEST_ORDER_OK cases="+str(len(rows)))
