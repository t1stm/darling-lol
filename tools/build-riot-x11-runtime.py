#!/usr/bin/env python3
"""Compile the changed X11 event handler and relink the existing backend."""
import json
import shlex
import subprocess
from pathlib import Path
project = Path(__file__).resolve().parent.parent
framework = project / 'build/darling-src/build/src/external/cocotron/AppKit'
config_path = project / 'build/config.json'
sdk = json.loads(config_path.read_text())['sdk'] if config_path.exists() else '/usr/local/libexec/darling'
flags = {}
for line in (framework / 'CMakeFiles/X11_backend.dir/flags.make').read_text().splitlines():
    if line.startswith('C_') and ' = ' in line:
        key, value = line.split(' = ', 1)
        flags[key] = shlex.split(value)
link = shlex.split((framework / 'CMakeFiles/X11_backend.dir/link.txt').read_text())
for name in ('X11Display', 'X11Window', 'X11SubWindow'):
    obj = project / f'build/riot-{name}.o'
    subprocess.run(['clang', *flags['C_DEFINES'], *flags['C_INCLUDES'], *flags['C_FLAGS'], '-O3', '-march=native', '-mtune=generic', '-Wno-macro-redefined', '-c', str(project / f'build/darling-src/src/external/cocotron/AppKit/X11.backend/{name}.m'), '-o', str(obj)], check=True)
    link[link.index(f'CMakeFiles/X11_backend.dir/X11.backend/{name}.m.o')] = str(obj)
link[link.index('-o') + 1] = str(project / 'build/riot-X11')
subprocess.run(link, cwd=framework, check=True)
built_binary = project / 'build/riot-X11'
destinations = [
    Path.home() / '.darling/System/Library/Frameworks/AppKit.framework/Versions/C/Resources/Backends/X11.backend/Contents/MacOS/X11',
    Path.home() / '.darling/Users/fgeroldi/RuntimeFrameworks/AppKit.framework/Versions/C/Resources/Backends/X11.backend/Contents/MacOS/X11',
]
for dst in destinations:
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(built_binary, dst)
        print(f'Installed X11 backend to {dst}')
    except Exception as e:
        print(f'Could not install to {dst}: {e}')
print('Built isolated X11 backend')

# Exercise actual backend modifier transitions without compositor shortcuts.
probe = project / 'build/riot-modifier-check.o'
subprocess.run(['clang', *flags['C_DEFINES'], *flags['C_INCLUDES'], *flags['C_FLAGS'],
    '-O3', '-march=native', '-mtune=generic', '-Wno-macro-redefined', '-c', str(project / 'tools/riot-modifier-check.m'),
    '-o', str(probe)], check=True)
subprocess.run(['clang', '-target', 'x86_64-apple-macosx11.0', '-fuse-ld=lld',
    '-nostdlib', '-isysroot', sdk, str(probe),
    '-lSystem', '-framework', 'AppKit', '-framework', 'Foundation', '-lobjc',
    '-o', str(project / 'build/riot-modifier-check')], check=True)

# Verify that cached Chromium presentation cannot cover a native game drawable.
probe = project / 'build/riot-remote-frame-ownership-check.o'
subprocess.run(['clang', *flags['C_DEFINES'], *flags['C_INCLUDES'], *flags['C_FLAGS'],
    '-O3', '-march=native', '-mtune=generic', '-UNDEBUG', '-Wno-macro-redefined', '-c',
    str(project / 'tools/riot-remote-frame-ownership-check.m'), '-o', str(probe)], check=True)
subprocess.run(['clang', '-target', 'x86_64-apple-macosx11.0', '-fuse-ld=lld',
    '-nostdlib', '-isysroot', sdk, str(probe), '-lSystem', '-lobjc',
    '-framework', 'Foundation', '-framework', 'CoreFoundation',
    '-o', str(project / 'build/riot-remote-frame-ownership-check')], check=True)

probe = project / 'build/riot-fullscreen-geometry-check.o'
subprocess.run(['clang', *flags['C_DEFINES'], *flags['C_INCLUDES'], *flags['C_FLAGS'],
    '-O3', '-march=native', '-mtune=generic', '-UNDEBUG', '-Wno-macro-redefined', '-c',
    str(project / 'tools/riot-fullscreen-geometry-check.m'), '-o', str(probe)], check=True)
subprocess.run(['clang', '-target', 'x86_64-apple-macosx11.0', '-fuse-ld=lld',
    '-nostdlib', '-isysroot', sdk, str(probe), '-lSystem', '-lobjc', '-framework', 'Foundation',
    '-o', str(project / 'build/riot-fullscreen-geometry-check')], check=True)
