#!/usr/bin/env python3
"""Check paged values, replacement snapshots, index boundaries and stale indexes."""
import argparse,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument("--seed",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();a.output.mkdir()
for variant in ["indexed","stale-current-group","stale-sealed-group"]:
    project=a.output/variant;(project/"src").mkdir(parents=True)
    shutil.copyfile(ROOT/"compiler/mgnc/mognitio.toml",project/"mognitio.toml")
    shutil.copyfile(ROOT/"tests/mgnc/harnesses/v160-paged-index.mgn",project/"src/mgnc.mgn")
    for module,file in [("Data","data.mgn"),("Tables","update.mgn")]:
        text=(ROOT/"compiler/mgnc/src"/module/file).read_text()
        if module=="Tables" and variant=="stale-current-group":
            old="group=replaceList<List<T>>(group,page%64,changed);"
            assert old in text;text=text.replace(old,"group=group;")
        if module=="Tables" and variant=="stale-sealed-group":
            old="groups=replaceList<List<List<T>>>(groups,page/64,replaceList<List<T>>(previousGroup,page%64,changed));"
            assert old in text;text=text.replace(old,"groups=groups;")
        (project/"src"/module).mkdir();(project/"src"/module/file).write_text(text)
    binary=project/"probe"
    result=subprocess.run([a.seed,"build",project/"mognitio.toml","-o",binary],capture_output=True,timeout=900)
    assert (result.returncode,result.stdout,result.stderr)==(0,b"",b""),(variant,result)
    result=subprocess.run([binary],capture_output=True,timeout=120)
    expected=(0,b"V160_PAGED_INDEX_OK values=65537 replacements=16\n",b"") if variant=="indexed" else (1,b"paged oracle mismatch\n",b"")
    assert (result.returncode,result.stdout,result.stderr)==expected,(variant,result)
    print(variant,"PASS",flush=True)
print("V160_PAGED_INDEX_CHECK_OK positive=1 rejected=2")
