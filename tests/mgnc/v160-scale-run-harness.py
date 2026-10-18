#!/usr/bin/env python3
"""Exercise complete, failed and interrupted scale evidence independently."""
import contextlib, hashlib, io, json, runpy, struct, subprocess, sys, tempfile
from pathlib import Path
from unittest.mock import patch
from v160_elf import elf

HERE = Path(__file__).resolve().parent
image = bytearray(128)
image[:16] = b"\x7fELF\x02\x01\x01" + bytes(9)
struct.pack_into("<HHIQQQIHHHHHH", image, 16, 2, 62, 1, 0x400078, 64, 0, 0, 64, 56, 1, 0, 0, 0)
struct.pack_into("<IIQQQQQQ", image, 64, 1, 5, 0, 0x400000, 0x400000, len(image), len(image), 4096)
elf(image)
for offset in [0, 24, 68, 96]:
    changed = bytearray(image); changed[offset] ^= 1
    try: elf(changed)
    except AssertionError: pass
    else: raise AssertionError(("bad ELF accepted", offset))
checks = 5
sha = lambda data: hashlib.sha256(data).hexdigest()
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary); compiler = root/"compiler"; compiler.write_bytes(b"controlled compiler")
    for scenario in ["pass", "build-failure", "timeout", "late-inventory", "mutation", "membership", "compiler-mutation", "skip"]:
        fixtures = root/(scenario+"-fixtures"); fixtures.mkdir()
        compiler.write_bytes(b"controlled compiler")
        cases = []
        for name in ["one", "two", "three"]:
            folder = fixtures/name; folder.mkdir(); (folder/"mognitio.toml").write_bytes(b"fixture")
            cases.append(dict(name=name, axis="test", negative=False, build_status=0,
                run_status=7, stdout_sha256=sha(b""), stdout_bytes=0, stderr_hex="",
                inventory=[dict(path="mognitio.toml", bytes=7, sha256=sha(b"fixture"))]))
        if scenario == "late-inventory": (fixtures/"two/mognitio.toml").write_bytes(b"changed")
        (fixtures/"manifest.json").write_text(json.dumps(cases))
        output = root/(scenario+"-result"); calls = []
        def controlled(command, **options):
            calls.append(command)
            if len(command)>1 and str(command[1]) == "build":
                if scenario == "timeout": raise subprocess.TimeoutExpired(command, options["timeout"])
                if scenario == "membership": (Path(command[2]).parent/"new.mgn").write_bytes(b"extra")
                if scenario == "compiler-mutation": compiler.write_bytes(b"changed compiler")
                if scenario == "mutation": Path(command[2]).write_bytes(b"changed")
                if scenario == "build-failure": return subprocess.CompletedProcess(command, 3, b"", b"bad")
                Path(command[-1]).write_bytes(image)
                return subprocess.CompletedProcess(command, 0, b"", b"")
            return subprocess.CompletedProcess(command, 7, b"", b"")
        argv = [str(HERE/"v160-native-scale-run.py"), "--compiler", str(compiler),
                "--fixtures", str(fixtures), "--output", str(output)]
        if scenario == "skip": argv += ["--skip", "two"]
        failed = False
        with patch.object(sys, "argv", argv), patch("subprocess.run", controlled), contextlib.redirect_stdout(io.StringIO()):
            try: runpy.run_path(argv[0], run_name="__main__")
            except (AssertionError, subprocess.TimeoutExpired): failed = True
        report = json.loads((output/"results.json").read_text())
        statuses = [row["status"] for row in report["records"]]
        expected = (["Passed"]*3 if scenario=="pass" else
                    ["Passed","NotRun","Passed"] if scenario=="skip" else
                    ["Passed","Failed","NotRun"] if scenario=="late-inventory" else
                    ["Failed","NotRun","NotRun"])
        assert statuses == expected, (scenario,statuses)
        assert failed == (scenario not in ("pass","skip"))
        assert report["compiler_sha256"] == sha(b"controlled compiler")
        if failed:
            row = next(row for row in report["records"] if row["status"]=="Failed")
            assert row["phase"] in ("inventory","build","runtime")
            assert row["reason"] == ("TimeoutExpired" if scenario=="timeout" else "AssertionError")
        checks += 1
print("V160_SCALE_RUN_HARNESS_OK checks="+str(checks))
