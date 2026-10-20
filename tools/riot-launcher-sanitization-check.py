#!/usr/bin/env python3
"""Verify launcher environment sanitization, leaked host fd closure, and macOS pure presentation."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

def find_repo_root():
    candidate = Path("@PROJECT_ROOT@")
    if (candidate / "scripts/run.sh").is_file():
        return candidate
    for p in Path(__file__).resolve().parents:
        if (p / "scripts/run.sh").is_file():
            return p
    return Path(__file__).resolve().parent.parent

ROOT = find_repo_root()


def test_ensure_darling_runtime_unit():
    """Verify ensure-darling-runtime.py's fd closing and environment sanitization functions."""
    import importlib.util
    path = ROOT / "tools/ensure-darling-runtime.py"
    spec = importlib.util.spec_from_file_location("ensure_darling_runtime", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # 1. Test is_linux_host_var
    assert mod.is_linux_host_var("WAYLAND_DISPLAY")
    assert mod.is_linux_host_var("XDG_RUNTIME_DIR")
    assert mod.is_linux_host_var("XDG_CURRENT_DESKTOP")
    assert mod.is_linux_host_var("XDG_SESSION_TYPE")
    assert mod.is_linux_host_var("MESA_NO_ERROR")
    assert mod.is_linux_host_var("MESA_DEBUG")
    assert mod.is_linux_host_var("mesa_glthread")
    assert mod.is_linux_host_var("DRI_PRIME")
    assert mod.is_linux_host_var("LIBGL_ALWAYS_SOFTWARE")
    assert mod.is_linux_host_var("ROCM_PATH")
    assert mod.is_linux_host_var("__GL_MaxFramesAllowed")
    assert mod.is_linux_host_var("__GL_THREADED_OPTIMIZATIONS")
    assert mod.is_linux_host_var("DBUS_SESSION_BUS_ADDRESS")
    assert mod.is_linux_host_var("DBUS_SYSTEM_BUS_ADDRESS")
    assert mod.is_linux_host_var("DESKTOP_SESSION")
    assert mod.is_linux_host_var("GDMSESSION")
    assert mod.is_linux_host_var("SESSION_MANAGER")
    assert mod.is_linux_host_var("SSH_AUTH_SOCK")
    assert mod.is_linux_host_var("SYSTEMD_EXEC_PID")
    assert mod.is_linux_host_var("INVOCATION_ID")
    assert mod.is_linux_host_var("JOURNAL_STREAM")
    assert mod.is_linux_host_var("MANAGERPID")
    assert mod.is_linux_host_var("GNOME_DESKTOP_SESSION_ID")
    assert mod.is_linux_host_var("KDE_FULL_SESSION")
    assert mod.is_linux_host_var("PULSE_SERVER")
    assert mod.is_linux_host_var("QT_QPA_PLATFORM")
    assert mod.is_linux_host_var("GTK_MODULES")
    assert mod.is_linux_host_var("GDK_BACKEND")
    assert mod.is_linux_host_var("GIO_LAUNCHED_DESKTOP_FILE")
    assert mod.is_linux_host_var("COLORTERM")
    assert mod.is_linux_host_var("VTE_VERSION")
    assert mod.is_linux_host_var("WINDOWID")
    assert mod.is_linux_host_var("GAMEMODERUN")
    assert mod.is_linux_host_var("LD_PRELOAD")
    assert mod.is_linux_host_var("LD_LIBRARY_PATH")
    assert mod.is_linux_host_var("ELECTRON_RUN_AS_NODE")
    assert mod.is_linux_host_var("DYLD_INSERT_LIBRARIES")
    assert mod.is_linux_host_var("XAUTHORITY")
    assert mod.is_linux_host_var("VK_ICD_FILENAMES")
    assert mod.is_linux_host_var("VK_LAYER_PATH")
    assert mod.is_linux_host_var("VULKAN_SDK")
    assert mod.is_linux_host_var("LIBVA_DRIVER_NAME")
    assert mod.is_linux_host_var("VDPAU_DRIVER")
    assert mod.is_linux_host_var("GBM_BACKEND")
    assert mod.is_linux_host_var("FLATPAK_ID")
    assert mod.is_linux_host_var("SNAP")
    assert mod.is_linux_host_var("SNAP_NAME")
    assert mod.is_linux_host_var("APPIMAGE")
    assert mod.is_linux_host_var("APPDIR")
    assert mod.is_linux_host_var("OWD")
    assert mod.is_linux_host_var("DEBUGINFOD_URLS")
    assert mod.is_linux_host_var("PAM_KWALLET5_LOGIN")
    assert mod.is_linux_host_var("SELINUX_ROLE_REQUESTED")
    assert mod.is_linux_host_var("NOTIFY_SOCKET")
    assert mod.is_linux_host_var("LISTEN_FDS")
    assert mod.is_linux_host_var("LISTEN_PID")
    assert mod.is_linux_host_var("LISTEN_FDNAMES")
    assert mod.is_linux_host_var("DESKTOP_STARTUP_ID")
    assert mod.is_linux_host_var("WINDOWPATH")
    assert mod.is_linux_host_var("XCURSOR_THEME")
    assert mod.is_linux_host_var("XCURSOR_SIZE")
    assert mod.is_linux_host_var("LC_ADDRESS")
    assert mod.is_linux_host_var("LC_IDENTIFICATION")
    assert mod.is_linux_host_var("LC_MEASUREMENT")
    assert mod.is_linux_host_var("LC_NAME")
    assert mod.is_linux_host_var("LC_PAPER")
    assert mod.is_linux_host_var("LC_TELEPHONE")
    assert mod.is_linux_host_var("USERNAME")
    assert mod.is_linux_host_var("MAIL")
    assert mod.is_linux_host_var("LS_COLORS")
    assert mod.is_linux_host_var("COLORFGBG")
    assert mod.is_linux_host_var("VSSCRIPT_PATH")
    assert mod.is_linux_host_var("CHROME_DEVTOOLS_MCP_JS")
    assert mod.is_linux_host_var("BASH_FUNC_foo%%")
    assert mod.is_linux_host_var("ANTIGRAVITY_AGENT")
    assert mod.is_linux_host_var("AGY_BROWSER_WS_URL")
    assert mod.is_linux_host_var("PAGER")
    assert mod.is_linux_host_var("GIT_PAGER")
    assert mod.is_linux_host_var("MANPAGER")
    assert mod.is_linux_host_var("MANROFFOPT")
    assert mod.is_linux_host_var("SHLVL")
    assert mod.is_linux_host_var("DISABLE_AUTO_UPDATE")

    # Variables that must NOT be stripped (legitimate macOS / Darling / app vars)
    assert not mod.is_linux_host_var("HOME")
    assert not mod.is_linux_host_var("USER")
    assert not mod.is_linux_host_var("LOGNAME")
    assert not mod.is_linux_host_var("PATH")
    assert not mod.is_linux_host_var("TMPDIR")
    assert not mod.is_linux_host_var("DISPLAY")
    assert not mod.is_linux_host_var("EGL_PLATFORM")
    assert not mod.is_linux_host_var("LANG")
    assert not mod.is_linux_host_var("LC_ALL")
    assert not mod.is_linux_host_var("XMODIFIERS")
    assert not mod.is_linux_host_var("DYLD_LIBRARY_PATH")
    assert not mod.is_linux_host_var("DYLD_FRAMEWORK_PATH")
    assert not mod.is_linux_host_var("DARLING_XSHM_LIBRARY")
    assert not mod.is_linux_host_var("DPREFIX")
    assert not mod.is_linux_host_var("RCLOL_GPU_DIRECT_PRESENT")
    assert not mod.is_linux_host_var("RCLOL_REFRESH_HZ")
    assert not mod.is_linux_host_var("DARLING_CA_PRESENT_AT_COMMIT")
    assert not mod.is_linux_host_var("__CF_USER_TEXT_ENCODING")
    assert not mod.is_linux_host_var("APPLE_SUPPRESS_X11_THEMING")

    # 2. Test sanitize_host_environment
    dirty_env = {
        "WAYLAND_DISPLAY": "wayland-0",
        "XDG_CURRENT_DESKTOP": "GNOME",
        "MESA_NO_ERROR": "1",
        "DRI_PRIME": "1",
        "ROCM_PATH": "/opt/rocm",
        "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
        "HOME": "/home/user",
        "USER": "user",
        "DISPLAY": ":0",
        "DYLD_LIBRARY_PATH": "/Users/user/RuntimeLibraries",
        "RCLOL_GPU_DIRECT_PRESENT": "1",
    }
    removed = mod.sanitize_host_environment(dirty_env)
    assert set(removed) == {
        "WAYLAND_DISPLAY", "XDG_CURRENT_DESKTOP", "MESA_NO_ERROR",
        "DRI_PRIME", "ROCM_PATH", "DBUS_SESSION_BUS_ADDRESS",
    }
    assert "HOME" in dirty_env
    assert "USER" in dirty_env
    assert "DISPLAY" in dirty_env
    assert "DYLD_LIBRARY_PATH" in dirty_env
    assert "RCLOL_GPU_DIRECT_PRESENT" in dirty_env

    # 3. Test CLI --check-env
    p_fail = subprocess.run(
        [sys.executable, str(path), "--check-env"],
        env={"WAYLAND_DISPLAY": "wayland-0", "PATH": os.environ.get("PATH", "")},
        capture_output=True, text=True,
    )
    assert p_fail.returncode == 1
    assert "LEAKED_HOST_ENV" in p_fail.stderr

    p_ok = subprocess.run(
        [sys.executable, str(path), "--check-env"],
        env={"PATH": "/usr/bin:/bin", "HOME": "/home/user", "USER": "user"},
        capture_output=True, text=True,
    )
    assert p_ok.returncode == 0
    assert "CLEAN_MACOS_ENVIRONMENT" in p_ok.stdout


def test_launcher_fd_and_env_sanitization():
    """Verify that run-riot-client.sh strips all Linux host environment variables and closes open fds."""
    (ROOT / "build").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sanitization-check-", dir=ROOT / "build") as directory:
        folder = Path(directory)
        launcher = folder / "launch.sh"
        guest_token = "@" + "GUEST_HOME@"
        launcher_src = (ROOT / "tools/run-riot-client.sh").read_text().replace(guest_token, "/Users/offline-check")
        launcher.write_text(launcher_src)
        launcher.chmod(0o755)

        bin_dir = folder / "bin"
        bin_dir.mkdir()
        env_dump_file = folder / "darling_env.json"
        fds_dump_file = folder / "darling_fds.json"

        # Stub darling executable that logs its environment and open file descriptors
        stub_darling = f'''#!{sys.executable}
import json, os, sys
with open({str(env_dump_file)!r}, "w") as f:
    json.dump(dict(os.environ), f)

# Inspect open file descriptors in /proc/self/fd excluding inspection dirfd
fds = []
if os.path.isdir('/proc/self/fd'):
    dir_fd = os.open('/proc/self/fd', os.O_RDONLY | os.O_DIRECTORY)
    fds = [int(n) for n in os.listdir(dir_fd) if n.isdigit() and int(n) != dir_fd]
    os.close(dir_fd)
with open({str(fds_dump_file)!r}, "w") as f:
    json.dump(sorted(fds), f)
'''
        (bin_dir / "darling").write_text(stub_darling)
        (bin_dir / "darling").chmod(0o755)

        # Stub python3 so maintenance tools don't fail
        stub_python = f'''#!{sys.executable}
import sys
sys.exit(0)
'''
        (bin_dir / "python3").write_text(stub_python)
        (bin_dir / "python3").chmod(0o755)

        prefix = folder / "prefix"
        (prefix / "Applications/Riot Client.app").mkdir(parents=True)

        # Create heavily polluted Linux host environment
        test_env = dict(os.environ)
        test_env["PATH"] = str(bin_dir) + os.pathsep + test_env.get("PATH", "")
        test_env["DPREFIX"] = str(prefix)
        test_env["RIOT_LAUNCHER_HOST"] = str(folder / "RiotClientServices")
        test_env.update({
            "WAYLAND_DISPLAY": "wayland-0",
            "XDG_CURRENT_DESKTOP": "GNOME",
            "XDG_SESSION_TYPE": "wayland",
            "XDG_RUNTIME_DIR": "/run/user/1000",
            "XDG_DATA_DIRS": "/usr/local/share:/usr/share",
            "XDG_CONFIG_DIRS": "/etc/xdg",
            "XDG_SESSION_ID": "2",
            "MESA_NO_ERROR": "1",
            "MESA_DEBUG": "1",
            "MESA_LOADER_DRIVER_OVERRIDE": "zink",
            "mesa_glthread": "true",
            "DRI_PRIME": "1",
            "LIBGL_ALWAYS_SOFTWARE": "1",
            "LIBGL_DRI3_DISABLE": "1",
            "ROCM_PATH": "/opt/rocm",
            "__GL_MaxFramesAllowed": "1",
            "__GL_THREADED_OPTIMIZATIONS": "1",
            "__GL_YIELD": "NOTHING",
            "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
            "DBUS_SYSTEM_BUS_ADDRESS": "unix:path=/var/run/dbus/system_bus_socket",
            "DESKTOP_SESSION": "ubuntu",
            "GDMSESSION": "gnome",
            "GDM_LANG": "en_US.UTF-8",
            "SESSION_MANAGER": "local/alienware:@/tmp/.ICE-unix/1234",
            "SSH_AUTH_SOCK": "/run/user/1000/keyring/ssh",
            "SSH_AGENT_PID": "4321",
            "SYSTEMD_EXEC_PID": "9876",
            "INVOCATION_ID": "abcd1234ef",
            "JOURNAL_STREAM": "8:9999",
            "MANAGERPID": "1000",
            "MANAGERPIDFDID": "123",
            "GNOME_DESKTOP_SESSION_ID": "this-is-deprecated",
            "KDE_FULL_SESSION": "true",
            "PULSE_SERVER": "unix:/tmp/pulse-socket",
            "PIPEWIRE_LATENCY": "128/48000",
            "ALSA_CONFIG_PATH": "/usr/share/alsa/alsa.conf",
            "QT_QPA_PLATFORM": "wayland",
            "QT_IM_MODULE": "ibus",
            "GTK_MODULES": "canberra-gtk-module",
            "GDK_BACKEND": "wayland",
            "GIO_LAUNCHED_DESKTOP_FILE": "/usr/share/applications/app.desktop",
            "GSETTINGS_SCHEMA_DIR": "/usr/share/glib-2.0/schemas",
            "GJS_DEBUG_OUTPUT": "stderr",
            "GLIBC_TUNABLES": "glibc.pthread.rseq=0",
            "COLORTERM": "truecolor",
            "VTE_VERSION": "7600",
            "WINDOWID": "12345678",
            "CHROME_DESKTOP": "chrome.desktop",
            "FC_FONTATIONS": "1",
            "MEMORY_PRESSURE_WATCH": "/sys/fs/cgroup",
            "NO_AT_BRIDGE": "1",
            "MOTD_SHOWN": "pam",
            "VIRTUAL_ENV": "/home/alienware/.venv",
            "ZSH_TMUX_AUTOSTARTED": "true",
            "GAMEMODERUN": "1",
            "LD_PRELOAD": "/usr/lib/libgamemodeauto.so.0",
            "LD_LIBRARY_PATH": "/usr/lib/x86_64-linux-gnu",
            "ELECTRON_RUN_AS_NODE": "1",
            "DYLD_INSERT_LIBRARIES": "/tmp/host_injected.so",
            "XAUTHORITY": "/run/user/1000/.mutter-Xwaylandauth.AMCRX3",
            "VK_ICD_FILENAMES": "/usr/share/vulkan/icd.d/intel_icd.x86_64.json",
            "VK_LAYER_PATH": "/usr/share/vulkan/explicit_layer.d",
            "LIBVA_DRIVER_NAME": "iHD",
            "VDPAU_DRIVER": "va_gl",
            "GBM_BACKEND": "dri",
            "FLATPAK_ID": "com.riot.test",
            "SNAP": "/snap/test/current",
            "SNAP_NAME": "test",
            "APPIMAGE": "/home/user/app.AppImage",
            "APPDIR": "/tmp/.mount_app123",
            "OWD": "/home/user",
            "DEBUGINFOD_URLS": "https://debuginfod.ubuntu.com",
            "PAM_KWALLET5_LOGIN": "/run/user/1000/kwallet5.socket",
            "SELINUX_ROLE_REQUESTED": "unconfined_r",
            "NOTIFY_SOCKET": "/run/user/1000/systemd/notify",
            "LISTEN_FDS": "1",
            "LISTEN_PID": "1234",
            "LISTEN_FDNAMES": "socket",
            "DESKTOP_STARTUP_ID": "gnome-shell-123",
            "WINDOWPATH": "2",
            "XCURSOR_THEME": "Adwaita",
            "XCURSOR_SIZE": "24",
            "LC_ADDRESS": "en_US.UTF-8",
            "LC_IDENTIFICATION": "en_US.UTF-8",
            "LC_MEASUREMENT": "en_US.UTF-8",
            "LC_NAME": "en_US.UTF-8",
            "LC_PAPER": "en_US.UTF-8",
            "LC_TELEPHONE": "en_US.UTF-8",
            "USERNAME": "alienware",
            "MAIL": "/var/spool/mail/alienware",
            "LS_COLORS": "rs=0:di=01;34",
            "COLORFGBG": "15;0",
            "VSSCRIPT_PATH": "/usr/lib/libvsscript.so",
            "CHROME_DEVTOOLS_MCP_JS": "/usr/lib/chrome-devtools-mcp.js",
            "BASH_FUNC_foo%%": "() { echo hi; }",
            "SHELL": "/bin/fish",
            # Legitimate options that MUST survive
            "RCLOL_GPU_DIRECT_PRESENT": "1",
            "RCLOL_GPU_DIRECT_ASYNC": "1",
            "DARLING_CA_PRESENT_AT_COMMIT": "1",
            "RCLOL_FORWARD_MOUSE_MOVED": "1",
            "RCLOL_MOUSE_CONFINEMENT": "1",
            "RCLOL_REFRESH_HZ": "144",
        })

        # Leak several open file descriptors (pipes and files) into launcher
        pipe_r1, pipe_w1 = os.pipe()
        pipe_r2, pipe_w2 = os.pipe()
        leaked_fds = [pipe_r1, pipe_w1, pipe_r2, pipe_w2]

        proc = subprocess.run(
            ["sh", str(launcher)],
            env=test_env,
            pass_fds=leaked_fds,
            capture_output=True,
            text=True,
        )
        for fd in leaked_fds:
            try:
                os.close(fd)
            except OSError:
                pass

        assert proc.returncode == 0, f"Launcher failed: stderr={proc.stderr}"
        assert env_dump_file.is_file(), "Stub darling was not executed"
        guest_env = json.loads(env_dump_file.read_text())

        # 1. Verify ALL Linux host variables are stripped
        forbidden_keys = [
            "WAYLAND_DISPLAY", "XDG_CURRENT_DESKTOP", "XDG_SESSION_TYPE", "XDG_RUNTIME_DIR",
            "XDG_DATA_DIRS", "XDG_CONFIG_DIRS", "XDG_SESSION_ID", "MESA_NO_ERROR", "MESA_DEBUG",
            "MESA_LOADER_DRIVER_OVERRIDE", "mesa_glthread", "DRI_PRIME", "LIBGL_ALWAYS_SOFTWARE",
            "LIBGL_DRI3_DISABLE", "ROCM_PATH", "__GL_MaxFramesAllowed", "__GL_THREADED_OPTIMIZATIONS",
            "__GL_YIELD", "DBUS_SESSION_BUS_ADDRESS", "DBUS_SYSTEM_BUS_ADDRESS", "DESKTOP_SESSION",
            "GDMSESSION", "GDM_LANG", "SESSION_MANAGER", "SSH_AUTH_SOCK", "SSH_AGENT_PID",
            "SYSTEMD_EXEC_PID", "INVOCATION_ID", "JOURNAL_STREAM", "MANAGERPID", "MANAGERPIDFDID",
            "GNOME_DESKTOP_SESSION_ID", "KDE_FULL_SESSION", "PULSE_SERVER", "PIPEWIRE_LATENCY",
            "ALSA_CONFIG_PATH", "QT_QPA_PLATFORM", "QT_IM_MODULE", "GTK_MODULES", "GDK_BACKEND",
            "GIO_LAUNCHED_DESKTOP_FILE", "GSETTINGS_SCHEMA_DIR", "GJS_DEBUG_OUTPUT", "GLIBC_TUNABLES",
            "COLORTERM", "VTE_VERSION", "WINDOWID", "CHROME_DESKTOP", "FC_FONTATIONS",
            "MEMORY_PRESSURE_WATCH", "NO_AT_BRIDGE", "MOTD_SHOWN", "VIRTUAL_ENV", "ZSH_TMUX_AUTOSTARTED",
            "GAMEMODERUN", "LD_PRELOAD", "LD_LIBRARY_PATH", "ELECTRON_RUN_AS_NODE",
            "DYLD_INSERT_LIBRARIES", "XAUTHORITY",
            "VK_ICD_FILENAMES", "VK_LAYER_PATH", "LIBVA_DRIVER_NAME", "VDPAU_DRIVER", "GBM_BACKEND",
            "FLATPAK_ID", "SNAP", "SNAP_NAME", "APPIMAGE", "APPDIR", "OWD", "DEBUGINFOD_URLS",
            "PAM_KWALLET5_LOGIN", "SELINUX_ROLE_REQUESTED", "NOTIFY_SOCKET", "LISTEN_FDS",
            "LISTEN_PID", "LISTEN_FDNAMES", "DESKTOP_STARTUP_ID", "WINDOWPATH", "XCURSOR_THEME",
            "XCURSOR_SIZE", "LC_ADDRESS", "LC_IDENTIFICATION", "LC_MEASUREMENT", "LC_NAME",
            "LC_PAPER", "LC_TELEPHONE", "USERNAME", "MAIL", "LS_COLORS", "COLORFGBG",
            "VSSCRIPT_PATH", "CHROME_DEVTOOLS_MCP_JS", "BASH_FUNC_foo%%",
            "PAGER", "GIT_PAGER", "MANPAGER", "MANROFFOPT", "DISABLE_AUTO_UPDATE",
        ]
        for key in forbidden_keys:
            assert key not in guest_env, f"Forbidden Linux host variable leaked to guest: {key}={guest_env.get(key)}"

        # 2. Verify pure macOS presentation variables are present
        assert guest_env.get("LANG") == "en_US.UTF-8"
        assert guest_env.get("LC_ALL") == "en_US.UTF-8"
        assert guest_env.get("SHELL") == "/bin/zsh"
        assert guest_env.get("XMODIFIERS") == "@im=none"
        assert guest_env.get("EGL_PLATFORM") == "x11"
        assert guest_env.get("__CF_USER_TEXT_ENCODING") == "0x1F5:0x0:0x0"
        assert guest_env.get("APPLE_SUPPRESS_X11_THEMING") == "1"
        assert guest_env.get("DYLD_LIBRARY_PATH") == "/Users/offline-check/RuntimeLibraries"
        assert guest_env.get("DYLD_FRAMEWORK_PATH") == "/Users/offline-check/RuntimeFrameworks"
        assert guest_env.get("DARLING_XSHM_LIBRARY") == "/Users/offline-check/libDarlingXShm.dylib"

        # 3. Verify Darling / League runtime switches survived
        assert guest_env.get("RCLOL_GPU_DIRECT_PRESENT") == "1"
        assert guest_env.get("RCLOL_GPU_DIRECT_ASYNC") == "1"
        assert guest_env.get("DARLING_CA_PRESENT_AT_COMMIT") == "1"
        assert guest_env.get("RCLOL_FORWARD_MOUSE_MOVED") == "1"
        assert guest_env.get("RCLOL_MOUSE_CONFINEMENT") == "1"
        assert guest_env.get("RCLOL_REFRESH_HZ") == "144"

        # 4. Verify leaked file descriptors were closed
        assert fds_dump_file.is_file()
        open_fds = json.loads(fds_dump_file.read_text())
        for leaked in leaked_fds:
            assert leaked not in open_fds, f"Leaked host file descriptor {leaked} remained open in guest process: {open_fds}"


def test_close_inherited_fds_fallback():
    """Verify that close_inherited_fds() closes fds when /proc/self/fd is unavailable."""
    code = """
import importlib.util, os, sys
from unittest.mock import patch
from pathlib import Path
path = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("ensure_darling_runtime", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

r, w = os.pipe()
assert r > 2 and w > 2
with patch("os.path.isdir", return_value=False):
    mod.close_inherited_fds()

for fd in (r, w):
    try:
        os.close(fd)
        sys.exit(1)
    except OSError:
        pass
sys.exit(0)
"""
    p = subprocess.run([sys.executable, "-c", code, str(ROOT / "tools/ensure-darling-runtime.py")])
    assert p.returncode == 0, "Fallback fd closing failed"


def test_scripts_run_sh_fd_and_env():
    """Verify that scripts/run.sh closes leaked fds and unsets conflicting host variables."""
    run_sh = ROOT / "scripts/run.sh"
    content = run_sh.read_text()
    assert "for fd_path in /proc/self/fd/*; do" in content
    assert "eval \"exec ${fd}>&-\"" in content
    assert "_fd=3" in content and "while [ \"$_fd\" -le 256 ]; do" in content
    assert "unset WAYLAND_DISPLAY MESA_NO_ERROR DRI_PRIME ROCM_PATH mesa_glthread" in content
    assert "_linux_vars=$(env | awk" in content
    assert "unset -v \"$_var\"" in content


def main():
    test_ensure_darling_runtime_unit()
    test_close_inherited_fds_fallback()
    test_launcher_fd_and_env_sanitization()
    test_scripts_run_sh_fd_and_env()
    print("LAUNCHER_SANITIZATION_CHECK pass=1 host_env_stripped=PASS pure_macos_env=PASS leaked_fds_closed=PASS")


if __name__ == "__main__":
    main()

