#!/usr/bin/env python3
"""Seed1.9 checks of actual constant pool, emitter, and independent mutation proofs.

Small fixture carriers mirror the owning Native fields, keeping this focused
check independent from the cost of compiling every compiler subsystem. All
pool/conversion/literal/data/source-proof/machine-proof code is copied unchanged.
"""
import argparse
from pathlib import Path
import shutil
import random
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
STUBS = {
'WholeChecks': r'''namespace Mgnc\WholeChecks;use Mgnc\Data\{Span,Diagnostic,problem};public let require:Function(Bool,Span,String):Result<Unit,Diagnostic>=function(valid:Bool,span:Span,message:String):Result<Unit,Diagnostic>{branch when{valid=>Result<Unit,Diagnostic>::Ok(unit),else=>Result<Unit,Diagnostic>::Err(problem("internal",span,message))}};''',
'TypeData': r'''namespace Mgnc\TypeData;use Mgnc\MathValue\{Integer};public type ValueTerm=product{mathematical:Integer;};public type Argument=sum{Type(Int);Value(ValueTerm);};''',
'WholeIR': r'''namespace Mgnc\WholeIR;use Mgnc\Data\{Paged,Span};use Mgnc\MathValue\{Integer};use Mgnc\TypeData\{Argument};public type Origin=product{span:Span;};public type Operation=product{code:String;wide:List<Integer>;arguments:List<Argument>;origin:Origin;unavailable:String;};public type Block=product{operations:List<Operation>;};public type Body=product{blocks:Paged<Block>;};''',
'WholeConcrete': r'''namespace Mgnc\WholeConcrete;use Mgnc\Data\{Paged};use Mgnc\WholeIR\{Body};public type Instance=product{body:Body;};public type Plan=product{instances:Paged<Instance>;};''',
'WholeNativeData': r'''namespace Mgnc\WholeNativeData;use Mgnc\Data\{Paged};use Mgnc\WholeIntegerPool\{Constant};use Mgnc\WholeConcrete\{Plan};public type Procedure=product{operationLabels:Paged<List<Int>>;terminatorLabels:Paged<Int>;};public type Native=product{integers:Paged<Constant>;concrete:Plan;procedures:Paged<Procedure>;};''',
'WholeNativeLookup': r'''namespace Mgnc\WholeNativeLookup;use Mgnc\Data\{Span,Diagnostic};use Mgnc\WholeIntegerPool\{Constant,find};use Mgnc\WholeNativeData\{Native};use Mgnc\MathValue\{Integer};public let integer:Function(Native,Integer,Span):Result<Constant,Diagnostic>=function(plan:Native,value:Integer,span:Span):Result<Constant,Diagnostic>{find(plan->integers,value,span)};''',
}
PROBE = r'''namespace Mgnc;
use Mgnc\Data\{Paged,Span,Diagnostic,empty,push,lookup,number};
use Mgnc\MathValue\{Integer};
use Mgnc\WholeIntegerPool\{Constant,intern,limbs as convertLimbs};
use Mgnc\WholeIntegerPoolProof\{verify as proof};
use Mgnc\WholeIntegerPoolCheck\{verify as sourceProof};
use Mgnc\WholeIntegerPoolMachine\{verify as machineProof};
use Mgnc\WholeIntegerPoolData\{emit as poolData};
use Mgnc\WholeIntegerLiteral\{emit as literal};
use Mgnc\WholeIR\{Origin,Operation,Block,Body};
use Mgnc\WholeConcrete\{Instance,Plan};
use Mgnc\WholeNativeData\{Native,Procedure};
use Mgnc\TypeData\{Argument,ValueTerm};
use Mgnc\Machine\{Code,Record,label,raw,flush};
use Mgnc\Tables\{replaceItem};
use Std\Io\{writeStdout};
let rejected:Function(Result<Unit,Diagnostic>):Bool=function(result:Result<Unit,Diagnostic>):Bool{branch on result{Result<Unit,Diagnostic>::Ok(value:Unit)=>false,Result<Unit,Diagnostic>::Err(error:Diagnostic)=>error->phase=="internal"}};
let checked:Function():Result<Unit,Diagnostic>=function():Result<Unit,Diagnostic>{
 let span:Span=Span{start:0,end:0,line:1,column:1};let positive:Integer=Integer{negative:false,digits:"9999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999"};
 let negative:Integer=Integer{negative:true,digits:positive->digits};let other:Integer=Integer{negative:false,digits:"9999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999998"};let tiny:Integer=Integer{negative:false,digits:"17"};
 var pool:Paged<Constant>=try intern(empty<Constant>(),positive,256,span);pool=try intern(pool,positive,999,span);assert pool->count==1;pool=try intern(pool,negative,257,span);pool=try intern(pool,tiny,999,span);assert pool->count==2;pool=try intern(pool,other,258,span);assert pool->count==3;
 let origin:Origin=Origin{span:span};var ops:List<Operation>=List<Operation>[];
 loop over(List<Integer>[positive,positive,tiny] as value:Integer){ops=ops->append(Operation{code:"integer",wide:List<Integer>[value],arguments:List<Argument>[],origin:origin,unavailable:""});};
 ops=ops->append(Operation{code:"value-parameter",wide:List<Integer>[],arguments:List<Argument>[Argument::Value(ValueTerm{mathematical:negative})],origin:origin,unavailable:""});ops=ops->append(Operation{code:"integer",wide:List<Integer>[other],arguments:List<Argument>[],origin:origin,unavailable:""});
 let concrete:Plan=Plan{instances:push<Instance>(empty<Instance>(),Instance{body:Body{blocks:push<Block>(empty<Block>(),Block{operations:ops})}})};
 let procedures:Paged<Procedure>=push<Procedure>(empty<Procedure>(),Procedure{operationLabels:push<List<Int>>(empty<List<Int>>(),List<Int>[300,301,302,303,304]),terminatorLabels:push<Int>(empty<Int>(),305)});
 let plan:Native=Native{integers:pool,concrete:concrete,procedures:procedures};try sourceProof(plan);
 var code:Code=Code{records:empty<Record>(),nextLabel:1000,pending:List<Int>[]};var target:Int=300;
 loop over(List<Integer>[positive,positive,tiny,negative,other] as value:Integer){code=label(code,target);target=target+1;code=try literal(code,plan,value,span);code=raw(code,List<Int>[72,137,133,184,255,255,255]);};code=label(code,305);code=flush(try poolData(code,pool));try machineProof(plan,code);
 let first:Constant=try lookup<Constant>(pool,0);let second:Constant=try lookup<Constant>(pool,1);assert first->label==256&&second->label==257;
 var changed:Paged<Constant>=try replaceItem<Constant>(pool,0,Constant{value:negative,label:first->label,limbs:first->limbs});assert rejected(sourceProof(Native{integers:changed,concrete:concrete,procedures:procedures}));
 assert rejected(sourceProof(Native{integers:push<Constant>(pool,first),concrete:concrete,procedures:procedures}));
 changed=try replaceItem<Constant>(try replaceItem<Constant>(pool,0,second),1,first);assert rejected(sourceProof(Native{integers:changed,concrete:concrete,procedures:procedures}));
 assert rejected(proof(Constant{value:positive,label:256,limbs:List<Int>[1]},span));assert rejected(proof(Constant{value:positive,label:256,limbs:first->limbs->append(0)},span));assert rejected(proof(Constant{value:positive,label:256,limbs:first->limbs->append(1073741824)},span));
 var index:Int=0;var dataMutation:Bool=false;var targetMutation:Bool=false;var callMutation:Bool=false;var immediateMutation:Bool=false;
 loop over(code->records->pages->append(code->records->tail) as page:List<Record>){loop over(page as record:Record){
  var mutation:Record=record;var selected:Bool=false;
  branch when{record->kind==2&&record->target==256&&!targetMutation=>{mutation=Record{kind:2,bytes:record->bytes,value:0,target:257};selected=true;targetMutation=true;},record->kind==2&&record->target==210&&!callMutation=>{mutation=Record{kind:2,bytes:record->bytes,value:0,target:211};selected=true;callMutation=true;},record->kind==4&&record->value==35&&!immediateMutation=>{mutation=Record{kind:4,bytes:record->bytes,value:37,target:0};selected=true;immediateMutation=true;},record->kind==1&&record->target==256=>{let data:Record=try lookup<Record>(code->records,index+1);let records:Paged<Record>=try replaceItem<Record>(code->records,index+1,Record{kind:0,bytes:data->bytes->append(0),value:0,target:0});assert rejected(machineProof(plan,Code{records:records,nextLabel:1000,pending:List<Int>[]}));dataMutation=true;},else=>unit};
  branch when{selected=>{let records:Paged<Record>=try replaceItem<Record>(code->records,index,mutation);assert rejected(machineProof(plan,Code{records:records,nextLabel:1000,pending:List<Int>[]}));},else=>unit};index=index+1;
 };};assert dataMutation&&targetMutation&&callMutation&&immediateMutation;
 loop over(pool->pages->append(pool->tail) as page:List<Constant>){loop over(page as entry:Constant){try proof(entry,span);var line:String=number(entry->label)+" "+branch when{entry->value->negative=>"-",else=>"+"};loop over(entry->limbs as limb:Int){line=line+" "+number(limb);};discard writeStdout(line+"\n");};};
 Result<Unit,Diagnostic>::Ok(unit)
};
let main:Function(List<String>):Int=function(args:List<String>):Int{branch on checked(){Result<Unit,Diagnostic>::Ok(value:Unit)=>0,Result<Unit,Diagnostic>::Err(error:Diagnostic)=>{discard writeStdout(error->message+"\n");1}}};
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', required=True, type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='mgn-integer-pool-') as temporary:
        root = Path(temporary)
        source = root/'src'
        source.mkdir()
        actual = ['Data', 'MathValue', 'TextUtil', 'Width', 'Tables', 'IntMap', 'Machine', 'WholeX64', 'WholeABI', 'WholeInteger',
                  'WholeIntegerPool', 'WholeIntegerPoolProof', 'WholeIntegerPoolCheck', 'WholeIntegerPoolMachine', 'WholeIntegerPoolData', 'WholeIntegerLiteral']
        for name in actual:
            shutil.copytree(ROOT/'compiler/mgnc/src'/name, source/name)
        for name, text in STUBS.items():
            (source/name).mkdir()
            (source/name/'fixture.mgn').write_text(text)
        (root/'mognitio.toml').write_text('[project]\nname = "probe"\nroot_namespace = "Mgnc"\n')
        rng = random.Random(20063)
        vectors = []
        for width in [63, 64, 65, 127, 128, 255, 256, 511, 1024, 2048, 4096]:
            value = (1 << width) + rng.getrandbits(width)
            expected = []
            remaining = value
            while remaining:
                expected.append(remaining & ((1 << 30)-1))
                remaining >>= 30
            for negative in [False, True]:
                vectors.append(' {let chunkValue:Integer=Integer{negative:'+str(negative).lower()+',digits:"'+str(value)+'"};let actual:List<Int>=try convertLimbs(chunkValue,span);let wanted:List<Int>=List<Int>['+','.join(map(str,expected))+'];assert actual->length()==wanted->length();var ordinal:Int=0;loop over(actual as limb:Int){assert limb==(try atList<Int>(wanted,ordinal));ordinal=ordinal+1;};try proof(Constant{value:chunkValue,label:999,limbs:actual},span);};')
        fixture = PROBE.replace('use Mgnc\\Tables\\{replaceItem};', 'use Mgnc\\Tables\\{replaceItem,atList};')
        fixture = fixture.replace(' Result<Unit,Diagnostic>::Ok(unit)\n};', ''.join(vectors)+'\n Result<Unit,Diagnostic>::Ok(unit)\n};')
        (source/'probe.mgn').write_text(fixture)
        image = root/'probe'
        built = subprocess.run([args.seed.resolve(), 'build', root/'mognitio.toml', '-o', image], capture_output=True, timeout=240)
        assert (built.returncode, built.stdout, built.stderr) == (0, b'', b''), built.stderr
        ran = subprocess.run([image], capture_output=True, timeout=60)
        assert ran.returncode == 0 and not ran.stderr, (ran.returncode, ran.stdout, ran.stderr)
        rows = ran.stdout.decode().splitlines()
        expected = [int('9'*100), -int('9'*100), int('9'*99+'8')]
        assert len(rows) == 3, rows
        for index, (line, value) in enumerate(zip(rows, expected)):
            label, sign, *limbs = line.split()
            number = sum(int(limb) << (30*i) for i, limb in enumerate(limbs))
            assert number*(-1 if sign == '-' else 1) == value and int(label) == 256+index
    print('INTEGER_POOL_OK unique=3 repeated=1 immediate=1 value-parameter=1 mutations=10 chunk-vectors=22')


if __name__ == '__main__':
    main()
