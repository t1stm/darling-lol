#!/usr/bin/env python3
"""Clear a dead Darling server's stale PID marker, and stale shared buffers once no server runs."""
import json
import os
from pathlib import Path
import sys
import time

LINUX_ENV_PREFIXES = (
    'XDG_', 'MESA_', 'DRI_', 'ROCM_', 'LIBGL_', '__GL_', 'DBUS_',
    'SSH_', 'SYSTEMD_', 'GNOME_', 'KDE_', 'PULSE_', 'PIPEWIRE_',
    'ALSA_', 'QT_', 'GTK_', 'GDK_', 'GIO_', 'GSETTINGS_', 'GJS_',
    'GLIBC_', 'MEMORY_PRESSURE_', 'VIRTUAL_ENV', 'ZSH_TMUX_', 'GAMEMODE',
    'VK_', 'VULKAN_', 'LIBVA_', 'VDPAU_', 'GBM_', 'FLATPAK_',
    'SNAP_', 'DEBUGINFOD_', 'PAM_', 'SELINUX_', 'BASH_FUNC_',
    'ANTIGRAVITY_', 'AGY_',
)

LINUX_ENV_EXACT = {
    'WAYLAND_DISPLAY', 'DESKTOP_SESSION', 'DESKTOP_STARTUP_ID', 'GDMSESSION', 'GDM_LANG',
    'GDM_SETUP_DISPLAY', 'GNOME_SETUP_DISPLAY', 'SESSION_MANAGER',
    'INVOCATION_ID', 'JOURNAL_STREAM', 'MANAGERPID', 'MANAGERPIDFDID',
    'NOTIFY_SOCKET', 'LISTEN_FDS', 'LISTEN_PID', 'LISTEN_FDNAMES',
    'COLORTERM', 'VTE_VERSION', 'WINDOWID', 'WINDOWPATH',
    'XCURSOR_THEME', 'XCURSOR_SIZE', 'CHROME_DESKTOP',
    'FC_FONTATIONS', 'NO_AT_BRIDGE', 'MOTD_SHOWN', 'LD_PRELOAD',
    'LD_LIBRARY_PATH', 'ELECTRON_RUN_AS_NODE', 'DYLD_INSERT_LIBRARIES',
    'XAUTHORITY', 'mesa_glthread', 'SNAP', 'APPIMAGE', 'APPDIR', 'OWD',
    'USERNAME', 'MAIL', 'LS_COLORS', 'COLORFGBG',
    'VSSCRIPT_PATH', 'CHROME_DEVTOOLS_MCP_JS',
    'LC_ADDRESS', 'LC_IDENTIFICATION', 'LC_MEASUREMENT', 'LC_NAME', 'LC_PAPER', 'LC_TELEPHONE',
    'PAGER', 'GIT_PAGER', 'MANPAGER', 'MANROFFOPT', 'SHLVL', 'DISABLE_AUTO_UPDATE',
}

def is_linux_host_var(key: str) -> bool:
    """Return True if an environment variable is Linux/host specific and should be stripped."""
    if key in LINUX_ENV_EXACT:
        return True
    return any(key.startswith(p) for p in LINUX_ENV_PREFIXES)

def close_inherited_fds():
    """Close leaked host file descriptors > 2 so children and daemons do not inherit them."""
    closed_via_proc = False
    try:
        fd_dir = '/proc/self/fd'
        if os.path.isdir(fd_dir):
            fds = [int(name) for name in os.listdir(fd_dir) if name.isdigit()]
            for fd in fds:
                if fd > 2:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
            closed_via_proc = True
    except OSError:
        closed_via_proc = False

    if not closed_via_proc:
        try:
            import resource
            max_fd = min(resource.getrlimit(resource.RLIMIT_NOFILE)[0], 4096)
        except Exception:
            max_fd = 1024
        try:
            os.closerange(3, max_fd)
        except Exception:
            for fd in range(3, max_fd):
                try:
                    os.close(fd)
                except OSError:
                    pass

def sanitize_host_environment(env=os.environ):
    """Strip Linux-specific host variables from environment dict in-place and return stripped keys."""
    removed = []
    for key in list(env.keys()):
        if is_linux_host_var(key):
            removed.append(key)
            del env[key]
    return removed
def recover_marker(prefix):
    marker = prefix / '.init.pid'
    try:
        pid = int(marker.read_text().strip())
    except (OSError, ValueError):
        pid = 0
    if pid > 0:
        status = Path('/proc') / str(pid) / 'status'
        try:
            state = next(line.split()[1] for line in status.read_text().splitlines() if line.startswith('State:'))
            dead = state == 'Z'
        except FileNotFoundError:
            dead = True
        except (OSError, StopIteration):
            dead = False
        if dead:
            os.replace(marker, prefix / f'.init.pid.stale-{pid}-{time.time_ns()}')
            print(f'Recovered stale Darling server marker for PID {pid}', flush=True)

def any_server_running(proc_root=Path('/proc')):
    """True if any darlingserver runs, for any prefix: /dev/shm buffers are not per prefix."""
    for proc in proc_root.iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if (proc / 'comm').read_text().strip() == 'darlingserver':
                status = proc / 'status'
                if status.is_file():
                    try:
                        state = next(line.split()[1] for line in status.read_text().splitlines() if line.startswith('State:'))
                        if state == 'Z':
                            continue
                    except (OSError, StopIteration):
                        pass
                return True
        except PermissionError:
            # A hidden process might be a server; shared buffers are global, so fail closed.
            return True
        except OSError:
            pass
    return False

def _matching_pids(kind, proc_root):
    """Find same-user candidates by guest executable; this does not establish ownership."""
    uid = os.getuid()
    for proc in proc_root.iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if proc.stat().st_uid != uid:
                continue
            argv = (proc / 'cmdline').read_bytes()
            if kind == 'launchd':
                matches = argv.rstrip(b'\0') == b'/sbin/launchd'
            else:
                executable = argv.split(b'\0', 1)[0].decode(errors='replace')
                matches = (proc / 'comm').read_text().startswith('chrome_crashpad') and any(
                    bundle in executable for bundle in (
                        '/Riot Client.app/', '/League of Legends.app/',
                        '/League of Legends (TM) Client.app/'))
            if matches:
                yield proc.name
        except (OSError, ValueError):
            continue


def stop_orphaned_launchd(proc_root=Path('/proc')):
    """Warn about launchd candidates without assuming prefix ownership or signalling them."""
    pids = list(_matching_pids('launchd', proc_root))
    if pids:
        print(f'Preserving launchd candidate PIDs {", ".join(pids)}: prefix ownership '
              'cannot be proved. If setup is blocked, shut down the original Darling '
              'session or inspect the leftover processes manually.', file=sys.stderr, flush=True)


def stop_riot_crashpad(proc_root=Path('/proc')):
    """Warn about Riot crashpad candidates without assuming prefix ownership or signalling them."""
    pids = list(_matching_pids('crashpad', proc_root))
    if pids:
        print(f'Preserving Riot crashpad candidate PIDs {", ".join(pids)}: prefix ownership '
              'cannot be proved. Use the original session to shut down leftover helpers.',
              file=sys.stderr, flush=True)

def remove_owned(paths):
    uid = os.getuid()
    for path in paths:
        try:
            if path.is_file() and path.stat().st_uid == uid:
                path.unlink()
        except OSError:
            pass

def ensure_prefix_smbios(prefix):
    if not (prefix / 'private/etc').is_dir():
        return
    helper = Path(__file__).resolve().with_name('gen-darling-smbios.py')
    if not helper.is_file():
        return
    import importlib.util
    spec = importlib.util.spec_from_file_location('gen_darling_smbios', helper)
    if spec and spec.loader:
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        cfg, created = mod.ensure_smbios(prefix)
        if created:
            print(f"Provisioned Darling SMBIOS ({cfg['SMBIOS_MODEL']} {cfg['SMBIOS_SERIAL_NUMBER']})", flush=True)

def resolve_guest_user():
    config_file = Path(__file__).resolve().parent.parent / 'build/config.json'
    if config_file.is_file():
        try:
            cfg = json.loads(config_file.read_text())
            if cfg.get('guest_user'):
                return cfg['guest_user']
        except Exception:
            pass
    return os.environ.get('GUEST_USER') or os.environ.get('USER') or Path.home().name

def ensure_guest_xauthority(prefix):
    if not (prefix / 'private/etc').is_dir():
        return
    auth_src = os.environ.get('XAUTHORITY')
    candidates = []
    if auth_src:
        candidates.append(Path(auth_src))
    candidates.append(Path.home() / '.Xauthority')
    run_user = Path(f'/run/user/{os.getuid()}')
    if run_user.is_dir():
        try:
            candidates.extend(sorted(run_user.glob('.mutter-Xwaylandauth.*'), key=lambda p: p.stat().st_mtime, reverse=True))
            candidates.extend(sorted(run_user.glob('xauth_*'), key=lambda p: p.stat().st_mtime, reverse=True))
        except OSError:
            pass

    guest_user = resolve_guest_user()
    target = prefix / 'Users' / guest_user / '.Xauthority'
    for src in candidates:
        if src.is_file() and os.access(src, os.R_OK):
            try:
                import shutil
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
                target.chmod(0o600)
                break
            except OSError:
                pass

def main():
    if '--check-env' in sys.argv:
        leaked = [k for k in os.environ if is_linux_host_var(k)]
        if leaked:
            print(f"LEAKED_HOST_ENV: {', '.join(sorted(leaked))}", file=sys.stderr)
            sys.exit(1)
        print("CLEAN_MACOS_ENVIRONMENT")
        return
    prefix = Path(os.environ.get('DPREFIX', str(Path.home() / '.darling')))
    ensure_guest_xauthority(prefix)
    removed = sanitize_host_environment()
    if '--print-unsets' in sys.argv:
        for k in sorted(removed):
            print(k)
        return
    if '--sanitize' in sys.argv or '--strip-env' in sys.argv:
        print(f"STRIPPED_HOST_ENV: {', '.join(sorted(removed))}")
        return
    recover_marker(prefix)
    ensure_prefix_smbios(prefix)
    # Frame and present buffers left by a killed session confuse the next one's publishers.
    if not any_server_running():
        stop_orphaned_launchd()
        stop_riot_crashpad()
        remove_owned((prefix / 'private/tmp').glob('.com.riotgames.*'))
        remove_owned(Path('/dev/shm').glob('darling-*'))


if __name__ == '__main__':
    close_inherited_fds()
    main()

