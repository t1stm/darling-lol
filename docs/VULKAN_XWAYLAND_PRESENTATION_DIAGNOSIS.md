# Pure Vulkan Pipeline, Xwayland Presentation, and Render Diagnostics

> [!NOTE]
> For the overall subsystem design and runtime compliance architecture across Darling, see the [Technical Architecture & Runtime Conformance Guide](ARCHITECTURE_AND_RUNTIME_CONFORMANCE.md).

## 1. Architectural Overview

The rendering subsystem of the game engine within Darling was transitioned from legacy OpenGL/CGL/EGL interop to a **100% Pure Vulkan presentation pipeline** (`CAMetalLayer` -> `VkSurfaceKHR` + `VkSwapchainKHR`).

### Operational Status:
1. **Game Simulation, Network & State Transitions**:
   - Connection to game server verified and stable.
   - Asset loading (champions, map geometry, textures, particle effects) completes with zero memory leaks.
   - Full state progression verified: `PREGAME` -> `SPAWN` -> `GAMESTATE_GAMELOOP`.
   - **Audio & Input**: In-game audio streams correctly and mouse click input dispatches into the 3D simulation space.
2. **Crash Mitigation (`SIGABRT` Resolved)**:
   - Previously, the game encountered a fatal signal 6 (`SIGABRT`) at the 18-19s mark during `EndRender & EndFrame`.
   - Root cause: Stubs in `-[CAMetalDrawable presentAtTime:]` and `-[CAMetalDrawable presentAfterMinimumDuration:]` in `CAMetalDrawable.mm` explicitly invoked `abort()`.
   - Resolution: Forwarded both methods to `[self present]`. Frame submission proceeds continuously without termination.
3. **AppKit Window Dragging & Client Window Management**:
   - Resolved mouse button pass-through in `X11Display.m` by scoping CSD dragging strictly to the titlebar strip and removing `isMovableByWindowBackground` interception on full window bodies.
   - Duplicate window decorations removed via `_MOTIF_WM_HINTS` for custom CSD views.
4. **Lifecycle Supervisor (`tools/riot-lifecycle-supervisor.py`)**:
   - Intelligent lifecycle monitoring that preserves the Darling runtime and background services during active matches and lobby transitions.
   - Automatically shuts down `RiotClientServices` and the Darling server when all client windows are closed by the user, while cleaning up orphaned Chromium CEF helper processes (`audio`, `network`, `renderer`, `storage`).

---

## 2. Runtime Binary Synchronization & Framework Path Verification

During diagnosis of runtime presentation failures, loader and path resolution behaviors were audited across guest environments:
1. **Dynamic Linker Binding (`LC_LOAD_DYLIB`)**:
   - The game binary (`LeagueofLegends`) directly references `/System/Library/Frameworks/QuartzCore.framework/Versions/A/QuartzCore`.
   - The launcher environment (`tools/run-riot-client.sh`) configures `DYLD_FRAMEWORK_PATH=/Users/fgeroldi/RuntimeFrameworks`.
2. **Framework Path Precedence**:
   - Verification confirmed that the AppKit X11 backend (`X11.backend`) resided exclusively in `/Users/fgeroldi/RuntimeFrameworks/AppKit.framework` (the corresponding path under `/System/Library/...` was empty), confirming that `DYLD_FRAMEWORK_PATH` takes precedence during runtime execution.
3. **Binary Divergence Mitigation**:
   - Auditing identified a timestamp and size divergence between `~/.darling/System/Library/Frameworks/QuartzCore.framework/Versions/A/QuartzCore` (258,220 bytes) and `~/.darling/Users/fgeroldi/RuntimeFrameworks/QuartzCore.framework/Versions/A/QuartzCore` (262,204 bytes).
   - The compilation script `tools/build-m58f336-quartzcore.py` was updated to atomically synchronize identical binaries across both the system framework and user runtime framework paths.

---

## 3. Xwayland Black Screen Diagnosis & Root Cause Analysis

### A. Symptom Description
During 3D match startup under Wayland + Xwayland (KWin compositor), the match engine initialized, network synced, and audio played, but the target X11 window displayed only a black background.

### B. Root Cause 1: Native Display Resolution Failure (`nativeDpy == NULL`)
- In Cocotron, `CAMetalLayer.mm` previously obtained the native X11 display pointer solely through `_CGSNativeDisplay(CGSMainConnectionID())`.
- In `CoreGraphics/CGS.m`:
  ```objc
  void* _CGSNativeDisplay(CGSConnectionID connId) {
      return [_CGSConnectionForID(connId) nativeDisplay];
  }
  ```
- In `CGSConnectionX11`, `-(void *)nativeDisplay` was never implemented, and the base class `CGSConnection` provided only an abstract stub. Additionally, `System/Library/Frameworks/CoreGraphics.framework/.../Backends/X11.backend` lacked an active executable binary.
- Consequently, `_CGSNativeDisplay(CGSMainConnectionID())` invariably returned `NULL`.

#### Resulting Infinite Loop in `recreateDrawables`:
1. With `nativeDpy == NULL`, the call `getTopLevelWindow(nativeDpy, subwinObj, subWin)` hit an early guard:
   ```cpp
   static void* getTopLevelWindow(void* dpy, id subwinObj, void* nativeWin) {
       if (!dpy || !nativeWin) return nativeWin;
   ```
   This immediately returned `nativeWin` (`0x5200003`) without emitting any diagnostic log.
2. In `recreateDrawables`, the condition:
   ```cpp
   if (pfn_vkCreateXlibSurfaceKHR && presentationWin && nativeDpy)
   ```
   failed because `nativeDpy == NULL`. The entire Vulkan surface creation (`vkCreateXlibSurfaceKHR`) and swapchain allocation (`vkCreateSwapchainKHR`) blocks were bypassed.
3. `_vkSwapchain` remained `VK_NULL_HANDLE`.
4. In `queuePresent:`, encountering `_vkSwapchain == VK_NULL_HANDLE` triggered repeated invocations of `recreateDrawables` on every frame.
5. The cycle looped indefinitely (`recreateDrawables subWin=0x5200003 topLevelWin=0x5200003`) with zero Vulkan WSI calls executed and zero frames presented.

#### The `BadWindow` Artifact:
An earlier hypothesis suggested that `subWin` returned `BadWindow`. Investigation established that this was an artifact of querying window IDs via host X11 inspection utilities after the guest process had already exited. The subwindow handle was completely valid throughout active process execution.

### C. Root Cause 2: Vulkan Instance Extension Probing (`pfn_vkCreateXlibSurfaceKHR == 0x0`)
- After implementing multi-tier display resolution, `nativeDpy` resolved to a valid X11 Display pointer (`0xcfb0630`).
- However, `vkGetInstanceProcAddr(Indium::globalInstance, "vkCreateXlibSurfaceKHR")` returned `NULL`.
- Per Khronos Vulkan specifications, `vkGetInstanceProcAddr` must return `NULL` for any extension function not explicitly enabled in `VkInstanceCreateInfo.ppEnabledExtensionNames`.
- The running `libindium.dylib` lacked dynamic enumeration and enablement of `VK_KHR_xlib_surface` during `VkInstance` creation, leaving the surface creation entrypoint unresolved.

---

## 4. Implemented Architectural Solutions

### 1. Robust Multi-Tier Native Display Resolution
Decoupled X11 display resolution in `CAMetalLayer.mm` across five fallback mechanisms:
1. `-[subwinObj nativeDisplay]` on `X11SubWindow` / `CGSubWindow`.
2. Ivar `_display` via Objective-C runtime introspection on `subwinObj`.
3. Ivar `_display` on the parent window (`parentWindow`).
4. Active AppKit display via `[(X11Display *)[NSDisplay currentDisplay] display]`.
5. Dynamic fallback via `XOpenDisplay(getenv("DISPLAY"))` using `libX11`.

### 2. Display and Window Property Exposure in `X11SubWindow` and `CGSubWindow`
- In `CoreGraphics/include/CoreGraphics/CGSubWindow.h` and `CGSubWindow.m`:
  Declared and implemented `- (void *)parentNativeWindow` and `- (void *)nativeDisplay`.
- In `AppKit/X11.backend/X11SubWindow.h` and `X11SubWindow.m`:
  Implemented:
  ```objc
  - (void *)nativeDisplay { return (void *)_display; }
  - (Display *)display { return _display; }
  - (Window)window { return _window; }
  ```

### 3. Display-Decoupled Top-Level Window Resolution & Hierarchy Traversal
In `getTopLevelWindow`:
- Added diagnostic tracing: `getTopLevelWindow ENTER subWin=%p dpy=%p subwinObj=%p`.
- Traverses parent hierarchies via `[subwinObj parentNativeWindow]`, `[subwinObj parentWindow] windowHandle`, and the `_parent` ivar even if `dpy` is null.
- When `dpy` is valid and `XQueryTree` is resolved via `libX11`, performs full X11 tree traversal up to the root-child window for KWin / Xwayland compatibility.

### 4. Empirical Subwindow and Top-Level Presentation with Dynamic Fallback
- Presentation target selection is controlled via the `DARLING_VULKAN_PRESENT_TARGET` environment variable (`auto` [default], `subwin`, `toplevel`).
- In `auto` mode:
  1. Attempts `VkSurfaceKHR` and `VkSwapchainKHR` creation on `subWin` (DRI3/Present under Xwayland).
  2. Instruments all WSI calls with comprehensive error and capability logging:
     - `vkCreateXlibSurfaceKHR` (verifying `VkResult`).
     - `vkGetPhysicalDeviceSurfaceSupportKHR` (verifying presentation queue support).
     - `vkGetPhysicalDeviceSurfaceCapabilitiesKHR` (logging min/max extents and transform flags).
     - `vkCreateSwapchainKHR` (verifying swapchain handle, dimensions, format, and present mode).
  3. If subwindow presentation fails at any step, automatically falls back to `topLevelWin`.
  4. When presenting on `topLevelWin`, invokes `XUnmapWindow` on the opaque `subWin` child to prevent occlusion of rendered frames.
  5. Upon swapchain creation, transitions to direct frame presentation in `presentDirectVulkan:`.

### 5. Dynamic Loading and Verification of `libX11` Symbols
Implemented `resolveX11Symbols()`, which dynamically searches candidate libraries in order:
- `/usr/lib/native/libX11.dylib`
- `libX11.dylib`
- `libX11.so.6`
- `libX11.so`
- `/usr/lib64/libX11.so.6`

Validates and logs resolved function pointers for: `XQueryTree`, `XFree`, `XOpenDisplay`, `XMapRaised`, `XMapWindow`, `XUnmapWindow`, and `XFlush`.

### 6. Dynamic Vulkan Instance Extension Enablement
- Added instance extension enumeration via `vkEnumerateInstanceExtensionProperties` to detect `VK_KHR_xlib_surface` on the host driver.
- Configured `VkInstanceCreateInfo.ppEnabledExtensionNames` to explicitly enable `VK_KHR_xlib_surface` during `libindium.dylib` initialization.

---

## 5. Verification Checklist & Runtime Diagnostic Signatures

During runtime testing via `tools/run-riot-client.sh` or `scripts/run.sh`, monitor `~/.darling/private/tmp/metal-device.log` to confirm correct presentation operation:

1. **`libX11` Loading and Symbol Resolution**:
   ```text
   [CAMetalLayer] pid=... dlopen("/usr/lib/native/libX11.dylib") -> ...
   [CAMetalLayer] pid=... libX11 symbols: handle=... XQueryTree=... XOpenDisplay=...
   ```
2. **Display and Window Hierarchy Resolution**:
   ```text
   [CAMetalLayer] pid=... recreateDrawables nativeDpy=0x... source=subwinObj.nativeDisplay ...
   [CAMetalLayer] pid=... getTopLevelWindow ENTER subWin=0x... dpy=0x...
   [CAMetalLayer] pid=... getTopLevelWindow: parentNativeWindow resolved topLevelWin=0x...
   ```
3. **Vulkan Surface and Swapchain Allocation**:
   ```text
   [CAMetalLayer] pid=... Attempting Vulkan WSI on subWin window ...
   [CAMetalLayer] pid=... vkCreateXlibSurfaceKHR res=0 surface=0x... on subWin ...
   [CAMetalLayer] pid=... vkGetPhysicalDeviceSurfaceSupportKHR res=0 supported=1 ...
   [CAMetalLayer] pid=... vkCreateSwapchainKHR res=0 swapchain=0x... extent=...
   [CAMetalLayer] pid=... Swapchain active on subWin ...
   ```
   *(If `subWin` fails under specific compositors, verify fallback to `topLevelWin` and unmapping of the subwindow).*
4. **Continuous Frame Presentation**:
   ```text
   [CAMetalLayer] pid=... presentDirectVulkan frame=1 drawable=... acqRes=0 imgIdx=... subRes=0 fenceRes=0 presRes=0
   ```
   Verify that `presRes == 0` (`VK_SUCCESS`) and that visual output renders smoothly on screen.

---

## 6. Performance Diagnosis and Optimization Roadmap

Visual presentation operates reliably. However, measured framerates currently average ~60 FPS (compared to 200~240 FPS on bare-metal Windows on the same RTX 4060 hardware).

### Identified Bottlenecks:
1. **Synchronous CPU Fence Wait**:
   - `vkWaitForFences` is invoked synchronously on the CPU render thread immediately following `vkQueueSubmit` in `presentDirectVulkan`.
   - Because GPU-to-display synchronization is already managed by `_vkRenderCompleteSemaphore`, this CPU wait serializes the pipeline, forcing the CPU to idle until the GPU completes its blit.
2. **Single-Flight Frame Pipeline**:
   - Using a single command buffer and fence limits concurrency. Implementing a ring buffer of 2 to 3 in-flight frames allows the CPU to record frame $N+1$ while the GPU executes frame $N$.
3. **Pipeline Stage Scope**:
   - Memory barriers currently specify `VK_PIPELINE_STAGE_ALL_COMMANDS_BIT`. Narrowing barriers to `VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT` -> `VK_PIPELINE_STAGE_TRANSFER_BIT` prevents pipeline drainage stalls.
4. **Presentation Mode**:
   - Prioritizing `VK_PRESENT_MODE_IMMEDIATE_KHR` or `VK_PRESENT_MODE_MAILBOX_KHR` unlocks unconstrained low-latency rendering.
