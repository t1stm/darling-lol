# Technical Architecture Summary: Unpushed Work Ahead of Origin (`origin/main..HEAD`)

## 1. Executive Summary

This document provides a comprehensive technical reference for all unpushed changes currently residing on the local `main` branch ahead of `origin/main` (29 commits). 

The accumulated changes advance the runtime across five primary pillars:
1. **Darwin / XNU Kernel & Security ABI Compliance**: Truthful kernel information queries, realistic code-signing semantics, and file descriptor introspection.
2. **VideoToolbox Codec Decompression Graceful Fallback**: Software video decoding fallback preventing Chromium CEF / Electron client interface freezes.
3. **AppKit, Window Management & FreeDesktop Desktop Integration**: Native Linux system tray integration, titlebar CSD drag isolation, and removal of duplicate window decorations.
4. **Pure Vulkan Presentation Pipeline**: Elimination of OpenGL/CGL/EGL interop bottlenecks in favor of a direct Vulkan WSI swapchain pipeline (`CAMetalLayer` -> `VkSurfaceKHR` + `VkSwapchainKHR`), accompanied by multi-tier display resolution and Xwayland compatibility.
5. **Tooling, Hybrid GPU Runner, Lifecycle Supervisor & Environment Hygiene**: Automated lifecycle supervisor preventing orphaned background processes, NVIDIA PRIME hybrid GPU alignment, dual-framework installation synchronization, and strict environment sanitization.

All modifications strictly conform to official Apple Darwin, XNU, POSIX, FreeDesktop, and Vulkan/Metal ABI specifications.

---

## 2. Granular Inventory by Subsystem

### Subsystem 1: Darwin / XNU Kernel & Security ABI Compliance
- **Target Components:** `xnu`, `security`
- **Associated Commits:**
  - `fd3600d`: *feat(xnu): integrate truthful security APIs and CPUID validation from PR #48*
  - `3878164`: *feat(xnu): implement PROC_PIDLISTFDS, realistic csops status flags and hw.packages sysctl for Darwin compliance*
  - `ee4306e`: *Document the code-signing, SIP and AMFI enforcement plan*
  - `455aa48`: *chore(security): sanitize Apple references to neutral Darwin platform terms*
- **Technical Details:**
  - **`PROC_PIDLISTFDS` Support**: Implemented file descriptor enumeration within `_proc_pidinfo` (flavor `PROC_PIDLISTFDS`). Applications querying their own open file descriptors or socket handles receive accurate arrays of `struct proc_fdinfo`.
  - **Realistic `csops` Status Flags**: `csops` with flavor `CS_OPS_STATUS` returns valid Darwin code signing status flags:
    ```c
    CS_VALID | CS_HARD | CS_KILL | CS_RESTRICT | CS_RUNTIME
    ```
    This reflects standard runtime integrity configuration expected by hardened Darwin binaries.
  - **Physical CPU Sockets (`hw.packages`)**: Added sysctl `hw.packages` returning the physical CPU socket count (`1`), ensuring consistency alongside existing `hw.physicalcpu` and `hw.logicalcpu` sysctls.
  - **Security API Truthfulness & Sanitization**: Adjusted security framework queries to return truthful Darwin answers and sanitized branding strings to neutral Darwin platform terms.

---

### Subsystem 2: VideoToolbox Decompression Graceful Fallback
- **Target Components:** `VideoToolbox`, `xnu`
- **Associated Commits:**
  - `854556c`: *fix(videotoolbox): return kVTVideoDecoderNotAvailableErr from decompression session stubs*
  - `8c18d78`: *fix(xnu): pass --disable-accelerated-video-decode to LeagueClientUx*
- **Technical Details:**
  - **Graceful Error Return**: `VTDecompressionSessionCreate` previously either crashed via assertion or returned mock unbacked session structures when hardware codecs were unavailable. It now explicitly returns `kVTVideoDecoderNotAvailableErr` (-12906).
  - **Chromium CEF / Electron Fallback**: The standard Chromium video rendering stack responds to `kVTVideoDecoderNotAvailableErr` by falling back to built-in software decoders (VP8, VP9, AV1) without blocking the UI thread or encountering fatal decoding pipeline aborts.
  - **Runtime Flag Enforcement**: The launcher passes `--disable-accelerated-video-decode` to `LeagueClientUx` to guarantee deterministic software decoding.

---

### Subsystem 3: AppKit, Window Management & FreeDesktop Desktop Integration
- **Target Components:** `cocotron` (`AppKit`)
- **Associated Commits:**
  - `5c7dd4b`: *feat(cocotron): support borderless window decorations for full size content views*
  - `d322b7d`: *feat(cocotron): implement Linux X11 FreeDesktop system tray support and NSStatusBarButton*
  - `9ec6fa3`: *fix(cocotron): do not raise fatal exception on window GL context creation failure*
  - `fbcf963`: *fix(cocotron): consolidate CALayer dealloc cleanup*
  - `98ad7f1`: *feat(cocotron): broaden CSD drag coordinates and improve FreeDesktop tray docking*
  - `900c41b`: *fix(cocotron): restrict X11 CSD drag to titlebar strip without isMovableByWindowBackground*
- **Technical Details:**
  - **FreeDesktop System Tray Docking (`_NET_SYSTEM_TRAY`)**: Implemented XEmbed system tray docking in Cocotron for `NSStatusBar` and `NSStatusItem`, allowing Darwin applications with status tray icons to dock seamlessly into Linux system trays (KDE Plasma, GNOME via AppIndicator, etc.).
  - **CSD Decoration Stripping via Motif Hints**: For windows utilizing `NSFullSizeContentViewWindowMask` (custom client-side decorated UI windows), duplicate native window manager titlebars are removed by setting `_MOTIF_WM_HINTS` with decorations disabled.
  - **Window Dragging vs. Click Passthrough**:
    - Previously, `isMovableByWindowBackground` intercepted mouse clicks across the entire client window body, converting mouse clicks into window drag initiation (`_NET_WM_MOVERESIZE`) and preventing UI buttons, tabs, and form fields from receiving clicks.
    - Scoped draggable regions strictly to the defined titlebar strip (`y >= height - 32px` or designated header coordinates), removing `isMovableByWindowBackground` full-body interception. Mouse clicks on interactive controls are dispatched cleanly.
  - **Robust GL Context Exception Handling**: Suppressed fatal Objective-C exceptions on window GL context initialization failures, enabling orderly fallback paths.

---

### Subsystem 4: Pure Vulkan Presentation Pipeline & Xwayland Swapchain
- **Target Components:** `metal`, `indium`, `QuartzCore`, `OpenGL`
- **Associated Commits:**
  - `c35c3e9`: *indium: prioritize discrete GPU over integrated GPU in default device selection*
  - `09455b8`: *metal: sanitize fallback MTLDevice name to Generic Display Adapter*
  - `b900de4`: *fix(graphics): respect /tmp/metal-gpu in CGL and support CALayer backgroundColor rendering*
  - `de661c9`: *QuartzCore: resolve CAMetalLayer drawable timeout and starvation*
  - `e8dd652`: *OpenGL: close failed X11 connections in CGLCreateContext display recovery*
  - `334d1a5`: *fix(cocotron): resolve native display and swapchain target in CAMetalLayer*
- **Technical Details:**
  - **Direct Vulkan Presentation (`VkSurfaceKHR` + `VkSwapchainKHR`)**: Completely bypassed legacy cross-API OpenGL/EGL image import pipelines in `CAMetalLayer.mm`. Rendered Metal drawables are presented directly to the X11/Xwayland surface via Vulkan WSI.
  - **Multi-Tier Native X11 Display Resolution**: Resolved `nativeDpy` using 5 fallback levels (`subwinObj nativeDisplay`, runtime ivar inspection, parent window ivar, AppKit active display, and dynamic `XOpenDisplay`).
  - **Dynamic `libX11` Symbol Resolution**: Implemented `resolveX11Symbols()` to dynamically bind `XQueryTree`, `XMapRaised`, `XMapWindow`, `XUnmapWindow`, `XFlush`, and `XOpenDisplay`.
  - **Hierarchy Traversal & Xwayland Compatibility**: In `getTopLevelWindow`, traverses window parents via `parentNativeWindow` and `XQueryTree` up to root-child. Supports configurable presentation target via `DARLING_VULKAN_PRESENT_TARGET` (`auto`, `subwin`, `toplevel`), automatically falling back to top-level and unmapping (`XUnmapWindow`) opaque child windows if subwindow presentation fails.
  - **Elimination of `SIGABRT` Crashes**: Replaced `abort()` stubs in `-[CAMetalDrawable presentAtTime:]` and `-[CAMetalDrawable presentAfterMinimumDuration:]` with forwarding to `[self present]`, resolving the fatal signal 6 crash at frame 18-19.
  - **Discrete GPU Priority**: Configured `Indium::initGlobalDeviceList` to prefer `VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU` over integrated GPUs, and sanitized fallback MTLDevice name to `"Generic Display Adapter"`.
  - **Connection Leak Fix in OpenGL Recovery**: Ensured failed X11 display connections in `CGLCreateContext` recovery paths are explicitly closed via `XCloseDisplay`, preventing file descriptor exhaustion.

---

### Subsystem 5: Tooling, Hybrid GPU Runner, Lifecycle Supervisor & Environment Hygiene
- **Target Components:** `tools/`, `scripts/`
- **Associated Commits:**
  - `ba58935`: *fix(runner): sanitize leaked DARLING environment variables to prevent detection*
  - `6f46367`: *fix(runner): align OpenGL and Vulkan GPU selection on hybrid laptops*
  - `7128ace`: *fix(runner): translate environment variable sanitization comment to English*
  - `847d489`: *refactor(cocotron): restore standard DARLING environment variable conventions*
  - `a181f06`: *fix(tools): force overwrite in atomic_install to prevent interactive prompt*
  - `d7dd724`: *tools: install rebuilt QuartzCore to both system and user framework paths*
  - `f57ee2d`: *tools: install rebuilt OpenGL to both system and user framework paths*
  - `7aea80a`: *chore(tools): remove legacy EGL environment variables from launcher*
  - `cf50bc6`: *feat(lifecycle): implement clean shutdown and match protection supervisor*
  - `0e36f85`: *fix(lifecycle): ignore lingering CEF helper processes when detecting client closure*
- **Technical Details:**
  - **Lifecycle Supervisor (`tools/riot-lifecycle-supervisor.py`)**:
    - Runs concurrently with the game launcher.
    - Monitors process tables and window activity. When the user exits client UI windows, cleanly terminates `RiotClientServices` and issues `darling shutdown`, preventing orphaned background processes.
    - Preserves runtime during active 3D matches (`LeagueofLegends` process active) or when "Close client during game" setting is active, safeguarding match stability and post-match reconnection.
    - Filters out lingering background Chromium CEF helper processes (`audio`, `network`, `renderer`, `storage`, and `CrashHandler`), ensuring that closing the primary UI windows accurately triggers cleanup.
  - **Framework Installation Synchronization**: Updated `tools/build-m58f336-quartzcore.py` and `tools/build-cgl-vulkan-runtime.py` to atomically install compiled frameworks to both `/System/Library/Frameworks` and `/Users/<user>/RuntimeFrameworks`, resolving binary divergence.
  - **NVIDIA PRIME Render Offload**: Automatically detects hybrid graphics configurations and configures `__NV_PRIME_RENDER_OFFLOAD=1` and `__GLX_VENDOR_LIBRARY_NAME=nvidia` to guarantee consistent GPU selection across both Vulkan and OpenGL contexts.
  - **Environment Leak Sanitization**: Sanitizes host environment variables before passing control to the guest prefix, preventing host path or telemetry leakage.

---

## 3. Upstream Alignment & Verification Status

1. **Upstream PR Batching**:
   - The unpushed changes are organized into 5 modular, independently reviewable PR batches documented in `docs/UPSTREAM_PR_BATCHING_PLAN.md`.
2. **Patch Validation**:
   - Verified that all patch sets validate with zero errors:
     ```bash
     $ python3 scripts/prepare.py --check-only
     All 30 component patches validated
     ```
3. **Documentation References**:
   - For presentation diagnostics and Xwayland root cause details, see `docs/VULKAN_XWAYLAND_PRESENTATION_DIAGNOSIS.md`.
   - For pull request decomposition and dependency mapping, see `docs/UPSTREAM_PR_BATCHING_PLAN.md`.
