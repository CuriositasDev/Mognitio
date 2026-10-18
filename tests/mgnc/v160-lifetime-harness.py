#!/usr/bin/env python3
"""Ensure lifetime evidence rejects leaks, changed inputs and interrupted runs."""
import contextlib, hashlib, io, json, runpy, subprocess, sys, tempfile
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
checks=0;sha=lambda data:hashlib.sha256(data).hexdigest()
with tempfile.TemporaryDirectory() as temporary:
    root=Path(temporary);compiler=root/"compiler";compiler.write_bytes(b"controlled observer")
    for scenario in ["pass","owned-leak","fd-leak","wrong-exit","input-mutation","timeout"]:
        fixtures=root/(scenario+"-fixtures");fixtures.mkdir();cases=[]
        for name in ["lifetime-bounded","lifetime-retained","io-resource"]:
            folder=fixtures/name;folder.mkdir();(folder/"mognitio.toml").write_bytes(b"fixture")
            arguments=([[str(n)] for n in [10000,100000,1000000]] if name!="io-resource" else
                       [[str(n),mode] for n in [100,1000,10000] for mode in ["success","decode","read"]])
            cases.append(dict(name=name,arguments=arguments,inventory=[dict(path="mognitio.toml",bytes=7,sha256=sha(b"fixture"))]))
        (fixtures/"manifest.json").write_text(json.dumps(cases))
        output=root/scenario
        def controlled(command,**options):
            if str(command[1])=="build":
                Path(command[-1]).write_bytes(b"controlled native image")
                return subprocess.CompletedProcess(command,0,b"",b"")
            if scenario=="timeout":raise subprocess.TimeoutExpired(command,options["timeout"],output=b"partial")
            observed=Path(command[command.index("--report")+1])
            observed.write_text(json.dumps(dict(heap={"resources":1 if scenario=="owned-leak" else 0},
                high={"fds":5 if scenario=="fd-leak" else 3})))
            if scenario=="input-mutation":(fixtures/"lifetime-bounded/mognitio.toml").write_bytes(b"changed")
            return subprocess.CompletedProcess(command,3 if scenario=="wrong-exit" else 0,b"",b"")
        argv=[str(HERE/"v160-native-lifetime.py"),"--compiler",str(compiler),"--fixtures",str(fixtures),"--output",str(output)]
        failed=False
        with patch.object(sys,"argv",argv),patch("subprocess.run",controlled),contextlib.redirect_stdout(io.StringIO()):
            try:runpy.run_path(argv[0],run_name="__main__")
            except (AssertionError,subprocess.TimeoutExpired):failed=True
        data=json.loads((output/"results.json").read_text())
        if scenario=="pass":
            assert data["complete"] and not failed and all(r["status"]=="Passed" for r in data["records"])
        else:
            assert failed and not data["complete"]
            assert [r["status"] for r in data["records"]]==["Failed"]+["NotRun"]*14
            if scenario=="timeout":assert data["records"][0]["stdout_hex"]==b"partial".hex()
        checks+=1
print("V160_LIFETIME_HARNESS_OK scenarios="+str(checks))
