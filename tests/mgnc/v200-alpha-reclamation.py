#!/usr/bin/env python3
"""Observe reclamation after short/long temporary-bigint workloads."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    template = (ROOT / 'tests/mgnc/fixtures/v200-alpha-reclamation.mgn').read_text()
    assert template.count('let rounds:Int=64;') == 1
    report = {'compiler_sha256': hashlib.sha256(compiler.read_bytes()).hexdigest(), 'passed': False, 'runs': []}
    for count in [64, 4096]:
        folder = args.output / str(count)
        folder.mkdir()
        source, binary, observation = folder / 'input.mgn', folder / 'program', folder / 'stress.json'
        source.write_text(template.replace('let rounds:Int=64;', 'let rounds:Int=' + str(count) + ';'))
        for command in [[compiler, 'build', source, '-o', binary], [binary], [sys.executable, ROOT / 'tests/mgnc/v160-native-observe.py', '--stress', '--report', observation, '--', binary]]:
            result = subprocess.run(list(map(str, command)), capture_output=True, timeout=240)
            assert (result.returncode, result.stdout, result.stderr) == (0, b'', b''), (list(map(str, command)), result)
        actual = json.loads(observation.read_text())
        assert actual['stress'] and actual['heap']['collections'] > 0, actual
        heap = {key: value for key, value in actual['heap'].items() if key != 'root'}
        report['runs'].append({'iterations': count, 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'artifact_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'heap': heap})
    short, long = report['runs']
    assert long['heap']['allocations'] > short['heap']['allocations'] * 16, report
    assert long['heap']['collections'] > short['heap']['collections'] * 16, report
    # Both runs end with the same managed survivor values and shape. The bound
    # allows one small allocation's physical size if runtime ordering changes.
    assert long['heap']['live'] <= short['heap']['live'] + 128, report
    assert long['heap']['mapped'] <= short['heap']['mapped'] + 1048576, report
    report['passed'] = True
    report['interpretation'] = '64 times more temporary workload and collections with bounded final live and mapped heap; temporaries are reclaimed after their last uses.'
    (args.output / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    print('V200_ALPHA_RECLAMATION_OK short_live=' + str(short['heap']['live']) + ' long_live=' + str(long['heap']['live']) + ' short_allocations=' + str(short['heap']['allocations']) + ' long_allocations=' + str(long['heap']['allocations']))


if __name__ == '__main__':
    main()
