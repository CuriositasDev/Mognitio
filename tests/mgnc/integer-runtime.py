#!/usr/bin/env python3
"""Execute actual 1.9-seed-compiled integer emitter bytes against Python integers.

The five-module fixture compiles the checked-in Mognitio emitter, serializes its
Machine records, applies native helper relocations and executes that byte stream.
Allocator callbacks provide leaf storage; product GC/failure tests are separate.
No C compiler, assembler, or external bigint library is used by this test.
"""
import argparse
import ctypes
from pathlib import Path
import random
import shutil
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PROBE = r'''namespace Mgnc;
use Mgnc\Data\{empty,number};
use Mgnc\Machine\{Code,Record,flush};
use Mgnc\WholeInteger\{emit};
use Std\Io\{writeStdout};
let main:Function(List<String>):Int=function(args:List<String>):Int{
 let code:Code=flush(emit(Code{records:empty<Record>(),nextLabel:256,pending:List<Int>[]}));
 loop over(code->records->pages->append(code->records->tail) as page:List<Record>){loop over(page as record:Record){
  var line:String=number(record->kind)+" "+number(record->value)+" "+number(record->target);
  loop over(record->bytes as byte:Int){line=line+" "+number(byte);};discard writeStdout(line+"\n");
 };};0
};
'''


class Emitted:
    def __init__(self, records):
        self.libc = ctypes.CDLL(None)
        self.libc.calloc.argtypes = [ctypes.c_size_t, ctypes.c_size_t]
        self.libc.calloc.restype = ctypes.c_void_p
        self.libc.free.argtypes = [ctypes.c_void_p]
        self.libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_long]
        self.libc.mmap.restype = ctypes.c_void_p
        self.libc.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        allocator = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64)
        self.allocate = allocator(lambda size, descriptor: self.libc.calloc(1, size))
        self.fail = ctypes.CFUNCTYPE(None)(lambda: self.libc.abort())
        data = bytearray()
        labels, relocations = {}, []
        for line in records.decode().splitlines():
            kind, value, target, *octets = map(int, line.split())
            data.extend(octets)
            if kind == 1:
                assert target not in labels
                labels[target] = len(data)
            elif kind == 2:
                relocations.append((len(data), target))
                data.extend(b'\0'*4)
            else:
                assert kind == 0
        # Near trampolines make every native rel32 relocation independent of the
        # callback's virtual address. All internal relative branches stay intact.
        for target, callback in [(1, self.fail), (5, self.fail), (10, self.allocate)]:
            labels[target] = len(data)
            address = ctypes.cast(callback, ctypes.c_void_p).value
            data.extend(b'\x49\xbb'+struct.pack('<Q', address)+b'\x41\xff\xe3')
        wrappers = []
        for target in range(200, 209):
            wrappers.append(len(data))
            data.extend(b'\x48\x89\xf8\x48\x89\xf1\xe9')
            relocations.append((len(data), target))
            data.extend(b'\0'*4)
        word_offset = len(data)
        data.extend(b'\x53\x48\x89\xf3\x48\x89\xf8\xe8')
        relocations.append((len(data), 209))
        data.extend(b'\0'*4)
        data.extend(b'\x48\x89\x03\x48\x89\x53\x08\x48\x89\x4b\x10\x5b\xc3')
        for offset, target in relocations:
            struct.pack_into('<i', data, offset, labels[target]-offset-4)
        self.size = len(data)
        self.memory = self.libc.mmap(None, self.size, 7, 0x22, -1, 0)
        assert self.memory not in (None, (1 << 64)-1)
        ctypes.memmove(self.memory, bytes(data), self.size)
        binary = ctypes.CFUNCTYPE(ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint64)
        self.operations = [binary(self.memory+offset) for offset in wrappers[:7]]
        unary = ctypes.CFUNCTYPE(ctypes.c_uint64, ctypes.c_uint64)
        self.signed = unary(self.memory+wrappers[7])
        self.unsigned = unary(self.memory+wrappers[8])
        self.word = ctypes.CFUNCTYPE(None, ctypes.c_uint64, ctypes.c_void_p)(self.memory+word_offset)

    def decode(self, word):
        if word & 1:
            return ctypes.c_int64(word).value >> 1
        sign = ctypes.c_int64.from_address(word+24).value
        count = ctypes.c_uint64.from_address(word+32).value
        assert sign in (-1, 1) and 0 < count < 1000
        limbs = [ctypes.c_uint32.from_address(word+40+index*4).value for index in range(count)]
        assert limbs[-1] != 0 and all(limb < (1 << 30) for limb in limbs)
        number = sign*sum(limb << (30*index) for index, limb in enumerate(limbs))
        assert number < -(1 << 62) or number >= (1 << 62), ('noncanonical', number)
        self.libc.free(word)
        return number

    def close(self):
        assert self.libc.munmap(self.memory, self.size) == 0


def encode(number):
    if -(1 << 62) <= number < (1 << 62):
        return (number*2+1) & ((1 << 64)-1), None
    magnitude, limbs = abs(number), []
    while magnitude:
        limbs.append(magnitude & ((1 << 30)-1))
        magnitude >>= 30
    buffer = ctypes.create_string_buffer(40+4*len(limbs))
    ctypes.c_int64.from_buffer(buffer, 24).value = -1 if number < 0 else 1
    ctypes.c_uint64.from_buffer(buffer, 32).value = len(limbs)
    for index, limb in enumerate(limbs):
        ctypes.c_uint32.from_buffer(buffer, 40+index*4).value = limb
    return ctypes.addressof(buffer), buffer


def verify(emitted):
    rng = random.Random(20261124)
    edge = [0, 1, -1, (1 << 62)-1, -(1 << 62), 1 << 62, -(1 << 62)-1,
            (1 << 63)-1, -(1 << 63), (1 << 64)-1, 1 << 64,
            (1 << 150)+31, -(1 << 300)+13]
    pairs = [(left, right) for left in edge for right in edge]
    pairs += [(rng.getrandbits(rng.randrange(1, 1001))*rng.choice([-1, 1]),
               rng.getrandbits(rng.randrange(1, 1001))*rng.choice([-1, 1])) for _ in range(1000)]
    pairs += [(rng.randrange(-(1 << 62), 1 << 62), rng.randrange(-(1 << 62), 1 << 62))
              for _ in range(3000)]
    checks = 0
    for left, right in pairs:
        lhs, keep_left = encode(left)
        rhs, keep_right = encode(right)
        quotient = (abs(left)//abs(right)*(-1 if (left < 0) != (right < 0) else 1)) if right else 0
        expected = [left+right, left-right, left*right, quotient, left-quotient*right,
                    (left > right)-(left < right), -left]
        for operation, wanted in enumerate(expected):
            if right == 0 and operation in (3, 4):
                continue
            result = emitted.operations[operation](lhs, rhs)
            actual = ctypes.c_int64(result).value if operation == 5 else emitted.decode(result)
            assert actual == wanted, (operation, left, right, actual, wanted)
            checks += 1
        for number, word in [(left, lhs), (right, rhs)]:
            out = (ctypes.c_uint64*3)()
            emitted.word(word, out)
            assert out[1] == int(-(1 << 63) <= number < (1 << 63)), (number, list(out))
            assert out[2] == int(0 <= number < (1 << 64)), (number, list(out))
            if out[1] or out[2]:
                assert out[0] == number & ((1 << 64)-1)
            checks += 1
    for number in edge[:11]+[rng.randrange(-(1 << 63), 1 << 63) for _ in range(1000)]:
        if -(1 << 63) <= number < (1 << 63):
            assert emitted.decode(emitted.signed(number & ((1 << 64)-1))) == number
            checks += 1
    for number in [0, 1, (1 << 62)-1, 1 << 62, 1 << 63, (1 << 64)-1]+[rng.getrandbits(64) for _ in range(1000)]:
        assert emitted.decode(emitted.unsigned(number)) == number
        checks += 1
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', required=True, type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='mgn-integer-runtime-') as temporary:
        project = Path(temporary)/'project'
        source = project/'src'
        source.mkdir(parents=True)
        for module in ['Data', 'Machine', 'WholeX64', 'WholeABI', 'WholeInteger']:
            shutil.copytree(ROOT/'compiler/mgnc/src'/module, source/module)
        (project/'mognitio.toml').write_text('[project]\nname = "integerprobe"\nroot_namespace = "Mgnc"\n')
        (source/'integerprobe.mgn').write_text(PROBE)
        image = Path(temporary)/'probe'
        built = subprocess.run([args.seed.resolve(), 'build', project/'mognitio.toml', '-o', image],
                               capture_output=True, timeout=180)
        assert (built.returncode, built.stdout, built.stderr) == (0, b'', b''), built.stderr
        result = subprocess.run([image], capture_output=True, timeout=30)
        assert result.returncode == 0 and not result.stderr, result.stderr
        emitted = Emitted(result.stdout)
        try:
            checks = verify(emitted)
        finally:
            emitted.close()
    print(f'INTEGER_RUNTIME_OK checks={checks}')


if __name__ == '__main__':
    main()
