#!/usr/bin/env python3
"""Observe native contract packages through an internal probe or admitted compiler."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
def source(prefix,body):
    return {'src/app.mgn':'namespace App;'+prefix+'let main:Function(List<String>):Int=function(args:List<String>):Int{'+body+'};'}
def fixtures():
    show='contract Show{show(value:Self):Int;}witness Proof=Int implements Show{show(value:Self):Int{value}}'
    take='contract Add{add(value:Self,a:Int,b:Int):Int;}witness Proof=Int implements Add{add(value:Self,a:Int,b:Int):Int{value+a*10+b}}'
    values={
        'scalar':(source(show,'assert Show(7)->show()==7;0'),0),
        'managed-snapshot':(source('type Value=product{text:String;};contract Read{read(value:Self):String;}witness Proof=Value implements Read{read(value:Self):String{value->text}}','var original:Value=Value{text:"kept"};let packed:Read=Read(original);original=Value{text:"changed"};discard "other"+" allocation";assert packed->read()=="kept";0'),0),
        'unit':(source('contract Count{count(value:Self):Int;}witness Proof=Unit implements Count{count(value:Self):Int{9}}','assert Count(unit)->count()==9;0'),0),
        'empty-product':(source('type Value=product{};contract Count{count(value:Self):Int;}witness Proof=Value implements Count{count(value:Self):Int{5}}','assert Count(Value{})->count()==5;0'),0),
        'function':(source('contract Invoke{invoke(value:Self):Int;}witness Proof=Function():Int implements Invoke{invoke(value:Self):Int{value()}}','let kept:String="saved";let packed:Invoke=Invoke(function():Int{kept->length()});discard "other"+" allocation";assert packed->invoke()==5;0'),0),
        'list':(source('contract Size{size(value:Self):Int;}witness Proof=List<Int> implements Size{size(value:Self):Int{value->length()}}','let packed:Size=Size(List<Int>[1,2,3]);discard List<String>["other","allocation"];assert packed->size()==3;0'),0),
        'member-order':(source('contract Pair{first(this:Self):Int;second(that:Self,x:Int):Int;}witness Proof=Int implements Pair{second(value:Int,x:Int):Int{value+x}first(value:Self):Int{value}}','assert Pair(3)->second(Pair(4)->first())==7;0'),0),
        'returned-method-closure':(source('contract Keep{keep(value:Self):Function():String;}witness Proof=String implements Keep{keep(value:Self):Function():String{function():String{value}}}','let kept:Function():String=Keep("retained")->keep();discard "other"+" allocation";assert kept()=="retained";0'),0),
        'recursive-package':(source('contract Repeat{repeat(value:Self):Int;}witness Proof=Int implements Repeat{repeat(value:Self):Int{branch when{value<=0=>0,else=>Repeat(value-1)->repeat()+1}}}','assert Repeat(5)->repeat()==5;0'),0),
        'empty-contract':(source('contract Empty{}witness Proof=Int implements Empty{}','let values:List<Empty>=List<Empty>[Empty(1),Empty(2)];discard "other"+" allocation";assert values->length()==2;0'),0),
        'receiver-arguments-once':(source(take,'var count:Int=0;let result:Int=({count=count+1;Add(count)})->add({count=count+1;count},{count=count+1;count});assert result==24;assert count==3;0'),0),
        'argument-return':(source('contract Add{add(value:Self,a:Int,b:Int):Int;}witness Proof=Int implements Add{add(value:Self,a:Int,b:Int):Int{assert false;0}}','Add(3)->add({return 17;},{assert false;0})'),17),
        'argument-try':(source('contract Take{take(value:Self,n:Int):Result<Int,IndexError>;}witness Proof=Int implements Take{take(value:Self,n:Int):Result<Int,IndexError>{assert false;Result<Int,IndexError>::Ok(value+n)}}let attempt:Function():Result<Int,IndexError>=function():Result<Int,IndexError>{Take(1)->take(try List<Int>[]->at(0))};','branch on attempt(){Result<Int,IndexError>::Ok(value:Int)=>{assert false;},Result<Int,IndexError>::Err(error:IndexError)=>{assert error->index==0;assert error->length==0;}};0'),0),
        'method-return-try':(source('contract Compute{compute(value:Self):Result<Int,IndexError>;}witness Proof=Int implements Compute{compute(value:Self):Result<Int,IndexError>{branch when{value<0=>{return Result<Int,IndexError>::Err(IndexError{index:value,length:0});},else=>unit};let found:Int=try List<Int>[value]->at(0);Result<Int,IndexError>::Ok(found+1)}}','branch on Compute(4)->compute(){Result<Int,IndexError>::Ok(value:Int)=>{assert value==5;},Result<Int,IndexError>::Err(error:IndexError)=>{assert false;}};branch on Compute(-1)->compute(){Result<Int,IndexError>::Ok(value:Int)=>{assert false;},Result<Int,IndexError>::Err(error:IndexError)=>{assert error->index== -1;}};0'),0),
        'alias':(source('alias Number=Int;contract Show{show(value:Self):Number;}alias Display=Show;witness Proof=Number implements Display{show(value:Number):Int{value}}','assert Display(3)->show()==3;0'),0),
        'wide-word':(source(r'use Std\Numeric\{Bits,Unsigned};contract Word{word(value:Self):Bits<64>;}witness Proof=Int<64,Unsigned> implements Word{word(value:Self):Bits<64>{value->toBits()}}','assert Word(Int<64,Unsigned>{18446744073709551615})->word()==Bits<64>{18446744073709551615};0'),0),
        'container-closure':(source(show+'type Saved=product{value:Show;};','let saved:Saved=Saved{value:Show(11)};let values:List<Show>=List<Show>[saved->value];let later:Function():Int=function():Int{branch on values->at(0){Result<Show,IndexError>::Ok(value:Show)=>value->show(),Result<Show,IndexError>::Err(error:IndexError)=>0}};discard "other"+" allocation";assert later()==11;0'),0),
    }
    model=r'namespace App\Model;public contract Read{read(value:Self):Int;}type Value=product{value:Int;};witness Scalar=Int implements Read{read(value:Self):Int{value}}witness Managed=Value implements Read{read(value:Self):Int{value->value}}public let scalar:Function():Read=function():Read{Read(7)};public let managed:Function():Read=function():Read{Read(Value{value:13})};'
    consumer=r'namespace App\Consumer;use App\Model\{Read};public let consume:Function(Read):Int=function(value:Read):Int{value->read()};'
    main=r'namespace App;use App\Model\{scalar,managed};use App\Consumer\{consume};let main:Function(List<String>):Int=function(args:List<String>):Int{assert consume(scalar())==7;assert consume(managed())==13;0};'
    values['hidden-two-pairs']=({'src/Model/model.mgn':model,'src/Consumer/consumer.mgn':consumer,'src/app.mgn':main},0)
    return values

def main():
    parser=argparse.ArgumentParser();choice=parser.add_mutually_exclusive_group(required=True);choice.add_argument('--seed',type=Path);choice.add_argument('--compiler',type=Path);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    if args.seed:
        project=out/'compiler';shutil.copytree(ROOT/'compiler/mgnc',project);shutil.copy2(HERE/'harnesses/v170-contract-native.mgn',project/'src/mgnc.mgn')
        inventory=[dict(path=p.relative_to(project).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(project.rglob('*')) if p.is_file()];(out/'inputs.json').write_text(json.dumps(inventory,indent=2)+'\n')
        compiler=out/'probe';build=subprocess.run([str(args.seed.resolve()),'build',str(project/'mognitio.toml'),'-o',str(compiler)],capture_output=True,timeout=900);(out/'build.stdout').write_bytes(build.stdout);(out/'build.stderr').write_bytes(build.stderr);assert (build.returncode,build.stdout,build.stderr)==(0,b'',b''),(build.returncode,build.stderr)
        assert all(sha(project/r['path'])==r['sha256'] for r in inventory)
    else:compiler=args.compiler.resolve()
    digest=sha(compiler);rows=[]
    def call(name,command,expected=0,cwd=ROOT):
        result=subprocess.run(list(map(str,command)),cwd=cwd,capture_output=True,timeout=180);passed=(result.returncode,result.stdout,result.stderr)==(expected,b'',b'');rows.append(dict(case=name,exit=result.returncode,stdout_hex=result.stdout.hex(),stderr_hex=result.stderr.hex(),passed=passed));(out/'results.json').write_text(json.dumps(dict(compiler_sha256=digest,internal_probe=bool(args.seed),observations=rows),indent=2)+'\n');assert passed,rows[-1]
    for name,(sources,status) in fixtures().items():
        project=out/'cases'/name
        for relative,text in dict(sources,**{'mognitio.toml':'[project]\nname="app"\nroot_namespace="App"\n'}).items():
            path=project/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
        inputs={p.relative_to(project).as_posix():sha(p) for p in project.rglob('*') if p.is_file()};artifact=project/'program';manifest=project/'mognitio.toml'
        command=[compiler,manifest,artifact] if args.seed else [compiler,'build',manifest,'-o',artifact]
        call(name+'-build',command);call(name+'-native',[artifact],status,cwd=project)
        if status==0:call(name+'-stress',[sys.executable,HERE/'v160-native-observe.py','--stress','--report',project/'stress.json','--',artifact],cwd=project)
        if status==0:
            stress=json.loads((project/'stress.json').read_text());assert stress['stress'] and stress['heap']['collections']>0
        assert all(sha(project/p)==digest for p,digest in inputs.items());assert sha(compiler)==digest
    print('V170_CONTRACT_NATIVE_OK fixtures='+str(len(fixtures()))+' observations='+str(len(rows)))
if __name__=='__main__':main()
