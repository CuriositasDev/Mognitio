#!/usr/bin/env python3
"""Check named evidence and typed IR, with explicit native admission validation."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

MODEL=r"""namespace App\Model;
public type Value=product{value:Int;};
public contract Show{show(self:Self):Int;}
public witness Proof=Value implements Show{show(self:Self):Int{self->value}}
"""
def entry(imports='',body='0',prefix=''):
    return 'namespace App;\n'+imports+'\n'+prefix+'\nlet main:Function(List<String>):Int=function(args:List<String>):Int{'+body+'};\n'
def own(prefix,body='0'):
    return {'src/app.mgn':entry(body=body,prefix=prefix)}
BASE='type Value=product{value:Int;};contract Show{show(self:Self):Int;}witness Proof=Value implements Show{show(self:Self):Int{self->value}}'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--compiler',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument("--keep-going",action="store_true")
    parser.add_argument("--native",action="store_true",help="require successful native builds for accepted sources")
    args=parser.parse_args();compiler=args.compiler.resolve();args.output=args.output.resolve();args.output.mkdir(parents=True,exist_ok=False)
    positive={
        'unused-import':{'src/Model/model.mgn':MODEL,'src/app.mgn':entry(r'use App\Model\{Value,Show,Proof};')},
        'unreachable-file':{'src/Model/model.mgn':MODEL,'src/app.mgn':entry()},
        'aliased-evidence':{'src/Model/model.mgn':MODEL,'src/app.mgn':entry(r'use App\Model\{Value,Show,Proof as Evidence};','Show(Value{value:7})->show()')},
        'hidden-implementation':{'src/Model/model.mgn':MODEL.replace('public type Value','type Value').replace('public witness Proof','witness Proof')+'public let make:Function():Show=function():Show{Show(Value{value:7})};','src/app.mgn':entry(r'use App\Model\{Show,make};','make()->show()')},
        'dispatch':own(BASE,'Show(Value{value:7})->show()'),
        'two-pairs':own(BASE+'type Other=product{value:Int;};witness OtherProof=Other implements Show{show(self:Other):Int{self->value}}','let a:Show=Show(Value{value:1});let b:Show=Show(Other{value:2});a->show()+b->show()'),
        'method-order':own('contract Pair{first(this:Self):Int;second(that:Self,x:Int):Int;}witness Proof=Int implements Pair{second(value:Int,x:Int):Int{value+x}first(value:Self):Int{value}}','Pair(3)->second(Pair(4)->first())'),
        'empty-contract':own('contract Empty{}witness Proof=Int implements Empty{}','discard Empty(1);0'),
        'scalar-receiver':own('contract Show{show(value:Self):Int;}witness Proof=Int implements Show{show(value:Self):Int{value}}','Show(3)->show()'),
        'list-receiver':own('contract Size{size(value:Self):Int;}witness Proof=List<Int> implements Size{size(value:Self):Int{value->length()}}','Size(List<Int>[1,2])->size()'),
        'function-receiver':own('contract Invoke{invoke(value:Self):Int;}witness Proof=Function():Int implements Invoke{invoke(value:Self):Int{value()}}','Invoke(function():Int{4})->invoke()'),
        'nested-closure':own('contract Show{show(value:Self):Int;}witness Proof=Int implements Show{show(value:Self):Int{let f:Function():Int=function():Int{value};f()}}','Show(3)->show()'),
        'recursive-pack':own('contract Repeat{repeat(value:Self):Int;}witness Proof=Int implements Repeat{repeat(value:Self):Int{Repeat(value)->repeat()}}','discard Repeat(3)->repeat();0'),
        'noncomplete-package':own('contract Size{size(value:Self):Int;}witness Proof=List<Int> implements Size{size(value:Self):Int{value->length()}}','Size(List<Int>[panic{"stop"}])'),
        'type-aliases':own('alias Number=Int;contract Show{show(value:Self):Number;}alias Display=Show;witness Proof=Number implements Display{show(value:Number):Int{value}}','Display(3)->show()'),
        'isolated-parameter-shadow':own('let value:Int=1;contract Show{show(value:Self):Int;}witness Proof=Int implements Show{show(value:Self):Int{value}}','Show(3)->show()'),
        'nested-signature':own('type Data=product{value:String;};type Value=product{value:Data;};contract Show{show(value:Self):Data;}witness Proof=Value implements Show{show(value:Self):Data{value->value}}'),
        'generic-package':own(BASE+'template pack<T>=function(value:T):Show{Show(Value{value:1})};','pack<Int>(1)->show()'),
        'assert-method-body':own(BASE.replace('self->value}','assert true;self->value}'),'Show(Value{value:1})->show()'),
    }
    negative={
        'unknown-package-operand':(own('contract Show{show(value:Self):Int;}witness Proof=Int implements Show{show(value:Self):Int{value}}','Show(panic{"stop"})'),'semantic'),
        'dispatch-generic':(own(BASE,'Show(Value{value:1})->show<Int>()'),'type'),
        'missing-evidence':(own('contract Show{show(value:Self):Int;}','Show(1)->show()'),'semantic'),
        'import-types-only':({'src/Model/model.mgn':MODEL,'src/app.mgn':entry(r'use App\Model\{Value,Show};','Show(Value{value:1})->show()')},'semantic'),
        'duplicate-unreachable':({'src/Model/model.mgn':MODEL,'src/app.mgn':entry(),'src/Other/other.mgn':r'namespace App\Other;use App\Model\{Value,Show};witness OtherProof=Value implements Show{show(value:Self):Int{value->value}}'},'semantic'),
        'contract-missing-receiver':(own('contract Show{show():Int;}'),'semantic'),
        'contract-concrete-receiver':(own('contract Show{show(value:Int):Int;}'),'semantic'),
        'contract-nested-self':(own('contract Show{show(value:Self,x:List<Self>):Int;}'),'semantic'),
        'contract-result-self':(own('contract Show{show(value:Self):Self;}'),'semantic'),
        'contract-duplicate-method':(own('contract Show{show(value:Self):Int;show(value:Self):Int;}'),'semantic'),
        'contract-duplicate-parameter':(own('contract Show{show(value:Self,value:Int):Int;}'),'semantic'),
        'missing-method':(own('contract Show{show(value:Self):Int;}witness Proof=Int implements Show{}'),'semantic'),
        'duplicate-method':(own('contract Show{show(value:Self):Int;}witness Proof=Int implements Show{show(value:Self):Int{value}show(value:Self):Int{value}}'),'semantic'),
        'extra-method':(own('contract Show{show(value:Self):Int;}witness Proof=Int implements Show{show(value:Self):Int{value}extra(value:Self):Int{value}}'),'type'),
        'wrong-receiver':(own('contract Show{show(value:Self):Int;}witness Proof=Int implements Show{show(value:Bool):Int{0}}'),'type'),
        'wrong-result':(own('contract Show{show(value:Self):Int;}witness Proof=Int implements Show{show(value:Self):Bool{true}}'),'type'),
        'wrong-parameter':(own('contract Show{show(value:Self,x:Int):Int;}witness Proof=Int implements Show{show(value:Self,x:Bool):Int{value}}'),'type'),
        'missing-receiver':(own('contract Show{show(value:Self):Int;}witness Proof=Int implements Show{show():Int{0}}'),'semantic'),
        'self-in-body':(own('contract Show{show(value:Self):Int;}witness Proof=Int implements Show{show(value:Self):Int{let bad:Self=value;bad}}'),'semantic'),
        'self-in-parameter':(own('contract Show{show(value:Self,x:Int):Int;}witness Proof=Int implements Show{show(value:Self,x:Self):Int{value}}'),'semantic'),
        'outer-value':(own('let outer:Int=4;'+BASE.replace('self->value}','outer}')),'semantic'),
        'outer-standard-function':(own(r'use Std\Io\{writeStdout,IoError};'+BASE.replace('self->value}','discard writeStdout("bad");0}')),'semantic'),
        'unused-bad-body':(own(BASE.replace('self->value}','false}')),'type'),
        'witness-as-value':(own(BASE,'discard Proof;0'),'semantic'),
        'witness-as-type':(own(BASE,'let bad:Proof=1;0'),'semantic'),
        'noncontract-target':(own('witness Proof=Int implements Bool{}'),'semantic'),
        'method-reference':(own(BASE,'discard Show(Value{value:1})->show;0'),'semantic'),
        'dispatch-argument':(own(BASE,'Show(Value{value:1})->show(1)'),'semantic'),
        'dispatch-unknown':(own(BASE,'Show(Value{value:1})->missing()'),'semantic'),
        'public-private-type':(own('type Hidden=product{value:Int;};public contract Show{show(value:Self):Int;}public witness Proof=Hidden implements Show{show(value:Self):Int{value->value}}'),'semantic'),
        'contract-cycle':(own('contract First{get(value:Self):Second;}contract Second{get(value:Self):First;}'),'semantic'),
        'old-anonymous-syntax':(own('contract Show{show(value:Self):Int;}witness Int implements Show{show(value:Self):Int{value}}'),'parse'),
    }
    observations=[]
    def call(name,command,status,phase=None):
        run=subprocess.run(list(map(str,command)),capture_output=True,timeout=180,umask=0o022)
        passed=run.returncode==status and run.stdout==b'' and (run.stderr==b'' if phase is None else ('mgnc: '+phase+':').encode() in run.stderr)
        row={'case':name,'exit':run.returncode,'stdout_hex':run.stdout.hex(),'stderr_hex':run.stderr.hex(),'passed':passed};observations.append(row)
        (args.output/'results.json').write_text(json.dumps(observations,indent=2)+'\n');assert passed or args.keep_going,row
    for valid,cases in [(True,positive),(False,negative)]:
        for name,case in cases.items():
            sources,phase=(case,None) if valid else case
            project=args.output/name;manifest=project/'mognitio.toml'
            for relative,source in dict(sources,**{'mognitio.toml':'[project]\nname="app"\nroot_namespace="App"\n'}).items():
                path=project/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(source)
            inventory={p.relative_to(project).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in project.rglob('*') if p.is_file()}
            for verb in ['check','lower']:call(name+'-'+verb,[compiler,verb,manifest],0 if valid else 1,phase)
            image=project/'program'
            admitted=valid and args.native
            if not admitted:image.write_bytes(b'preserved')
            call(name+'-build',[compiler,'build',manifest,'-o',image],0 if admitted else 1,None if admitted else ('unsupported' if valid else phase))
            if admitted:assert image.read_bytes().startswith(b'\x7fELF')
            else:assert image.read_bytes()==b'preserved'
            assert all(hashlib.sha256((project/path).read_bytes()).hexdigest()==digest for path,digest in inventory.items())
    assert all(row["passed"] for row in observations),[(row["case"],bytes.fromhex(row["stderr_hex"]).decode()) for row in observations if not row["passed"]]
    print(f'V170_CONTRACTS_OK positive={len(positive)} negative={len(negative)} observations={len(observations)}')
if __name__=='__main__':main()
