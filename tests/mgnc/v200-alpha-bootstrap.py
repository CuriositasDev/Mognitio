#!/usr/bin/env python3
"""Pinned 1.9/alpha compatibility cells and A12 with no seed or checkout mounted."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
IMPORTS = r'use Std\Numeric\{Bits,Signed,Unsigned,IntegerConversionError};'
MANIFEST = '[project]\nname="app"\nroot_namespace="App"\n'


def program(body='0', prefix=''):
    return 'namespace App;' + IMPORTS + prefix + 'let main:Function(List<String>):Int=function(args:List<String>):Int{' + body + '};'


def fixtures():
    yield 'tag-extrema', program('let low:Tag<-9223372036854775808>=Tag<-9223372036854775808>{};let high:Tag<9223372036854775807>=Tag<9223372036854775807>{};discard low;discard high;0', 'type Tag<N:Int>=product{};'), 0, 0
    for name, value in [('tag-below', '-9223372036854775809'), ('tag-above', '9223372036854775808')]:
        yield name, program('let value:Tag<' + value + '>=Tag<' + value + '>{};discard value;0', 'type Tag<N:Int>=product{};'), None, 0
    yield 'zero-identity', program('let value:Tag<-0>=Tag<0>{};discard value;0', 'type Tag<N:Int>=product{};'), 0, 0
    # Exactly the same source observes the change without an alpha-only bare literal.
    yield 'unsigned64-to-ordinary', program('branch on Int<64,Unsigned>{18446744073709551615}->convertTo<Int>(){Result<Int,IntegerConversionError>::Ok(value:Int)=>{branch on value->convertTo<Int<64,Unsigned>>(){Result<Int<64,Unsigned>,IntegerConversionError>::Ok(back:Int<64,Unsigned>)=>{assert back==Int<64,Unsigned>{18446744073709551615};},Result<Int<64,Unsigned>,IntegerConversionError>::Err(error:IntegerConversionError)=>{assert false;}};17},Result<Int,IntegerConversionError>::Err(error:IntegerConversionError)=>23}'), 23, 17
    yield 'unsigned64-to-signed64', program('branch on Int<64,Unsigned>{18446744073709551615}->convertTo<Int<64,Signed>>(){Result<Int<64,Signed>,IntegerConversionError>::Ok(value:Int<64,Signed>)=>{assert false;},Result<Int<64,Signed>,IntegerConversionError>::Err(error:IntegerConversionError)=>unit};0'), 0, 0
    yield 'unsigned64-bits', program('assert Int<64,Unsigned>{18446744073709551615}->toBits()==Bits<64>{18446744073709551615};assert Bits<64>{18446744073709551615}->asInteger<Unsigned>()==Int<64,Unsigned>{18446744073709551615};0'), 0, 0
    yield 'signed64-ordinary-extrema', program('branch on Int<64,Signed>{-9223372036854775808}->convertTo<Int>(){Result<Int,IntegerConversionError>::Ok(value:Int)=>{assert value== -9223372036854775808;},Result<Int,IntegerConversionError>::Err(error:IntegerConversionError)=>{assert false;}};branch on Int<64,Signed>{9223372036854775807}->convertTo<Int>(){Result<Int,IntegerConversionError>::Ok(value:Int)=>{assert value==9223372036854775807;},Result<Int,IntegerConversionError>::Err(error:IntegerConversionError)=>{assert false;}};0'), 0, 0
    yield 'adjacent-conversions', program('branch on (9223372036854775808)->convertTo<Int<64,Signed>>(){Result<Int<64,Signed>,IntegerConversionError>::Ok(value:Int<64,Signed>)=>{assert false;},Result<Int<64,Signed>,IntegerConversionError>::Err(error:IntegerConversionError)=>unit};branch on (9223372036854775808)->convertTo<Int<64,Unsigned>>(){Result<Int<64,Unsigned>,IntegerConversionError>::Ok(value:Int<64,Unsigned>)=>{assert value==Int<64,Unsigned>{9223372036854775808};},Result<Int<64,Unsigned>,IntegerConversionError>::Err(error:IntegerConversionError)=>{assert false;}};branch on (-9223372036854775809)->convertTo<Int<64,Signed>>(){Result<Int<64,Signed>,IntegerConversionError>::Ok(value:Int<64,Signed>)=>{assert false;},Result<Int<64,Signed>,IntegerConversionError>::Err(error:IntegerConversionError)=>unit};0'), None, 0
    migration = 'let encode:Function(Int):Result<Bits<64>,IntegerConversionError>=function(value:Int):Result<Bits<64>,IntegerConversionError>{branch on value->convertTo<Int<64,Signed>>(){Result<Int<64,Signed>,IntegerConversionError>::Ok(fixed:Int<64,Signed>)=>Result<Bits<64>,IntegerConversionError>::Ok(fixed->toBits()),Result<Int<64,Signed>,IntegerConversionError>::Err(error:IntegerConversionError)=>Result<Bits<64>,IntegerConversionError>::Err(error)}};'
    yield 'explicit-bits-migration', program('branch on encode(-1){Result<Bits<64>,IntegerConversionError>::Ok(value:Bits<64>)=>{assert value==Bits<64>{18446744073709551615};},Result<Bits<64>,IntegerConversionError>::Err(error:IntegerConversionError)=>{assert false;}};0', migration), 0, 0
    yield 'migration-outside-signed64', program('branch on encode(9223372036854775808){Result<Bits<64>,IntegerConversionError>::Ok(value:Bits<64>)=>{assert false;},Result<Bits<64>,IntegerConversionError>::Err(error:IntegerConversionError)=>unit};0', migration), None, 0
    yield 'ordinary-widthless-bits', program('assert 1->toBits()==Bits<64>{1};0'), 0, None
    yield 'unchanged-invalid-width', program('discard Bits<65>{1};0'), None, None
    for number in ['-9223372036854775809', '-9223372036854775808', '9223372036854775807', '9223372036854775808']:
        for family, value_type in [('bits', 'Bits<' + number + '>'), ('fixed', 'Int<' + number + ',Signed>')]:
            yield 'width-' + family + '-' + number, program('discard ' + value_type + '{0};0'), None, None
    for spelling in ['00', '1_0', '0x10']:
        yield 'spelling-' + spelling, program('discard ' + spelling + ';0'), None, None
    yield 'ordinary-max-plus-one', program('let exact:Int=9223372036854775807+1;assert exact>9223372036854775807;branch on exact->convertTo<Int<64,Unsigned>>(){Result<Int<64,Unsigned>,IntegerConversionError>::Ok(value:Int<64,Unsigned>)=>{assert value==Int<64,Unsigned>{9223372036854775808};},Result<Int<64,Unsigned>,IntegerConversionError>::Err(error:IntegerConversionError)=>{assert false;}};0'), (4, b'runtime error: integer overflow\n'), 0
    yield 'fixed-overflow-unchanged', program('discard Int<64,Signed>{9223372036854775807}+Int<64,Signed>{1};0'), (4, b'runtime error: integer overflow\n'), (4, b'runtime error: integer overflow\n')
    yield 'fixed-min-remainder-unchanged', program('assert Int<64,Signed>{-9223372036854775808}%Int<64,Signed>{-1}==Int<64,Signed>{0};0'), 0, 0



def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed-payload', required=True, type=Path)
    parser.add_argument('--alpha-payload', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'schema': 1, 'complete': False, 'cross_version': [], 'isolation': [], 'payloads': {}}

    def save():
        (args.output / 'results.json').write_text(json.dumps(report, indent=2) + '\n')

    def call(section, name, command, status=0, diagnostic=False, stdout=None, cwd=None, stderr=b''):
        result = subprocess.run(list(map(str, command)), cwd=cwd, capture_output=True, timeout=120)
        passed = result.returncode == status and (result.stdout == stdout if stdout is not None else (result.stdout == b'' or name.endswith('-test'))) and (bool(result.stderr) if diagnostic else result.stderr == stderr)
        row = {'case': name, 'command': list(map(str, command)), 'exit': result.returncode, 'stdout': result.stdout.decode(errors='replace'), 'stderr': result.stderr.decode(errors='replace'), 'passed': passed}
        report[section].append(row)
        save()
        assert passed, row
        return result

    seed = args.seed_payload.resolve()
    alpha = args.alpha_payload.resolve() if args.alpha_payload else None
    for version, payload in [('seed', seed)] + ([('alpha', alpha)] if alpha else []):
        identity = json.loads((payload / 'identity.json').read_text())
        assert identity['version'] == ('1.9.0' if version == 'seed' else '2.0.0-alpha'), identity['version']
        if version == 'seed':
            lock = json.loads((ROOT / 'packaging/alpha-seed.json').read_text())
            assert identity['build'] == lock['build'] and digest(payload / 'runtime/compiler') == lock['compilerSha256'], 'Unpinned seed compiler'
            assert identity['inputs']['commit'] == lock['receipt']['sourceCommit'], 'Unpinned seed source'
        report['payloads'][version] = {'version': identity['version'], 'build': identity['build'], 'path': str(payload), 'compiler_sha256': digest(payload / 'runtime/compiler'), 'identity_sha256': digest(payload / 'identity.json'), 'payload_sha256': digest(payload / 'payload.json')}
        for name, text, old_status, alpha_status in fixtures():
            folder = args.output / version / name
            (folder / 'src').mkdir(parents=True)
            manifest = folder / 'mognitio.toml'
            manifest.write_text(MANIFEST)
            source = folder / 'src/app.mgn'
            source.write_text(text)
            expected = old_status if version == 'seed' else alpha_status
            expected_stderr = b''
            if isinstance(expected, tuple):
                expected, expected_stderr = expected
            report['payloads'][version].setdefault('fixtures', {})[name] = digest(source)
            executable = folder / 'program'
            if expected is None:
                executable.write_bytes(b'preserved')
                for verb in ['run', 'build']:
                    command = [payload / 'bin/mgn', verb, manifest] + (['-o', executable] if verb == 'build' else [])
                    call('cross_version', version + '-' + name + '-' + verb, command, 1, diagnostic=True)
                    assert executable.read_bytes() == b'preserved'
            else:
                call('cross_version', version + '-' + name + '-run', [payload / 'bin/mgn', 'run', manifest], expected, stderr=expected_stderr)
                call('cross_version', version + '-' + name + '-build', [payload / 'bin/mgn', 'build', manifest, '-o', executable])
                call('cross_version', version + '-' + name + '-elf', [executable], expected, stderr=expected_stderr)
    if not alpha:
        report['pending'] = 'Alpha payload required for cross-version and A12 execution'
        save()
        print('V200_ALPHA_BOOTSTRAP_SEED_OK cases=' + str(len(list(fixtures()))) + ' alpha_pending=true')
        return
    assert shutil.which('bwrap'), 'bwrap is required; isolation cannot be replaced with an ordinary child'
    work = args.output / 'isolated'
    work.mkdir()
    text = program('assert 18446744073709551616*18446744073709551616==340282366920938463463374607431768211456;assert -9223372036854775808/-1==9223372036854775808;0', '@test let wide:Function():Unit=function():Unit{assert 18446744073709551616+1==18446744073709551617;};')
    for name in ['one', 'two']:
        folder = work / name
        (folder / 'src').mkdir(parents=True)
        (folder / 'mognitio.toml').write_text(MANIFEST)
        (folder / 'src/app.mgn').write_text(text)

    def isolated(command, directory='one', payload=True):
        base = ['bwrap', '--unshare-all', '--die-with-parent', '--new-session', '--clearenv', '--ro-bind', '/usr', '/usr', '--tmpfs', '/usr/lib/mognitio', '--symlink', 'usr/bin', '/bin', '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/lib64', '/lib64', '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--tmpfs', '/home', '--bind', str(work), '/work', '--chdir', '/work/' + directory, '--setenv', 'PATH', '/usr/bin:/bin', '--setenv', 'HOME', '/tmp']
        for launcher in ['/usr/bin/mgn', '/usr/bin/mognitio-lsp']:
            if Path(launcher).exists():
                base += ['--ro-bind', '/dev/null', launcher]
        if payload:
            base += ['--ro-bind', str(alpha), '/alpha']
        return base + ['--'] + command

    forbidden = [str(seed), str(ROOT), '/usr/lib/mognitio/' + next(Path('/usr/lib/mognitio').iterdir()).name, '/home/takuya9622/Projects/Mognitio']
    attest = 'import os,json;paths=' + repr(forbidden) + ';assert not any(os.path.exists(p) for p in paths);assert not os.listdir("/usr/lib/mognitio");assert not any(os.access(p,os.X_OK) for p in ["/usr/bin/mgn","/usr/bin/mognitio-lsp"]);print(json.dumps({"forbidden_absent":paths,"installed_seed_hidden":True,"installed_launchers_disabled":True}))'
    call('isolation', 'mount-attestation', isolated(['/usr/bin/python3', '-I', '-c', attest]), stdout=(json.dumps({'forbidden_absent': forbidden, 'installed_seed_hidden': True, 'installed_launchers_disabled': True}) + '\n').encode())
    # The attestation has a structured stdout, unlike language commands.
    call('isolation', 'alpha-cli-run', isolated(['/alpha/bin/mgn', 'run', 'mognitio.toml']))
    call('isolation', 'alpha-cli-build-one', isolated(['/alpha/bin/mgn', 'build', 'mognitio.toml', '-o', 'program']))
    call('isolation', 'alpha-cli-build-two', isolated(['/alpha/bin/mgn', 'build', 'mognitio.toml', '-o', 'program'], 'two'))
    first, second = work / 'one/program', work / 'two/program'
    assert first.read_bytes() == second.read_bytes(), 'Directory-dependent ELF generation'
    report['reproducible_elf_sha256'] = digest(first)
    test = call('isolation', 'alpha-cli-test', isolated(['/alpha/bin/mgn', 'test', 'mognitio.toml']))
    assert b'total=1 passed=1 failed=0 errors=0' in test.stdout, test
    bare = ['bwrap', '--unshare-all', '--die-with-parent', '--new-session', '--clearenv', '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--ro-bind', str(first), '/program', '--chdir', '/', '--', '/program']
    call('isolation', 'standalone-elf-no-compiler', bare)

    child = subprocess.Popen(isolated(['/alpha/bin/mognitio-lsp', '--stdio']), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    buffer = bytearray()

    def send(message):
        raw = json.dumps({'jsonrpc': '2.0', **message}, separators=(',', ':')).encode()
        child.stdin.write(b'Content-Length: ' + str(len(raw)).encode() + b'\r\n\r\n' + raw)
        child.stdin.flush()

    def receive(predicate):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            separator = buffer.find(b'\r\n\r\n')
            if separator >= 0:
                size = int(bytes(buffer[:separator]).decode().split(':', 1)[1].strip())
                if len(buffer) >= separator + 4 + size:
                    item = json.loads(bytes(buffer[separator + 4:separator + 4 + size]))
                    del buffer[:separator + 4 + size]
                    if predicate(item):
                        return item
                    continue
            ready, _, _ = select.select([child.stdout], [], [], max(0, deadline - time.monotonic()))
            if ready:
                chunk = os.read(child.stdout.fileno(), 65536)
                assert chunk, 'LSP exited before response'
                buffer.extend(chunk)
        raise AssertionError('LSP response timed out')

    try:
        send({'id': 1, 'method': 'initialize', 'params': {'rootUri': 'file:///work/one', 'capabilities': {}}})
        initialized = receive(lambda item: item.get('id') == 1)
        assert 'result' in initialized, initialized
        send({'method': 'initialized', 'params': {}})
        uri = 'file:///work/one/src/app.mgn'
        send({'method': 'textDocument/didOpen', 'params': {'textDocument': {'uri': uri, 'languageId': 'mognitio', 'version': 1, 'text': text}}})
        observations = []
        for version, contents, bad in [(1, text, False), (2, program('discard 1->toBits();0'), True), (3, text, False)]:
            if version > 1:
                send({'method': 'textDocument/didChange', 'params': {'textDocument': {'uri': uri, 'version': version}, 'contentChanges': [{'text': contents}]}})
            reply = receive(lambda item: item.get('method') == 'textDocument/publishDiagnostics' and item.get('params', {}).get('uri') == uri and item['params'].get('version') == version)
            diagnostics = reply['params']['diagnostics']
            assert bool(diagnostics) == bad, reply
            if bad:
                assert len(diagnostics) == 1 and 'ordinary Int' in diagnostics[0]['message'], reply
                start = contents.index('toBits')
                assert diagnostics[0]['range'] == {'start': {'line': 0, 'character': start}, 'end': {'line': 0, 'character': start + len('toBits')}}, reply
            observations.append(reply['params'])
        send({'id': 9, 'method': 'shutdown', 'params': {}})
        receive(lambda item: item.get('id') == 9)
        send({'method': 'exit'})
        child.stdin.close()
        child.wait(timeout=10)
        stderr = child.stderr.read()
        assert child.returncode == 0 and stderr in [b'', b'mognitio-lsp: Memory enforcement: best-effort process-tree RSS\n'], (child.returncode, stderr)
        report['lsp'] = {'isolated': True, 'observations': observations, 'exit': child.returncode, 'stderr': stderr.decode()}
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
    report['complete'] = True
    save()
    print('V200_ALPHA_BOOTSTRAP_OK cross_version_cases=' + str(2 * len(list(fixtures()))) + ' isolated_cli=run,build,test,lsp standalone=true reproducible=true')


if __name__ == '__main__':
    main()
