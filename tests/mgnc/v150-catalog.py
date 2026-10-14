#!/usr/bin/env python3
"""Closed standard catalog checks from an independent literal contract table."""
import argparse,hashlib,json,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("--compiler",required=True,type=Path);p.add_argument("--evidence",required=True,type=Path);args=p.parse_args()
sums={
 "IoOperation":"ReadTextFile WriteTextFile ReadStdin WriteStdout WriteStderr JoinPath ReadDirectory CreateDirectory",
 "IoErrorKind":"InvalidPath InvalidEncoding NotFound PermissionDenied UnsupportedTarget BrokenPipe ResourceExhausted Other",
 "DirectoryEntryKind":"File Directory Symlink Other","IoErrorPhase":"Input Target Body Cleanup",
 "ByteOrder":"LittleEndian BigEndian","BinaryFileMode":"Data Executable",
 "BinaryOutputErrorKind":"InvalidPath AlreadyExists NotFound PermissionDenied UnsupportedTarget ResourceExhausted Other",
 "BinaryOutputPhase":"Input Target Body Publish Cleanup","BinaryPublicationState":"NotPublished Published Unknown"}
products={
 "IoError":[("operation","IoOperation"),("kind","IoErrorKind"),("subject","String"),("phase","IoErrorPhase")],
 "DirectoryEntry":[("name","String"),("kind","DirectoryEntryKind")],
 "PathInfo":[("kind","DirectoryEntryKind"),("identity","FileIdentity")],
 "PathInfoError":[("kind","IoErrorKind"),("subject","String")],
 "Signed":[],"Unsigned":[],"IntegerConversionError":[],"BitShiftError":[("count","Int"),("width","Int")],
 "ByteValueError":[("index","Int"),("value","Int")],"BitWidthError":[("width","Int")],
 "BinaryDecodeError":[("width","Int"),("length","Int")],
 "BinaryOutputError":[("kind","BinaryOutputErrorKind"),("subject","String"),("phase","BinaryOutputPhase"),("publication","BinaryPublicationState")]}
functions={
 "readTextFile":"Function(String):Result<String,IoError>","writeTextFile":"Function(String,String):Result<Unit,IoError>",
 "readStdin":"Function():Result<String,IoError>","writeStdout":"Function(String):Result<Unit,IoError>",
 "writeStderr":"Function(String):Result<Unit,IoError>","joinPath":"Function(String,String):Result<String,IoError>",
 "readDirectory":"Function(String):Result<List<DirectoryEntry>,IoError>","createDirectory":"Function(String):Result<Unit,IoError>",
 "inspectPath":"Function(String):Result<PathInfo,PathInfoError>","bytesFromInts":"Function(List<Int>):Result<Bytes,ByteValueError>",
 "bytesFromBits":"Function(List<Bits<8>>):Bytes","publishFile":"Function(String,Bytes,BinaryFileMode):Result<Unit,BinaryOutputError>"}
imports="use Std\\Io\\{IoOperation,IoErrorKind,IoError,DirectoryEntryKind,DirectoryEntry,IoErrorPhase,FileIdentity,PathInfo,PathInfoError,readTextFile,writeTextFile,readStdin,writeStdout,writeStderr,joinPath,readDirectory,createDirectory,inspectPath};use Std\\Numeric\\{Signed,Unsigned,Bits,IntegerConversionError,BitShiftError};use Std\\Binary\\{Bytes,ByteOrder,ByteValueError,BitWidthError,BinaryDecodeError,BinaryFileMode,BinaryOutputErrorKind,BinaryOutputPhase,BinaryPublicationState,BinaryOutputError,bytesFromInts,bytesFromBits,publishFile};"
cases=[]
for name,signature in functions.items():
 cases.extend([(name+"-signature",f"let probe:{signature}={name};",0),(name+"-wrong-signature",f"let probe:Bool={name};",1)])
for name,variants in sums.items():
 body="branch on value{"+",".join(name+"::"+v+"=>0" for v in variants.split())+"}"
 cases.append((name+"-closed-variants",f"let probe:Function({name}):Int=function(value:{name}):Int{{{body}}};",0))
 body="branch on value{"+",".join(name+"::"+v+"=>0" for v in variants.split()[:-1])+"}"
 cases.append((name+"-missing-variant",f"let probe:Function({name}):Int=function(value:{name}):Int{{{body}}};",1))
for name,fields in products.items():
 signature="Function("+",".join(t for _,t in fields)+"):"+name
 parameters=",".join(f"p{i}:{t}" for i,(_,t) in enumerate(fields))
 construction=name+"{"+",".join(f"{field}:p{i}" for i,(field,_) in enumerate(fields))+"}"
 cases.append((name+"-closed-fields",f"let probe:{signature}=function({parameters}):{name}{{{construction}}};",0))
 if fields:
  access="".join(f"let f{i}:{t}=value->{field};discard f{i};" for i,(field,t) in enumerate(fields))
  cases.append((name+"-field-types",f"let probe:Function({name}):Int=function(value:{name}):Int{{{access}0}};",0))
for name in ["FileIdentity","Bytes"]:
 cases.append((name+"-opaque",f"let probe:{name}={name}{{}};",1))
records=[]
with tempfile.TemporaryDirectory(prefix="v150-catalog-") as temp:
 source=Path(temp)/"case.mgn"
 for name,body,expected in cases:
  text="namespace App;"+imports+body+"let main:Function(List<String>):Int=function(args:List<String>):Int{0};"
  source.write_text(text)
  result=subprocess.run([args.compiler,"check",source],capture_output=True,timeout=120)
  row={"case":name,"source_sha256":hashlib.sha256(text.encode()).hexdigest(),"exit":result.returncode,"stdout_hex":result.stdout.hex(),"stderr":result.stderr.decode(),"passed":result.returncode==expected and not result.stdout and (not result.stderr if expected==0 else bool(result.stderr))}
  records.append(row)
evidence={"compiler_sha256":hashlib.sha256(args.compiler.read_bytes()).hexdigest(),"records":records,"passed":all(r["passed"] for r in records)}
args.evidence.write_text(json.dumps(evidence,indent=2)+"\n")
assert evidence["passed"],[r for r in records if not r["passed"]]
print("V150_CATALOG_CONTRACT_OK checks="+str(len(records)))
