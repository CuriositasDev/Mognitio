#!/usr/bin/env python3
"""Build an internal native-planning probe without adding a public CLI mode."""
import argparse,hashlib,json,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('--seed',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args();args.output.mkdir(exist_ok=False)
project=args.output/'compiler';shutil.copytree(ROOT/'compiler/mgnc',project)
harness=(ROOT/'tests/mgnc/harnesses/v160-concrete.mgn').read_text().replace('namespace Mgnc;','namespace Mgnc\\ProbeConcrete;',1).replace('\nlet main:Function(','\npublic let main:Function(',1)
module=project/'src/ProbeConcrete';module.mkdir();(module/'probe.mgn').write_text(harness)
(project/'src/mgnc.mgn').write_text(r'''namespace Mgnc;
use Mgnc\ProbeConcrete\{main as probe};
use Mgnc\Driver\{run};
let main:Function(List<String>):Int=function(args:List<String>):Int{
 branch on args->at(0){Result<String,IndexError>::Ok(value:String)=>branch when{value=="--internals"=>probe(args),else=>run(args)},Result<String,IndexError>::Err(error:IndexError)=>run(args)}
};
''')
driver=project/'src/Driver/driver.mgn';text=driver.read_text();text=text.replace('use Mgnc\\Structural\\{analyzeSyntax};',r'''use Mgnc\Structural\{analyzeSyntax};
use Mgnc\WholeNativeProfile\{validate as validateNative};
use Mgnc\WholeConcrete\{Plan,build as concrete};
use Mgnc\WholeConcreteCheck\{verify as verifyConcrete};
use Mgnc\WholeClosures\{Closures,build as convertClosures};
use Mgnc\WholeClosureCheck\{verify as verifyClosures};
''')
old='branch when{checking=>{return Result<Analyzed,InputError>::Ok(Analyzed::Checked);},else=>unit};'
new='''branch when{checking=>{
 try validateNative(semantic);
 let lowered:LoweredProject=branch on wholeLower(semantic){Result<LoweredProject,Diagnostic>::Ok(value:LoweredProject)=>value,Result<LoweredProject,Diagnostic>::Err(error:Diagnostic)=>{return Result<Analyzed,InputError>::Err(INTERNAL);}};
 let plan:Plan=branch on concrete(semantic,lowered){Result<Plan,Diagnostic>::Ok(value:Plan)=>value,Result<Plan,Diagnostic>::Err(error:Diagnostic)=>{return Result<Analyzed,InputError>::Err(INTERNAL);}};
 branch on verifyConcrete(semantic,lowered,plan){Result<Unit,Diagnostic>::Ok(value:Unit)=>unit,Result<Unit,Diagnostic>::Err(error:Diagnostic)=>{return Result<Analyzed,InputError>::Err(INTERNAL);}};
 let closures:Closures=branch on convertClosures(plan){Result<Closures,Diagnostic>::Ok(value:Closures)=>value,Result<Closures,Diagnostic>::Err(error:Diagnostic)=>{return Result<Analyzed,InputError>::Err(INTERNAL);}};
 branch on verifyClosures(plan,closures){Result<Unit,Diagnostic>::Ok(value:Unit)=>unit,Result<Unit,Diagnostic>::Err(error:Diagnostic)=>{return Result<Analyzed,InputError>::Err(INTERNAL);}};
 return Result<Analyzed,InputError>::Ok(Analyzed::Checked);
},else=>unit};'''.replace('INTERNAL','InputError{status:3,path:"compiler",diagnostic:error,positionKnown:true,operation:"",kind:"",ioPhase:""}')
assert text.count(old)==1;driver.write_text(text.replace(old,new,1))
binary=args.output/'probe';built=subprocess.run([args.seed,'build',project/'mognitio.toml','-o',binary],capture_output=True,timeout=900);assert (built.returncode,built.stdout,built.stderr)==(0,b'',b''),(built.returncode,built.stdout,built.stderr)
result=subprocess.run([binary,'--internals'],capture_output=True,timeout=120);assert result.returncode==0 and result.stderr==b'',(result.returncode,result.stdout,result.stderr)
assert b'V160_CONCRETE_OK valid=2 rejected=10\n' in result.stdout and b'V160_CLOSURE_OK valid=2 rejected=4\n' in result.stdout
assert result.stdout.count(b'V160_CONCRETE_MUTANT ')==10 and result.stdout.count(b'V160_CLOSURE_MUTANT ')==4
(args.output/'internals.log').write_bytes(result.stdout);print(result.stdout.decode(),end='',flush=True)
subprocess.run(['python3',ROOT/'tests/mgnc/v160-native-profile.py','--compiler',binary,'--mode','profile','--output',args.output/'profile'],check=True,timeout=120)
subprocess.run(['python3',ROOT/'tests/mgnc/v160-generics.py','--output',args.output/'generics'],check=True,timeout=120)
for manifest in sorted((args.output/'generics').glob('*/mognitio.toml')):
 result=subprocess.run([binary,'check',manifest],capture_output=True,timeout=120);assert (result.returncode,result.stdout,result.stderr)==(0,b'',b''),(manifest.parent.name,result.returncode,result.stdout,result.stderr)
print('V160_CONCRETE_PLANNING_OK profile=31 generic=6 valid=4 rejected=14',flush=True)
