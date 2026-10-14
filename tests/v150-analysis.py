#!/usr/bin/env python3
"""Check the additional standard surface through the packaged static worker."""
import argparse
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("--payload", type=Path, required=True)
args = parser.parse_args()
imports = r"use Std\Io\{inspectPath,FileIdentity,PathInfo,PathInfoError};"
cases = [
    ("let api:Function(String):Result<PathInfo,PathInfoError>=inspectPath;", True),
    ('let observed:Result<PathInfo,PathInfoError>=inspectPath("/must-not-be-observed");', True),
    ("let same:Function(FileIdentity,FileIdentity):Bool=function(a:FileIdentity,b:FileIdentity):Bool{a==b};", True),
    ("let bad:FileIdentity=FileIdentity{};", False),
    ("let bad:Function(FileIdentity):Int=function(a:FileIdentity):Int{a->device};", False),
    ("let bad:Function(FileIdentity,FileIdentity):Bool=function(a:FileIdentity,b:FileIdentity):Bool{a<b};", False),
    ('let bad:Result<PathInfo,PathInfoError>=inspectPath(1);', False),
]
diagnostic_cases = [
    ('let probe:Function(FileIdentity):Unit=function(id:FileIdentity):Unit{assert id;};',
     'assert requires Bool; actual FileIdentity'),
    ('let probe:Function(List<FileIdentity>):Unit=function(ids:List<FileIdentity>):Unit{assert ids;};',
     'assert requires Bool; actual List<FileIdentity>'),
    ('let probe:Function(Function():FileIdentity):Unit=function(get:Function():FileIdentity):Unit{assert get;};',
     'assert requires Bool; actual Function(): FileIdentity'),
    ('@test let probe:Function():List<FileIdentity>=function():List<FileIdentity>{panic{"unreachable"};};',
     'test must have type Function(): Unit; actual Function(): List<FileIdentity>'),
]
all_cases = [(body, valid, None) for body, valid in cases]
all_cases += [(body, False, message) for body, message in diagnostic_cases]
for body, valid, expected_message in all_cases:
    text = "namespace App;"+imports+body
    snapshot = {"root": "/fixture", "manifest": '[project]\nname="app"\nroot_namespace="App"\n',
                "sources": {"src/app.mgn": text}}
    result = subprocess.run([str(args.payload/"runtime/sbcl"), "--core", str(args.payload/"runtime/mognitio.core"),
                             "--noinform", "--no-sysinit", "--no-userinit", "--mognitio-worker"],
                            input=json.dumps(snapshot).encode()+b"\n", capture_output=True, timeout=15)
    assert result.returncode == 0 and result.stderr == b"", result
    data = json.loads(result.stdout)
    assert data["complete"] is valid, (body, data)
    if expected_message:
        assert [(d["phase"], d["message"]) for d in data["diagnostics"]] == [("type", expected_message)], data
    if valid:
        raw = text.encode()
        standard = [mods for start, end, kind, mods in data["tokens"]["src/app.mgn"]
                    if raw[start:end] in (b"FileIdentity", b"PathInfo", b"PathInfoError", b"inspectPath")]
        assert standard and all(mods & 4 for mods in standard), data
print(f"V150_ANALYSIS_OK cases={len(cases)+len(diagnostic_cases)} diagnostics={len(diagnostic_cases)}")
