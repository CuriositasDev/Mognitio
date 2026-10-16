#!/usr/bin/env python3
"""Reproduce the ordinary Unicode scalar lookup source without external data."""
from pathlib import Path
import argparse
PREFIX = 'namespace Mgnc\\WholeUnicode;\n// Generated scalar enumeration; see tests/mgnc/generate-unicode.py.\nuse Mgnc\\TextUtil\\{code as ascii};\n'
SUFFIX = '\n\npublic let number:Function(String):Int=function(scalar:String):Int{\n let ordinary:Int=ascii(scalar);branch when{ordinary>=0=>{return ordinary;},else=>unit};var value:Int=0;loop over(pages as page:String){loop over(page->scalars() as candidate:String){branch when{candidate==scalar=>{return value;},else=>unit};value=value+1;branch when{value==55296=>{value=57344;},else=>unit};};};-1\n};\n'
def generate():
    def escaped(value):
        if value < 32 or value == 127:
            return "\\u{"+format(value,"x")+"}"
        if value in (34,92):
            return "\\"+chr(value)
        return chr(value)
    pages=['"'+''.join(escaped(value) for value in range(index,min(index+4096,0x110000)) if not 0xD800<=value<=0xDFFF)+'"' for index in range(0,0x110000,4096)]
    return PREFIX+"let pages:List<String>=List<String>[\n"+",\n".join(pages)+"];"+SUFFIX
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--check",action="store_true");parser.add_argument("path",type=Path);args=parser.parse_args()
    data=generate().encode("utf-8")
    if args.check:
        assert args.path.read_bytes()==data,"Unicode enumeration differs from its generator"
    else:
        args.path.write_bytes(data)
if __name__=="__main__":main()
