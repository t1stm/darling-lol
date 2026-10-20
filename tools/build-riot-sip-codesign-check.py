#!/usr/bin/env python3
from pathlib import Path
import shlex, subprocess

root = Path(__file__).resolve().parent.parent
flags = {}
for line in (root / 'build/darling-src/build/src/frameworks/CoreVideo/CMakeFiles/CoreVideo.dir/flags.make').read_text().splitlines():
    if line.startswith('C_') and ' = ' in line:
        key, value = line.split(' = ', 1)
        flags[key] = shlex.split(value)

obj = root / 'build/riot-sip-codesign-check.o'
subprocess.run(['clang', *flags['C_DEFINES'], *flags['C_INCLUDES'], *flags['C_FLAGS'],
                '-O2', '-c', str(root / 'tools/riot-sip-codesign-check.c'), '-o', str(obj)], check=True)
sdk = Path('@DARLING_SDK@')
if not sdk.is_dir():
    sdk = Path('/usr/local/libexec/darling')
subprocess.run(['clang', '-target', 'x86_64-apple-macosx11.0', '-fuse-ld=lld', '-nostdlib',
                '-isysroot', str(sdk), str(obj), '-lSystem', '-o',
                str(root / 'build/riot-sip-codesign-check')], check=True)

