#!/usr/bin/env python3
"""Build the CoreGraphics display and cursor compatibility override."""
from pathlib import Path
import shlex
import subprocess
root = Path(__file__).resolve().parent.parent
folder = root / 'build/darling-src/build/src/external/cocotron/CoreGraphics'
flags = {}
for line in (folder / 'CMakeFiles/CoreGraphics.dir/flags.make').read_text().splitlines():
    if line.startswith('C_') and ' = ' in line:
        key, value = line.split(' = ', 1)
        flags[key] = shlex.split(value)
link = shlex.split((folder / 'CMakeFiles/CoreGraphics.dir/link.txt').read_text())
for name in ('CGDirectDisplay', 'CGSubWindow'):
    obj = root / f'build/riot-{name}.o'
    subprocess.run(['clang', *flags['C_DEFINES'], *flags['C_INCLUDES'], *flags['C_FLAGS'],
                    '-O2', '-Wno-macro-redefined', '-c',
                    str(root / f'build/darling-src/src/external/cocotron/CoreGraphics/{name}.m'),
                    '-o', str(obj)], check=True)
    link[link.index(f'CMakeFiles/CoreGraphics.dir/{name}.m.o')] = str(obj)
link[link.index('-o') + 1] = str(root / 'build/riot-CoreGraphics')
subprocess.run(link, cwd=folder, check=True)
built_binary = root / 'build/riot-CoreGraphics'
destinations = [
    Path.home() / '.darling/System/Library/Frameworks/CoreGraphics.framework/Versions/A/CoreGraphics',
    Path.home() / '.darling/Users/fgeroldi/RuntimeFrameworks/CoreGraphics.framework/Versions/A/CoreGraphics',
]
for dst in destinations:
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(built_binary, dst)
        print(f'Installed CoreGraphics to {dst}')
    except Exception as e:
        print(f'Could not install to {dst}: {e}')
print('Built isolated CoreGraphics compatibility override')
