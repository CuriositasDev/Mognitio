#!/usr/bin/env python3
"""Check root/layout plans and their independent negative controls."""
import argparse,subprocess,runpy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
prepare=runpy.run_path(str(Path(__file__).resolve().with_name("root_plan_sources.py")))["prepare"]
p=argparse.ArgumentParser();p.add_argument("--seed",type=Path,required=True);p.add_argument("--output",type=Path,required=True);args=p.parse_args();args.output.mkdir()
# Match v160-root-order: unrelated compiler namespaces are outside this probe.
project=args.output/"project";prepare(ROOT,"v160-runtime-plans.mgn",project)
binary=args.output/"probe"
result=subprocess.run([args.seed,"build",project/"mognitio.toml","-o",binary],capture_output=True,timeout=900)
assert (result.returncode,result.stdout,result.stderr)==(0,b"",b""),(result.returncode,result.stdout,result.stderr)
result=subprocess.run([binary],capture_output=True,timeout=120)
assert result.returncode==0 and not result.stderr,(result.returncode,result.stdout,result.stderr)
assert result.stdout.count(b"V160_ROOT_MUTANT ")==9 and result.stdout.count(b"V160_LAYOUT_MUTANT ")==8
# Alpha adds the reserved bigint leaf and the ordinary Int layout to the
# historical 76 descriptors; the unchanged fixture still owns 52 instances.
assert b"V160_RUNTIME_PLAN_OK instances=52 descriptors=78 rejected=17\n" in result.stdout
assert b"V160_ROOT_DIFFERENTIAL_OK graphs=128 rejected=384\n" in result.stdout
(args.output/"results.log").write_bytes(result.stdout);print(result.stdout.decode(),end="")
