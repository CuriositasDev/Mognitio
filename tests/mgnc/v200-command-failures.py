#!/usr/bin/env python3
"""Public-command alpha resource and isolation regressions on unchanged executables.

RLIMIT_AS is applied to each launched public CLI and its real worker, or to the
normally compiled runtime artifact. A measured tiny control must pass at the
same limit where the larger workload reports a native allocation failure.
No compiler, application, allocator algorithm, or command routing is replaced.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[2]
MiB = 1024*1024


def project(folder, text):
    source = folder/'src'
    source.mkdir(parents=True)
    manifest = folder/'mognitio.toml'
    manifest.write_text('[project]\nname = "app"\nroot_namespace = "App"\n')
    (source/'app.mgn').write_text(text)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--compiler-only', action='store_true', help='development check; never claims full alpha coverage')
    args = parser.parse_args()
    payload = args.payload.resolve()
    mgn, compiler = payload/'bin/mgn', payload/'runtime/compiler'
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'complete': False, 'observations': [],
              'compiler_sha256': hashlib.sha256(compiler.read_bytes()).hexdigest(),
              'identity': json.loads((payload/'identity.json').read_text())}

    def save():
        (args.output/'results.json').write_text(json.dumps(report, indent=2)+'\n')

    def invoke(name, command, limit=None, timeout=180):
        def ceiling():
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        result = subprocess.run(list(map(str, command)), capture_output=True, timeout=timeout,
                                preexec_fn=ceiling if limit is not None else None)
        row = {'case': name, 'command': list(map(str, command)), 'limit_as': limit,
               'exit': result.returncode, 'stdout_hex': result.stdout.hex(), 'stderr_hex': result.stderr.hex()}
        report['observations'].append(row)
        save()
        return result

    control = project(args.output/'control', 'namespace App;let main:Function(List<String>):Int=function(args:List<String>):Int{0};')
    tiny_artifact = args.output/'tiny-program'
    chosen = None
    for cap in (64, 96, 128, 192, 256):
        limit = cap*MiB
        result = invoke('compiler-control-'+str(cap), [mgn, 'build', control, '-o', tiny_artifact], limit)
        if (result.returncode, result.stdout, result.stderr) == (0, b'', b''):
            chosen = limit
            break
    assert chosen is not None, 'Tiny control never succeeded under the tested resource caps'
    report['compiler_limit_as'] = chosen
    # All declarations are checked, including unused values. The bounded input
    # requires substantially more compiler heap than the tiny control project.
    magnitude = '1' + '0' * 99 if report['identity']['version'] == '2.0.0-alpha' else ''
    declarations = ''.join('let value'+str(index)+':Int='+magnitude+str(index)+';\n' for index in range(12000))
    target = project(args.output/'compiler-target', 'namespace App;\n'+declarations+
                     'let main:Function(List<String>):Int=function(args:List<String>):Int{0};\n'+
                     '@test let first:Function():Unit=function():Unit{assert true;};\n')
    output = args.output/'preserved-artifact'
    sentinel = b'preserve exact artifact bytes\x00\xff\n'
    output.write_bytes(sentinel)
    output.chmod(0o751)
    expected_mode = stat.S_IMODE(output.stat().st_mode)
    for command in ('build', 'test'):
        argv = [mgn, command, target]+(['-o', output] if command == 'build' else [])
        result = invoke('compiler-allocation-'+command, argv, chosen)
        assert result.returncode == 3 and result.stdout == b'', result
        assert b'allocation failure' in result.stderr and b'Compiler worker failed (exit 4)' in result.stderr, result
        assert b'tests:' not in result.stdout+result.stderr, result
        assert output.read_bytes() == sentinel and stat.S_IMODE(output.stat().st_mode) == expected_mode
        assert not list(args.output.glob('.mgn-*')), 'Private publication residue'
    report['compiler_failures_verified'] = True
    if args.compiler_only:
        save()
        print('V200_COMMAND_FAILURES_OK compiler-only')
        return

    retained_file = args.output/'retained-before-failure.txt'
    body = r'''namespace App;
use Std\Io\{writeTextFile,writeStdout,IoError};
let main:Function(List<String>):Int=function(args:List<String>):Int{
 branch on writeTextFile(FILE,"retained before arithmetic failure\n"){Result<Unit,IoError>::Ok(value:Unit)=>unit,Result<Unit,IoError>::Err(error:IoError)=>panic{"write failed"}};
 discard writeStdout("before bigint allocation\n");
 branch when{args->length()>0=>{return 0;},else=>unit};
 var retained:List<Int>=List<Int>[];var count:Int=0;
 loop while(count<500000){let large:Int=BIG;retained=retained->append(large*large);count=count+1;};
 discard writeStdout("unexpected completion\n");0
};
'''.replace('FILE', json.dumps(str(retained_file.resolve()))).replace('BIG', '1'+'0'*255+'1')
    runtime_manifest = project(args.output/'runtime-target', body)
    runtime = args.output/'runtime-program'
    compiled = invoke('runtime-normal-public-build', [mgn, 'build', runtime_manifest, '-o', runtime])
    assert (compiled.returncode, compiled.stdout, compiled.stderr) == (0, b'', b''), compiled
    runtime_hash = hashlib.sha256(runtime.read_bytes()).hexdigest()
    runtime_limit = 32*MiB
    control_result = invoke('runtime-control', [runtime, 'control'], runtime_limit)
    assert (control_result.returncode, control_result.stdout, control_result.stderr) == (0, b'before bigint allocation\n', b''), control_result
    failed = invoke('runtime-bigint-allocation', [runtime], runtime_limit)
    assert (failed.returncode, failed.stdout, failed.stderr) == (4, b'before bigint allocation\n', b'runtime error: allocation failure\n'), failed
    assert retained_file.read_bytes() == b'retained before arithmetic failure\n'
    # The normal run compiles the same project before its child enters main.
    # A successful short branch proves compilation fit under this separate cap.
    public_limit = 96 * MiB
    retained_file.unlink()
    public_control = invoke('public-run-control', [mgn, 'run', runtime_manifest, '--', 'control'], public_limit)
    assert (public_control.returncode, public_control.stdout, public_control.stderr) == (0, b'before bigint allocation\n', b''), public_control
    retained_file.unlink()
    public_failure = invoke('public-run-bigint-allocation', [mgn, 'run', runtime_manifest], public_limit)
    assert (public_failure.returncode, public_failure.stdout, public_failure.stderr) == (4, b'before bigint allocation\n', b'runtime error: allocation failure\n'), public_failure
    assert retained_file.read_bytes() == b'retained before arithmetic failure\n'
    assert hashlib.sha256(runtime.read_bytes()).hexdigest() == runtime_hash
    report['runtime_sha256'] = runtime_hash
    report['runtime_io_preserved'] = True

    isolation = project(args.output/'suite-isolation', r'''namespace App;
var zero:Int=0;
@test let first:Function():Unit=function():Unit{discard 18446744073709551616/zero;};
@test let second:Function():Unit=function():Unit{assert 18446744073709551616+1==18446744073709551617;};
''')
    suite = invoke('suite-division-failure-isolation', [mgn, 'test', isolation])
    assert suite.returncode == 4 and b'ERROR division-by-zero src/app.mgn::App::first' in suite.stdout, suite
    assert b'PASS src/app.mgn::App::second' in suite.stdout, suite
    assert b'tests: total=2 passed=1 failed=0 errors=1 aborted=0 not_run=0\n' in suite.stdout, suite
    assert suite.stderr.count(b'runtime error: division by zero') == 1, suite
    assert hashlib.sha256(compiler.read_bytes()).hexdigest() == report['compiler_sha256']
    report['complete'] = True
    report['passed'] = True
    save()
    print('V200_COMMAND_FAILURES_OK full observations='+str(len(report['observations'])))


if __name__ == '__main__':
    main()
