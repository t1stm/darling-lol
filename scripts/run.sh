#!/bin/sh
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo"

# Close leaked inherited host file descriptors > 2 early.
if [ -d /proc/self/fd ]; then
  for fd_path in /proc/self/fd/*; do
    fd="${fd_path##*/}"
    case "$fd" in
      0|1|2|'*') ;;
      *)
        eval "exec ${fd}>&-" 2>/dev/null || true
        ;;
    esac
  done
else
  _fd=3
  while [ "$_fd" -le 256 ]; do
    eval "exec ${_fd}>&-" 2>/dev/null || true
    _fd=$((_fd + 1))
  done
fi

# Strip early host display/driver variables before configure or gamemode.
unset WAYLAND_DISPLAY MESA_NO_ERROR DRI_PRIME ROCM_PATH mesa_glthread

# Strip all Linux-specific host variables so configure and wrappers run in pure environment:
_linux_vars=$(env | awk -F= '
  /^[A-Za-z_][A-Za-z0-9_]*=/ {
    k = $1
    if (k ~ /^(XDG_|MESA_|DRI_|ROCM_|LIBGL_|__GL_|DBUS_|SSH_|SYSTEMD_|GNOME_|KDE_|PULSE_|PIPEWIRE_|ALSA_|QT_|GTK_|GDK_|GIO_|GSETTINGS_|GJS_|GLIBC_|MEMORY_PRESSURE_|VIRTUAL_ENV|ZSH_TMUX_|GAMEMODE|VK_|VULKAN_|LIBVA_|VDPAU_|GBM_|FLATPAK_|SNAP_|DEBUGINFOD_|PAM_|SELINUX_|ANTIGRAVITY_|AGY_)/) {
      print k
    } else if (k ~ /^(WAYLAND_DISPLAY|DESKTOP_SESSION|DESKTOP_STARTUP_ID|GDMSESSION|GDM_LANG|GDM_SETUP_DISPLAY|GNOME_SETUP_DISPLAY|SESSION_MANAGER|INVOCATION_ID|JOURNAL_STREAM|MANAGERPID|MANAGERPIDFDID|NOTIFY_SOCKET|LISTEN_FDS|LISTEN_PID|LISTEN_FDNAMES|COLORTERM|VTE_VERSION|WINDOWID|WINDOWPATH|XCURSOR_THEME|XCURSOR_SIZE|CHROME_DESKTOP|FC_FONTATIONS|NO_AT_BRIDGE|MOTD_SHOWN|LD_PRELOAD|LD_LIBRARY_PATH|ELECTRON_RUN_AS_NODE|DYLD_INSERT_LIBRARIES|XAUTHORITY|mesa_glthread|SNAP|APPIMAGE|APPDIR|OWD|USERNAME|MAIL|LS_COLORS|COLORFGBG|VSSCRIPT_PATH|CHROME_DEVTOOLS_MCP_JS|LC_ADDRESS|LC_IDENTIFICATION|LC_MEASUREMENT|LC_NAME|LC_PAPER|LC_TELEPHONE|PAGER|GIT_PAGER|MANPAGER|MANROFFOPT|SHLVL|DISABLE_AUTO_UPDATE)$/) {
      print k
    }
  }
  /^BASH_FUNC_/ {
    k = $0
    sub(/%%=.*/, "", k)
    sub(/=.*/, "", k)
    print k
  }')
for _var in $_linux_vars; do
  case "$_var" in
    BASH_FUNC_*)
      _fn="${_var#BASH_FUNC_}"
      _fn="${_fn%%%}"
      unset -f "$_fn" 2>/dev/null || true
      unset -v "$_var" 2>/dev/null || true
      ;;
    *)
      unset -v "$_var" 2>/dev/null || unset "$_var" 2>/dev/null || true
      ;;
  esac
done
unset _linux_vars _var _fn _fd

if [ -n "${DARLING_WORKSPACE:-}" ] && ! python3 scripts/nix-state.py check; then
  echo 'Rootless runtime readiness is missing or incompatible; run darling-lol --installer in a terminal.' >&2
  exit 1
fi
export PATH="${DARLING_RUNNER_DIR:+$DARLING_RUNNER_DIR:}$repo/usr-local/bin:/usr/local/bin:$PATH"

python3 scripts/configure.py >/dev/null
if [ -d build/venv/bin ]; then PATH="$repo/build/venv/bin:$PATH"; export PATH; fi
runner="build/runtime/tools/run-riot-client.sh"
cmd="sh $runner"


# macOS identity stealth: enforce Apple MacBookPro16,1 GPU name and VRAM budget
export DARLING_METAL_GPU_NAME="${DARLING_METAL_GPU_NAME:-AMD Radeon Pro 5500M}"
export DARLING_METAL_MAC_GPU_NAME="${DARLING_METAL_MAC_GPU_NAME:-1}"
export DARLING_METAL_VRAM_MB="${DARLING_METAL_VRAM_MB:-4096}"

if [ "${RCLOL_GAMEMODE:-auto}" != "0" ] && command -v gamemoderun >/dev/null 2>&1; then
  cmd="gamemoderun $cmd"
fi

if [ "${RCLOL_GPU:-auto}" != "intel" ] && [ -z "${__NV_PRIME_RENDER_OFFLOAD:-}" ] && command -v prime-run >/dev/null 2>&1; then
  cmd="prime-run $cmd"
fi

exec $cmd

