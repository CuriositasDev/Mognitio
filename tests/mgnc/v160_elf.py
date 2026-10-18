"""Independent public ELF geometry check for full-backend executables."""
import struct

def elf(data):
    assert len(data) > 120
    assert data[:16] == b"\x7fELF\x02\x01\x01" + bytes(9)
    header = struct.unpack_from("<HHIQQQIHHHHHH", data, 16)
    assert header == (2, 62, 1, 0x400078, 64, 0, 0, 64, 56, 1, 0, 0, 0)
    segment = struct.unpack_from("<IIQQQQQQ", data, 64)
    assert segment == (1, 5, 0, 0x400000, 0x400000, len(data), len(data), 4096)
    assert segment[3] <= header[3] < segment[3] + segment[5]
