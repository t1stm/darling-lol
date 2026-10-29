#!/bin/sh
# Native presentation via direct X11 and Vulkan swapchain.
set -eu
# Native MangoHud uses the guest PID against the host /proc view and can abort
# in GPU_fdinfo::find_fd (issue #38). Disable inherited implicit activation
# before any helper can start Darling, including first-time installation.
unset MANGOHUD
export DISABLE_MANGOHUD=1
# Native guest crashes created large system core files and exhausted this disk.
# Address-only diagnostics suffice; bound this runner and its new namespace.
if [ "${RCLOL_CORE_DUMPS:-0}" != 1 ]; then
 ulimit -c 0
fi
runner_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$runner_dir/runtime-paths.sh"
# Opt-in partial recovery: if Darling is alive but a previous client tree is
# windowless, stop only that client/CEF tree and reuse the runtime. Never
# touches the game, darlingserver or the runtime sockets.
if [ "${RCLOL_RECOVER_STALE_CLIENT:-0}" = 1 ]; then
 python3 "$runner_dir/recover-stale-client.py"
fi
if [ "${RCLOL_RECOVER_HIDDEN_CLIENT:-0}" = 1 ]; then
 python3 "$runner_dir/recover-hidden-riot-client.py"
fi
# Opt-in cleanup of helpers left by an earlier launcher. This runs before the
# current helper is started. It removes only helpers of this prefix whose
# parent is init/systemd, so a helper of a live launcher is not touched.
if [ "${RCLOL_CLEAN_STALE_HELPERS:-0}" = 1 ]; then
 python3 "$runner_dir/clean-stale-helpers.py" --prefix "$prefix_dir" ||
  echo 'clean-stale-helpers: cleanup failed; continuing' >&2
fi
# The bundled downloader rejects IPv6 CONNECT_TO addresses. Only Riot CDN
# AAAA lookups are suppressed; set this to 0 to retain the upstream resolver.
export RCLOL_CDN_IPV4_ONLY="${RCLOL_CDN_IPV4_ONLY:-1}"
# Capture ownership before the certificate helper can start this session's runtime.
runtime_at_start=$(python3 "$runner_dir/session-supervisor.py" --prefix "$prefix_dir" --probe-runtime)
# It closes every fd above stderr, including the D-Bus socket gamemoderun's preloaded
# libgamemodeauto opened, whose exit hook then aborts; it does not need GameMode.
env -u LD_PRELOAD python3 "$runner_dir/ensure-darling-runtime.py"
python3 "$runner_dir/ensure-darling-service-accounts.py"
python3 "$runner_dir/ensure-league-runtime-layout.py"
# Security's system trust domain (SecTrustSettingsCopyCertificates) needs a root keychain and
# trust record built from the host CA bundle. Only a changed bundle starts Darling; a failure
# is reported but does not stop the launch.
python3 "$runner_dir/ensure-darling-root-certificates.py" ||
 echo 'Continuing without a Darling system root store; TLS clients may report untrusted roots' >&2
# Discard argument-rewriting settings from the former injected shim.
unset RCLOL_APP_ARGS RCLOL_APP_ARGS_SLOT RCLOL_APP_ARG2 RCLOL_APP_ARG2_SLOT
unset RCLOL_APP_ARG3 RCLOL_APP_ARG3_SLOT RCLOL_UX_ARG1 RCLOL_UX_ARG1_SLOT
unset RCLOL_UX_ARG2 RCLOL_UX_ARG2_SLOT
# The paired runtime presents completed GPU textures without CPU readback.
# Explicit 0 or an empty value selects the CPU fallback for diagnostics.
# DARLING_METAL_MAC_GPU_NAME reports the MacBookPro16,1 GPU of the host vendor (AMD or Intel) as
# MTLDevice.name, matching the model IOKit reports; memory figures stay the host's.
# VRAM clamp: honor an explicit DARLING_METAL_VRAM_MB, otherwise pin 4096 MB so the
# 5500M identity does not leak the host card's heap size.
export DARLING_METAL_VRAM_MB="${DARLING_METAL_VRAM_MB:-4096}"
for option in RCLOL_GPU_DIRECT_PRESENT RCLOL_GPU_DIRECT_ASYNC DARLING_CA_PRESENT_AT_COMMIT DARLING_CA_SKIP_LOCAL_IOSURFACE_RENDER RCLOL_FORWARD_MOUSE_MOVED RCLOL_MOUSE_CONFINEMENT DARLING_METAL_MAC_GPU_NAME; do
 eval 'value=${'"$option"'-1}'
 case "$value" in 0|'') unset "$option";; *) export "$option=$value";; esac
done
# VSync defaults to 0 (uncapped) unless explicitly requested
eval 'vsync_val=${RCLOL_GPU_DIRECT_VSYNC-0}'
case "$vsync_val" in 0|'') unset RCLOL_GPU_DIRECT_VSYNC;; *) export RCLOL_GPU_DIRECT_VSYNC="$vsync_val";; esac
export DARLING_METAL_GPU_NAME="${DARLING_METAL_GPU_NAME:-AMD Radeon Pro 5500M}"
prefix=$prefix_dir
# Resolve the loader before the environment filter replaces PATH with the Mac layout.
darling_bin=$(command -v darling) || {
 echo 'darling loader not found in PATH' >&2
 exit 1
}
# RIOT_GUEST_HOME is host-side; DYLD paths must be relative to the guest root.
case "$guest_home" in
 "$prefix"/*) guest_path=/${guest_home#"$prefix"/} ;;
 *) echo "RIOT_GUEST_HOME must be inside DPREFIX" >&2; exit 1 ;;
esac
# The first-time installer puts the client in /Users/Shared/Riot Games and then
# hands off through LaunchServices, which does not start it under Darling. Link
# the installed client where the normal launch expects it.
client="$prefix/Applications/Riot Client.app"
shared="$prefix/Users/Shared/Riot Games/Riot Client.app"
if [ -z "${RIOT_LAUNCHER_HOST:-}" ] && [ ! -e "$client" ]; then
 if [ ! -d "$shared" ]; then
  echo "Riot Client is not installed in $prefix; run scripts/installer.sh first" >&2
  exit 1
 fi
 if [ -L "$client" ]; then
  # An absolute link (/Users/Shared/...) resolves only inside the guest; the
  # guest still uses it for --app-root, but start the client by its real path.
  client=$shared
 else
  ln -s "../Users/Shared/Riot Games/Riot Client.app" "$client"
 fi
fi
# Opt-in automatic client-in-game handling. Start the watcher only after the
# installed-client check above: a failed installer launch must not leave a
# helper behind. The preference selector returns no action for missing or
# invalid close-during-game values.
if [ -z "${RIOT_LAUNCHER_HOST:-}" ]; then
 if [ "${RCLOL_CLIENT_IN_GAME_TRICKS:-0}" = 1 ]; then
  pref="$prefix_dir/Applications/League of Legends.app/Contents/LoL/Config/LCULocalPreferences.yaml"
  mode=$(python3 "$runner_dir/client-in-game-tricks.py" "$pref" 2>/dev/null || echo none)
  case "$mode" in
   close)
    echo 'client-in-game-tricks: closeLeagueClientDuringGame=true -> close helper' >&2
    python3 "$runner_dir/close-league-client-in-game.py" --detach &
    ;;
   hide)
    echo 'client-in-game-tricks: closeLeagueClientDuringGame=false -> hide helper' >&2
    python3 "$runner_dir/hide-league-client-in-game.py" --detach &
    ;;
   *)
    echo 'client-in-game-tricks: no action (client optimizations disabled or preferences missing/invalid)' >&2
    ;;
  esac
 elif [ "${RCLOL_CLOSE_CLIENT_IN_GAME:-0}" = 1 ]; then
  python3 "$runner_dir/close-league-client-in-game.py" --detach &
 elif [ "${RCLOL_HIDE_CLIENT_IN_GAME:-0}" = 1 ]; then
  python3 "$runner_dir/hide-league-client-in-game.py" --detach &
 fi
fi
A=${RIOT_LAUNCHER_HOST:-"$client/Contents/MacOS/RiotClientServices"}
# External XIM (for example Fcitx) consumes keys before Darling forwards them.
# Use Xlib's local input method; allow explicit testing of another modifier.
# Linux C.UTF-8 is not a supported codecvt locale in the macOS client.
# Keep this scoped to the guest; product region/locale arguments remain explicit.
# The first-time installer (RIOT_LAUNCHER_HOST) exits immediately when given --app-root for a
# Riot Client that is not installed yet; only pass it for the installed client.
# Its native intro screen renders image layers with a blue cover and does not take clicks
# under Darling, so start the install directly (the Riot Client UI that follows works).
if [ -n "${RIOT_LAUNCHER_HOST:-}" ]; then
 set -- --skip-to-install --launch-product=league_of_legends --launch-patchline=live
else
 set -- --app-root="/Applications/Riot Client.app"
 # The League login theme (video background, Install/Play button) is only shown when the client
 # is started for a product. RCLOL_LAUNCH_PRODUCT= (empty) starts the bare client instead.
 if [ -n "${RCLOL_LAUNCH_PRODUCT-league_of_legends}" ]; then
  set -- "$@" --launch-product="${RCLOL_LAUNCH_PRODUCT-league_of_legends}" \
    --launch-patchline="${RCLOL_LAUNCH_PATCHLINE-live}"
 fi
fi
# --- darling-lol perf: scheduling & driver latency hints ---
# Refresh rate for display link, async presenter, and frame pacing.
# NOTE: Current implementation and testing specifically target KDE Plasma + Wayland
# (KWin + Xwayland via kscreen-doctor / X11 WSI). GNOME + Wayland (Mutter) and other
# compositors are not actively covered at this time and are left to upstream maintainers.
# If RCLOL_REFRESH_HZ is already set in the environment, honor the override directly.
if [ -z "${RCLOL_REFRESH_HZ-}" ]; then
  if command -v kscreen-doctor >/dev/null 2>&1; then
    RCLOL_REFRESH_HZ=$(python3 -c '
import subprocess, re, sys, json
# 1. Try kscreen-doctor -j (JSON mode)
try:
    res = subprocess.run(["kscreen-doctor", "-j"], capture_output=True, text=True, timeout=2)
    if res.returncode == 0 and res.stdout.strip():
        data = json.loads(res.stdout)
        outputs = data.get("outputs", [])
        outputs.sort(key=lambda o: (not o.get("enabled", False), not o.get("connected", False), o.get("priority", 999)))
        for out in outputs:
            if out.get("enabled") and out.get("connected"):
                cur_id = str(out.get("currentModeId") or out.get("currentMode") or "")
                for m in out.get("modes", []):
                    if str(m.get("id")) == cur_id:
                        rate = float(m.get("refreshRate", 0))
                        if rate > 0:
                            print(int(round(rate)))
                            sys.exit(0)
except Exception:
    pass

# 2. Try kscreen-doctor -o (human-readable mode)
try:
    res = subprocess.run(["kscreen-doctor", "-o"], capture_output=True, text=True, timeout=2)
    if res.returncode == 0 and res.stdout.strip():
        best = None
        for chunk in res.stdout.split("Output:"):
            if not chunk.strip():
                continue
            if "enabled" in chunk and "connected" in chunk:
                m = re.search(r"@([0-9]+(?:\.[0-9]+)?)\*", chunk)
                if m:
                    rate = int(round(float(m.group(1))))
                    if "priority 1" in chunk or "primary" in chunk:
                        best = rate
                        break
                    elif best is None:
                        best = rate
        if best:
            print(best)
            sys.exit(0)
except Exception:
    pass
sys.exit(1)
' 2>/dev/null || true)
  fi

  if [ -z "${RCLOL_REFRESH_HZ-}" ] && command -v xrandr >/dev/null 2>&1; then
    RCLOL_REFRESH_HZ=$(xrandr --current 2>/dev/null | awk '
      / connected/ { primary = / primary / }
      /\*/ { for (i = 2; i <= NF; i++) if ($i ~ /\*/) { rate = $i; sub(/[*+]+/, "", rate)
              if (primary) { print int(rate + 0.5); found = 1; exit } else if (first == "") first = int(rate + 0.5) } }
      END { if (!found && first != "") print first }')
  fi

  # Fallback to high-refresh default (165 Hz) if autodetection did not resolve a rate
  if [ -z "${RCLOL_REFRESH_HZ-}" ]; then
    RCLOL_REFRESH_HZ=165
  fi
fi
if [ -n "${RCLOL_REFRESH_HZ-}" ]; then export RCLOL_REFRESH_HZ; fi
# Vulkan WSI & Mesa optimizations
export MESA_NO_ERROR="${MESA_NO_ERROR:-1}"
# Mesa resolves its shader disk cache below $HOME, which inside the guest is
# /Users/<user>: that path does not exist on the host filesystem, so every process logs
# "Failed to create /Users for shader cache (Permission denied)---disabling" and
# recompiles every shader on start (212 such lines in one launcher log). The host Mesa
# loaded into the guest reads MESA_SHADER_CACHE_DIR verbatim, so point it at a host
# directory; Mesa creates mesa_shader_cache/ and radv_builtin_shaders/ below it.
cache_root=${XDG_CACHE_HOME:-${HOME:-$prefix_dir}/.cache}/darling-lol
MESA_SHADER_CACHE_DIR="${MESA_SHADER_CACHE_DIR:=$cache_root}"
export MESA_SHADER_CACHE_DIR
mkdir -p "$MESA_SHADER_CACHE_DIR" 2>/dev/null || true
# NVIDIA proprietary driver: smooth 2-frame buffering, threaded optimizations and scheduler yielding
export __GL_MaxFramesAllowed="${__GL_MaxFramesAllowed:-2}"
export __GL_THREADED_OPTIMIZATIONS="${__GL_THREADED_OPTIMIZATIONS:-1}"
export __GL_YIELD="${__GL_YIELD:-USLEEP}"
export DARLING_VULKAN_PRESENT_TARGET="${DARLING_VULKAN_PRESENT_TARGET:-toplevel}"
# Reduce timer slack for tighter scheduling in the game process tree.
if [ -w /proc/self/timerslack_ns ]; then
  echo 1 > /proc/self/timerslack_ns 2>/dev/null || true
fi
# --- darling-lol GPU alignment (hybrid NVIDIA / integrated graphics) ---
# Ensure OpenGL (GLX/EGL) and Vulkan (Indium/Metal) run on the exact same GPU,
# preventing opaque-FD / DMABUF cross-GPU import failures.
gpu_selector=""
if [ -f /tmp/metal-gpu ]; then
  gpu_selector=$(head -n 1 /tmp/metal-gpu 2>/dev/null | tr -d ' \t\r\n' | tr '[:upper:]' '[:lower:]')
elif [ -n "${METAL_INDIUM_GPU:-}" ]; then
  gpu_selector=$(echo "$METAL_INDIUM_GPU" | tr -d ' \t\r\n' | tr '[:upper:]' '[:lower:]')
elif [ -n "${RCLOL_GPU:-}" ]; then
  gpu_selector=$(echo "$RCLOL_GPU" | tr -d ' \t\r\n' | tr '[:upper:]' '[:lower:]')
fi

has_nvidia=0
if [ -c /dev/nvidia0 ] || [ -d /proc/driver/nvidia ]; then
  has_nvidia=1
fi

case "$gpu_selector" in
  intel*|integrated*|mesa*|llvmpipe*|cpu*|0)
    unset __NV_PRIME_RENDER_OFFLOAD __GLX_VENDOR_LIBRARY_NAME __VK_LAYER_NV_optimus __EGL_VENDOR_LIBRARY_FILENAMES VK_DRIVER_FILES VK_ICD_FILENAMES
    if [ -f /usr/share/vulkan/icd.d/intel_icd.x86_64.json ]; then
      export VK_DRIVER_FILES=/usr/share/vulkan/icd.d/intel_icd.x86_64.json
      export VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/intel_icd.x86_64.json
    fi
    ;;
  amd*|radeon*|radv*)
    export DRI_PRIME=1
    ;;
  *)
    if [ "$has_nvidia" = 1 ]; then
      export __NV_PRIME_RENDER_OFFLOAD=1
      export __GLX_VENDOR_LIBRARY_NAME=nvidia
      export __VK_LAYER_NV_optimus=NVIDIA_only
      if [ -f /usr/share/vulkan/icd.d/nvidia_icd.x86_64.json ]; then
        export VK_DRIVER_FILES=/usr/share/vulkan/icd.d/nvidia_icd.x86_64.json
        export VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.x86_64.json
      elif [ -f /usr/share/vulkan/icd.d/nvidia_icd.json ]; then
        export VK_DRIVER_FILES=/usr/share/vulkan/icd.d/nvidia_icd.json
        export VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.json
      fi
    fi
    ;;
esac

# Auto-detect active DISPLAY if not set or empty
if [ -z "${DISPLAY:-}" ]; then
  for s in /tmp/.X11-unix/X*; do
    if [ -S "$s" ]; then
      DISPLAY=":${s##*/X}"
      break
    fi
  done
  DISPLAY="${DISPLAY:-:0}"
fi

# On affected setups Chromium's default temp directory is unusable. Electron
# can copy app.asar entries to temporary files for async reads and report a
# failed copy as "not found". Use a writable guest directory by default.
# exec-guest.py closes host file descriptors above stderr before starting the guest. A shell
# loop cannot: dash only accepts single-digit descriptors in redirections.
# Keep the launcher as a supervisor: on Ctrl+C/terminal close it stops the
# guest session instead of orphaning launchd/mldr and the client tree. It also
# shuts the runtime down after the loader exits, unless another session already
# owned it. Set RCLOL_CLEAN_ON_EXIT=0 for the previous exec-only behaviour, and
# RCLOL_STOP_AFTER_CLIENT_SECONDS=N to stop once the client window has been
# gone for N seconds with no game running.
exec python3 "$runner_dir/session-supervisor.py" --prefix "$prefix" \
  --darling "${darling_bin:-darling}" --runtime-at-start "$runtime_at_start" -- \
  python3 "$runner_dir/exec-guest.py" env -u ELECTRON_RUN_AS_NODE -u DYLD_INSERT_LIBRARIES -u LD_PRELOAD EGL_PLATFORM=x11 \
  MAC_CHROMIUM_TMPDIR="${MAC_CHROMIUM_TMPDIR:-/private/tmp}" \
  LANG="${RCLOL_GUEST_LOCALE:-en_US.UTF-8}" LC_ALL="${RCLOL_GUEST_LOCALE:-en_US.UTF-8}" \
  mesa_glthread="${RCLOL_MESA_GLTHREAD-${mesa_glthread-false}}" \
  XMODIFIERS="${RCLOL_XMODIFIERS:-@im=none}" DISPLAY="${DISPLAY}" \
  DYLD_LIBRARY_PATH="${DYLD_LIBRARY_PATH:-$guest_path/RuntimeLibraries}" \
  DYLD_FRAMEWORK_PATH="${DYLD_FRAMEWORK_PATH:-$guest_path/RuntimeFrameworks}" \
  DARLING_XSHM_LIBRARY="${DARLING_XSHM_LIBRARY:-$guest_path/libDarlingXShm.dylib}" \
  RCLOL_REFRESH_HZ="${RCLOL_REFRESH_HZ:-165}" \
  python3 "$runner_dir/riot-lifecycle-supervisor.py" "$darling_bin" "$A" --region="${RCLOL_REGION:-EUW}" --locale="${RCLOL_LOCALE:-en_GB}" \
    "$@" \
    --log-dir="$guest_path/Library/Logs/Riot Games/Riot Client"
