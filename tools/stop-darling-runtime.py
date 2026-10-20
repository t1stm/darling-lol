#!/usr/bin/env python3
"""Wait for Darling's old server to exit before rebuilding its namespace."""
import os
import signal
from pathlib import Path
import subprocess
import sys
import time
prefix = Path(os.environ.get('DPREFIX', str(Path.home() / '.darling')))
try:
    old_pid = int((prefix / '.init.pid').read_text().strip())
except (OSError, ValueError):
    old_pid = 0

def live(pid):
    if pid <= 0:
        return False
    try:
        state = next(line.split()[1] for line in (Path('/proc') / str(pid) / 'status').read_text().splitlines() if line.startswith('State:'))
        return state != 'Z'
    except (FileNotFoundError, ProcessLookupError, StopIteration):
        # A process can exit after status is opened but before it is read.
        return False

if old_pid == 0:
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if (entry / 'comm').read_text().strip() == 'darlingserver' and live(int(entry.name)):
                if entry.stat().st_uid == os.getuid():
                    old_pid = int(entry.name)
                    break
        except (OSError, ValueError):
            pass

def process_identity(pid):
    try:
        return (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()[19]
    except (OSError, IndexError):
        return None

def riot_descendants(server_pid):
    # The host server and its guest init have different PID namespaces. Follow
    # ancestry while the server is alive, rather than comparing namespace IDs.
    pending = [server_pid]
    seen = set()
    result = {}
    while pending:
        pid = pending.pop()
        if pid in seen or pid <= 0:
            continue
        seen.add(pid)
        try:
            for children in (Path('/proc') / str(pid) / 'task').glob('*/children'):
                pending.extend(int(child) for child in children.read_text().split())
            mappings = ''
            try:
                mappings = (Path('/proc') / str(pid) / 'maps').read_text()
            except OSError:
                pass
            cmdline = ''
            try:
                cmdline = (Path('/proc') / str(pid) / 'cmdline').read_bytes().decode('utf-8', errors='replace')
            except OSError:
                pass
            combined = mappings + '\n' + cmdline
            if ('Electron Framework.framework/Versions/A/Electron Framework' in combined or
                    '/Applications/Riot Client.app/' in combined or
                    '/Users/Shared/Riot Games/' in combined or
                    '/League of Legends.app/' in combined or
                    'RiotClient' in combined):
                result[pid] = process_identity(pid)
        except (OSError, ValueError):
            continue
    return result

def orphaned_riot():
    # A dead server marker cannot enumerate its former descendants. Recover
    # only same-user Riot mappings in this prefix with no live server ancestor.
    result = {}
    riot_markers = (
        str(prefix / 'Applications/Riot Client.app'),
        str(prefix / 'Applications/League of Legends.app'),
        str(prefix / 'Users/Shared/Riot Games'),
        str(prefix / 'Users/Shared/League of Legends'),
        'Electron Framework.framework/Versions/A/Electron Framework',
    )
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            pid = int(entry.name)
            if pid == os.getpid():
                continue
            mappings = ''
            try:
                mappings = (entry / 'maps').read_text()
            except OSError:
                pass
            cmdline = ''
            try:
                cmdline = (entry / 'cmdline').read_bytes().decode('utf-8', errors='replace')
            except OSError:
                pass
            combined = mappings + '\n' + cmdline
            matched = any(m in combined for m in riot_markers)
            if not matched and ('RiotClient' in cmdline or 'LeagueofLegends' in cmdline) and str(prefix) in cmdline:
                matched = True
            if not matched:
                continue

            ancestor = pid
            seen = set()
            has_server = False
            while ancestor > 1 and ancestor not in seen:
                seen.add(ancestor)
                proc = Path('/proc') / str(ancestor)
                try:
                    if proc.joinpath('comm').read_text().strip() == 'darlingserver' and live(ancestor):
                        has_server = True
                        break
                    fields = proc.joinpath('stat').read_text().rsplit(')', 1)[1].split()
                    ancestor = int(fields[1])
                except (OSError, ValueError, IndexError):
                    break
            if not has_server:
                result[pid] = process_identity(pid)
        except (OSError, ValueError, IndexError):
            continue
    return result

owned_riot = riot_descendants(old_pid)
owned_riot.update(orphaned_riot())
subprocess.run(['darling', 'shutdown'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
deadline = time.monotonic() + 5
while live(old_pid) and time.monotonic() < deadline:
    time.sleep(.1)
if live(old_pid):
    raise SystemExit(f'Darling server {old_pid} has not exited; runtime remains untouched')
# Shutdown can leave Electron helpers or League's startup window reparented
# and consuming CPU/GPU time.
def send_signal(pid, sig):
    try:
        os.kill(pid, sig)
    except PermissionError:
        try:
            subprocess.run(['sudo', '-n', 'kill', f'-{int(sig)}', str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        except OSError:
            pass
    except ProcessLookupError:
        pass

# Stop the observed descendants and verified serverless Riot processes in this
# prefix, guarding against PID reuse. Leave other live Darling sessions alone.
for pid, identity in owned_riot.items():
    if identity is not None and process_identity(pid) == identity and live(pid):
        send_signal(pid, signal.SIGTERM)
deadline = time.monotonic() + 3
while any(process_identity(pid) == identity and live(pid)
          for pid, identity in owned_riot.items()) and time.monotonic() < deadline:
    time.sleep(.1)
remaining = {pid: identity for pid, identity in owned_riot.items()
             if process_identity(pid) == identity and live(pid)}
# These helpers have no live server and ignored graceful termination. They
# cannot complete guest RPCs after shutdown. Kill only the previously observed
# Riot descendants, with the same PID/start-time guard used above.
for pid, identity in remaining.items():
    if process_identity(pid) == identity and live(pid):
        send_signal(pid, signal.SIGKILL)
deadline = time.monotonic() + 5
while any(process_identity(pid) == identity and live(pid)
          for pid, identity in remaining.items()) and time.monotonic() < deadline:
    time.sleep(.1)
if any(process_identity(pid) == identity and live(pid) for pid, identity in remaining.items()):
    raise SystemExit('Old Riot helpers remain alive; runtime remains untouched')
if '--shutdown-only' not in sys.argv:
    subprocess.run([sys.executable, str(Path(__file__).with_name('ensure-darling-runtime.py'))], check=True)
