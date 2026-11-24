#!/usr/bin/env python3
"""Public alpha integer regressions; Python integers are the independent oracle.

Full: python3 tests/mgnc/v200-alpha-integers.py --compiler /alpha/compiler --output /fresh/evidence
Frontend development: replace --compiler with --frontend-driver /check-and-lower-driver.
The frontend mode never reports runtime cases as verified.
"""
import argparse
import hashlib
import json
import random
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
IMPORTS = r'use Std\Numeric\{Bits,Signed,Unsigned,IntegerConversionError,BitShiftError};use Std\Binary\{Bytes,ByteOrder,BitWidthError,ByteValueError,bytesFromInts};'
H = 1 << 64


def literal(value):
    return '(' + str(value) + ')'


def trunc(a, b):
    return (abs(a) // abs(b)) * (-1 if (a < 0) != (b < 0) else 1)


def source(checks=(), prefix='', body='0'):
    # Bounded function bodies avoid coupling numeric coverage to parser depth.
    groups = [checks[i:i + 16] for i in range(0, len(checks), 16)]
    helpers = ''.join('let verify' + str(i) + ':Function():Unit=function():Unit{' + ''.join(group) + 'unit};' for i, group in enumerate(groups))
    calls = ''.join('verify' + str(i) + '();' for i in range(len(groups)))
    return 'namespace App;' + IMPORTS + prefix + helpers + 'let main:Function(List<String>):Int=function(args:List<String>):Int{' + calls + body + '};'


def assertion(expression):
    return 'assert ' + expression + ';'


def cases():
    rng = random.Random(200)
    pairs = [(H + 1, H), (-(H + 1), H), (H + 1, -H), (-(H + 1), -H), (-7, 3), (7, -3), (-7, -3)]
    for width in [63, 64, 65, 127, 128, 255, 256, 511]:
        a = (1 << width) + rng.getrandbits(width)
        b = (1 << (width // 2)) + rng.getrandbits(width // 2)
        pairs.extend([(a, b), (-a, b), (a, -b), (-a, -b)])
    checks = [assertion('-0==0'), assertion('-(-9223372036854775808)==9223372036854775808'), assertion('-9223372036854775808/-1==9223372036854775808'), assertion('-9223372036854775808%-1==0'), assertion(str(H) + '*' + str(H) + '==' + str(H * H))]
    for a, b in pairs:
        for op, expected in [('+', a + b), ('-', a - b), ('*', a * b), ('/', trunc(a, b)), ('%', a - b * trunc(a, b))]:
            checks.append(assertion(literal(a) + op + literal(b) + '==' + literal(expected)))
        for op, expected in [('<', a < b), ('<=', a <= b), ('>', a > b), ('>=', a >= b), ('==', a == b), ('!=', a != b)]:
            checks.append(assertion('(' + literal(a) + op + literal(b) + ')==' + str(expected).lower()))
    yield 'arithmetic-oracle', source(checks), 0, b''
    hundred = int('9' * 100)
    yield 'hundred-digits', source([assertion(literal(hundred) + '>18446744073709551616'), assertion('(' + literal(hundred) + '+1)-1==' + literal(hundred)), assertion(literal(-hundred) + '<-18446744073709551616')]), 0, b''
    # This is a scale sample, not a new literal digit limit.
    long_value = '1' + '0' * 2048
    yield 'long-literal', source([assertion(long_value + '>18446744073709551616')]), 0, b''
    prefix = 'type Tag<N:Int>=product{};alias Relay<N:Int>=Bits<N>;template constant<N:Int>=function():Int{N};'
    body = 'let value:Tag<-0>=Tag<0>{};discard value;let first:Tag<18446744073709551616>=Tag<18446744073709551616>{};discard first;assert constant<18446744073709551616>()==18446744073709551616;assert constant<18446744073709551617>()>constant<18446744073709551616>();assert constant<-18446744073709551617>()<-18446744073709551616;let low:Relay<1>=Bits<1>{1};let high:Relay<64>=Bits<64>{1};discard low;discard high;0'
    yield 'value-arguments', source(prefix=prefix, body=body), 0, b''
    conversions = []
    for width in range(1, 65):
        for signed in [False, True]:
            t = 'Int<' + str(width) + ',' + ('Signed' if signed else 'Unsigned') + '>'
            lo, hi = (-(1 << (width - 1)), (1 << (width - 1)) - 1) if signed else (0, (1 << width) - 1)
            for n in sorted({lo - 1, lo, hi, hi + 1, H * H, -(H * H)}):
                success = lo <= n <= hi
                yes = 'assert converted==' + t + '{' + str(n) + '};' if success else 'assert false;'
                no = 'assert false;' if success else 'unit;'
                conversions.append('branch on ' + literal(n) + '->convertTo<' + t + '>(){Result<' + t + ',IntegerConversionError>::Ok(converted:' + t + ')=>{' + yes + '},Result<' + t + ',IntegerConversionError>::Err(error:IntegerConversionError)=>{' + no + '}};')
            conversions.append('branch on ' + t + '{' + str(hi) + '}->convertTo<Int>(){Result<Int,IntegerConversionError>::Ok(converted:Int)=>{assert converted==' + str(hi) + ';},Result<Int,IntegerConversionError>::Err(error:IntegerConversionError)=>{assert false;}};')
    for ordinal in range(0, len(conversions), 96):
        yield 'conversion-oracle-' + str(ordinal // 96), source(conversions[ordinal:ordinal + 96]), 0, b''
    fixed = [assertion('Int<8,Signed>{-128}->toBits()==Bits<8>{128}'), assertion('Int<64,Unsigned>{18446744073709551615}->toBits()==Bits<64>{18446744073709551615}'), assertion('Int<64,Signed>{-9223372036854775808}%Int<64,Signed>{-1}==Int<64,Signed>{0}')]
    for order, octets in [('BigEndian', [1, 2]), ('LittleEndian', [2, 1])]:
        checks = ''.join('branch on value->at(' + str(index) + '){Result<Bits<8>,IndexError>::Ok(octet:Bits<8>)=>{assert octet==Bits<8>{' + str(octet) + '};},Result<Bits<8>,IndexError>::Err(error:IndexError)=>{assert false;}};' for index, octet in enumerate(octets))
        fixed.append('branch on Bits<16>{258}->toBytes(ByteOrder::' + order + '){Result<Bytes,BitWidthError>::Ok(value:Bytes)=>{assert value->length()==2;' + checks + '},Result<Bytes,BitWidthError>::Err(error:BitWidthError)=>{assert false;}};')
    yield 'fixed-width', source(fixed), 0, b''
    for name, expression, error in [('fixed-overflow', 'Int<64,Signed>{9223372036854775807}+Int<64,Signed>{1}', 'integer overflow'), ('division-zero', '1/0', 'division by zero'), ('remainder-zero', '1%0', 'division by zero')]:
        yield name, source(body='discard ' + expression + ';0'), 4, ('runtime error: ' + error + '\n').encode()
    yield 'short-circuit-zero', source([assertion('true||(1/0==0)'), assertion('!(false&&(1%0==0))')]), 0, b''
    boundary = []
    for index in [H, -H, H + 1, -1, 8]:
        fields = 'assert error->index==' + str(index) + ';assert error->length==1;'
        for receiver, payload in [('List<Int>[9]', 'Int'), ('Bits<1>{1}', 'Bool'), ('one()', 'Bits<8>')]:
            boundary.append('branch on ' + receiver + '->at(' + str(index) + '){Result<' + payload + ',IndexError>::Ok(value:' + payload + ')=>{assert false;},Result<' + payload + ',IndexError>::Err(error:IndexError)=>{' + fields + '}};')
        boundary.append('branch on Bits<8>{1}->shiftLeft(' + str(index) + '){Result<Bits<8>,BitShiftError>::Ok(value:Bits<8>)=>{assert false;},Result<Bits<8>,BitShiftError>::Err(error:BitShiftError)=>{assert error->count==' + str(index) + ';assert error->width==8;}};')
        boundary.append('branch on Bits<8>{1}->shiftRight(' + str(index) + '){Result<Bits<8>,BitShiftError>::Ok(value:Bits<8>)=>{assert false;},Result<Bits<8>,BitShiftError>::Err(error:BitShiftError)=>{assert error->count==' + str(index) + ';assert error->width==8;}};')
    boundary.append('branch on "x"->slice(0,18446744073709551616){Result<String,SliceError>::Ok(value:String)=>{assert false;},Result<String,SliceError>::Err(error:SliceError)=>{assert error->start==0;assert error->end==18446744073709551616;assert error->length==1;}};')
    boundary.append('branch on bytesFromInts(List<Int>[0,18446744073709551616,-1]){Result<Bytes,ByteValueError>::Ok(value:Bytes)=>{assert false;},Result<Bytes,ByteValueError>::Err(error:ByteValueError)=>{assert error->index==1;assert error->value==18446744073709551616;}};')
    boundary.append('branch on one()->slice(0,18446744073709551616){Result<Bytes,SliceError>::Ok(value:Bytes)=>{assert false;},Result<Bytes,SliceError>::Err(error:SliceError)=>{assert error->start==0;assert error->end==18446744073709551616;assert error->length==1;}};')
    byte_prefix = 'let one:Function():Bytes=function():Bytes{branch on bytesFromInts(List<Int>[1]){Result<Bytes,ByteValueError>::Ok(value:Bytes)=>value,Result<Bytes,ByteValueError>::Err(error:ByteValueError)=>panic{"byte fixture"}}};'
    boundary.extend([
        'branch on List<Int>[9]->at(0){Result<Int,IndexError>::Ok(value:Int)=>{assert value==9;},Result<Int,IndexError>::Err(error:IndexError)=>{assert false;}};',
        'branch on Bits<1>{1}->at(0){Result<Bool,IndexError>::Ok(value:Bool)=>{assert value;},Result<Bool,IndexError>::Err(error:IndexError)=>{assert false;}};',
        'branch on one()->at(0){Result<Bits<8>,IndexError>::Ok(value:Bits<8>)=>{assert value==Bits<8>{1};},Result<Bits<8>,IndexError>::Err(error:IndexError)=>{assert false;}};',
        'branch on "x"->slice(1,1){Result<String,SliceError>::Ok(value:String)=>{assert value=="";},Result<String,SliceError>::Err(error:SliceError)=>{assert false;}};',
        'branch on one()->slice(0,0){Result<Bytes,SliceError>::Ok(value:Bytes)=>{assert value->length()==0;},Result<Bytes,SliceError>::Err(error:SliceError)=>{assert false;}};',
        'branch on Bits<8>{1}->shiftLeft(0){Result<Bits<8>,BitShiftError>::Ok(value:Bits<8>)=>{assert value==Bits<8>{1};},Result<Bits<8>,BitShiftError>::Err(error:BitShiftError)=>{assert false;}};',
        'branch on Bits<8>{128}->shiftRight(7){Result<Bits<8>,BitShiftError>::Ok(value:Bits<8>)=>{assert value==Bits<8>{1};},Result<Bits<8>,BitShiftError>::Err(error:BitShiftError)=>{assert false;}};',
    ])
    yield 'error-boundaries', source(boundary, prefix=byte_prefix), 0, b''
    yield 'retention', (ROOT / 'tests/mgnc/fixtures/v200-alpha-retention.mgn').read_text(), 0, b''
    yield 'io-retention', (ROOT / 'tests/mgnc/fixtures/v200-alpha-io-retention.mgn').read_text(), 0, b''
    for n in [0, 255, -1, 256, H]:
        yield 'main-status-' + str(n), source(body=str(n)), n if 0 <= n <= 255 else 4, b'' if 0 <= n <= 255 else b'runtime error: invalid exit status\n'


def invalid_cases():
    for text in ['00', '1_0', '0x10']:
        yield 'spelling-' + text, source(body='discard ' + text + ';0'), 'lexical'
    for n in ['0', '1', str(H)]:
        yield 'ordinary-to-bits-' + n, source(body='discard (' + n + ')->toBits();0'), 'type'
    for expression in ['Int<8,Signed>{128}', 'Int<8,Signed>{-129}', 'Int<64,Unsigned>{18446744073709551616}', 'Bits<8>{256}', 'Int<8,Signed>{1}+1']:
        yield 'typed-' + str(len(expression)) + '-' + str(sum(map(ord, expression))), source(body='discard ' + expression + ';0'), 'type'
    for width in [0, 65, H, -H]:
        yield 'relay-width-' + str(width), source(prefix='alias Relay<N:Int>=Bits<N>;', body='let value:Relay<' + str(width) + '>=Bits<1>{0};discard value;0'), 'type'
    yield 'distinct-huge-types', source(prefix='type Tag<N:Int>=product{};', body='let value:Tag<1>=Tag<18446744073709551617>{};discard value;0'), 'type'
    yield 'value-expression', source(prefix='type Tag<N:Int>=product{};', body='let value:Tag<1+7>=Tag<8>{};discard value;0'), None
    yield 'template-width-huge', source(prefix='template one<N:Int>=function():Bits<N>{Bits<N>{1}};', body='discard one<18446744073709551616>();0'), 'type'
    yield 'value-runtime-variable', source(prefix='type Tag<N:Int>=product{};', body='let n:Int=8;let value:Tag<n>=Tag<8>{};discard value;0'), None
    yield 'value-negated-parameter', source(prefix='type Tag<N:Int>=product{};alias Flip<N:Int>=Tag<-N>;', body='0'), None


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--compiler', type=Path)
    mode.add_argument('--frontend-driver', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--timeout', type=int, default=240)
    args = parser.parse_args()
    executable = (args.compiler or args.frontend_driver).resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'mode': 'full' if args.compiler else 'frontend-only', 'complete': False, 'compiler_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(), 'fixtures': {}, 'observations': []}

    def save():
        (args.output / 'results.json').write_text(json.dumps(report, indent=2) + '\n')

    def run(name, command, status=0, stderr=b'', phase=None):
        result = subprocess.run(list(map(str, command)), capture_output=True, timeout=args.timeout)
        passed = result.returncode == status and result.stdout == b'' and (result.stderr == stderr if phase is None else (('mgnc: ' + phase + ':').encode() in result.stderr if phase else bool(result.stderr)))
        row = {'case': name, 'command': list(map(str, command)), 'exit': result.returncode, 'stdout_hex': result.stdout.hex(), 'stderr_hex': result.stderr.hex(), 'passed': passed}
        report['observations'].append(row)
        save()
        assert passed, row

    for name, text, status, stderr in cases():
        folder = args.output / name
        folder.mkdir()
        path, artifact = folder / 'input.mgn', folder / 'program'
        path.write_text(text)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        report['fixtures'][name] = {'source_sha256': digest, 'runtime_verified': False}
        if args.frontend_driver:
            run(name + '-frontend', [executable, path])
        else:
            for verb in ['check', 'lower']:
                run(name + '-' + verb, [executable, verb, path])
            run(name + '-build', [executable, 'build', path, '-o', artifact])
            runtime_args = [path, folder, folder / 'io-output.txt'] if name == 'io-retention' else []
            run(name + '-native', [artifact] + runtime_args, status, stderr)
            report['fixtures'][name]['runtime_verified'] = True
            report['fixtures'][name]['artifact_sha256'] = hashlib.sha256(artifact.read_bytes()).hexdigest()
            if name in ['retention', 'io-retention', 'error-boundaries']:
                stress = folder / 'stress.json'
                run(name + '-stress', [sys.executable, Path(__file__).with_name('v160-native-observe.py'), '--stress', '--report', stress, '--', artifact] + runtime_args, status, stderr)
                observation = json.loads(stress.read_text())
                assert observation['stress'] and observation['heap']['collections'] > 0, observation
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        save()
    for name, text, phase in invalid_cases():
        folder = args.output / name
        folder.mkdir()
        path, artifact = folder / 'input.mgn', folder / 'program'
        path.write_text(text)
        artifact.write_bytes(b'preserved')
        for verb in (['frontend'] if args.frontend_driver else ['check', 'lower', 'build']):
            command = [executable, path] if args.frontend_driver else [executable, verb, path] + (['-o', artifact] if verb == 'build' else [])
            # None means any static diagnostic phase, still requiring exit 1.
            run(name + '-' + verb, command, 1, phase=phase if phase else '')
            assert artifact.read_bytes() == b'preserved'
    report['complete'] = bool(args.compiler)
    report['passed'] = True
    save()
    print('V200_ALPHA_INTEGERS_OK mode=' + report['mode'] + ' fixtures=' + str(len(report['fixtures'])) + ' observations=' + str(len(report['observations'])))


if __name__ == '__main__':
    main()
