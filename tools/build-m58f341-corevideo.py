#!/usr/bin/env python3
"""Build the corrected display clock as an isolated per-user candidate."""
import json, shlex, subprocess
from pathlib import Path
project=Path(__file__).resolve().parent.parent
config_path = project / 'build/config.json'
cfg = json.loads(config_path.read_text()) if config_path.exists() else {}
sdk = cfg.get('sdk', '/usr/local/libexec/darling')
prefix = Path(cfg.get('prefix', Path.home() / '.darling'))
guest_home = Path(cfg.get('guest_home', '/Users/fgeroldi'))
guest_home_host = prefix / guest_home.relative_to('/')
framework=project/'build/darling-src/build/src/frameworks/CoreVideo'
flags={}
for line in (framework/'CMakeFiles/CoreVideo.dir/flags.make').read_text().splitlines():
 if line.startswith(('C_','CXX_')) and ' = ' in line:
  k,v=line.split(' = ',1);flags[k]=shlex.split(v)
obj=project/'build/m341-CVDisplayLink.o'
subprocess.run(['clang++',*flags['CXX_DEFINES'],*flags['CXX_INCLUDES'],*flags['CXX_FLAGS'],'-O2','-Wno-macro-redefined','-c',str(project/'build/darling-src/src/frameworks/CoreVideo/src/CVDisplayLink.mm'),'-o',str(obj)],check=True)
link=shlex.split((framework/'CMakeFiles/CoreVideo.dir/link.txt').read_text())
link[link.index('CMakeFiles/CoreVideo.dir/src/CVDisplayLink.mm.o')]=str(obj)
link[link.index('-o')+1]=str(project/'build/m341-CoreVideo')
subprocess.run(link,cwd=framework,check=True)
built_binary = project / 'build/m341-CoreVideo'
import shutil
try:
    shutil.copy2(built_binary, framework / 'CoreVideo')
except Exception:
    pass
destinations = [
    prefix / 'System/Library/Frameworks/CoreVideo.framework/Versions/A/CoreVideo',
    guest_home_host / 'RuntimeFrameworks/CoreVideo.framework/Versions/A/CoreVideo',
]
for dst in destinations:
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(built_binary, dst)
        print(f'Installed CoreVideo to {dst}')
    except Exception as e:
        print(f'Could not install to {dst}: {e}')
probe=project/'build/m341-clock-check.o'
subprocess.run(['clang',*flags['C_DEFINES'],*flags['C_INCLUDES'],*flags['C_FLAGS'],'-Wno-macro-redefined','-c',str(project/'tools/m58f341-display-clock-check.c'),'-o',str(probe)],check=True)
try:
    subprocess.run(['clang','-target','x86_64-apple-macosx11.0','-fuse-ld=lld','-nostdlib','-isysroot',sdk,str(probe),'-lSystem','-framework','CoreVideo','-o',str(project/'build/m341-clock-check')],check=True)
except Exception as e:
    print(f'Could not build clock probe: {e}')
print('Built isolated CoreVideo display clock and cadence probe')
