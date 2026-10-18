# VibeDarling merge

darling-lol's patches previously applied to upstream Darling (`darlinghq/darling`
`60ba801decee`). They now apply to the [VibeDarling](https://github.com/VibeDarling/darling)
fork at `1d451b15ffc0`, and every component pin in `upstream/manifest.json` is the
revision that VibeDarling's superproject records. Every previous darling-lol pin is
an ancestor of the corresponding VibeDarling revision, so this is a rebase of the
darling-lol patches onto VibeDarling, not a reverse merge.

The branch also contains PR #48 (truthful csops/csrctl/AMFI responses). Its xnu
changes merged without conflicts against VibeDarling, whose csops.c and csrctl.c
are unchanged from upstream.

## How conflicts were resolved

For each component, the darling-lol patch was committed on its old pin and
cherry-picked onto the VibeDarling revision. 13 components applied cleanly and 4
pins were already identical. The other 14 components had about 455 conflicting
hunks between them. The rules used to resolve them:

- When both sides added independent things (functions, ivars, declarations,
  sysctls), both were kept and duplicates were removed.
- When both sides fixed the same bug, the more complete fix was kept.
- When both sides reimplemented the same subsystem in incompatible ways, the
  darling-lol version was kept if League or the Riot Client depends on it and it
  has been tested in-game: Metal/indium rendering, presentation, X11 windows and
  input, display links, audio, launcher helpers. Otherwise the VibeDarling
  version was kept.

The sections below list every place where one side's implementation was dropped
in favour of the other. Anything not listed was kept from both sides.

Two components no longer need a darling-lol patch: VibeDarling already contains
the darling-lol change for libnotify (the notifyd launchd plist) and for
libpthread (`pthread_yield_np`).

## Dropped from VibeDarling (darling-lol kept)

### xnu (libsystem_kernel)
- The emulated OS version stays Darwin 23.6.0 / macOS 14.7. VibeDarling's Darwin
  25.0.0 / macOS 26.0 and its `DARLING_EMULATED_OS_PRODUCT_VERSION` cache
  variable were dropped.
- `workq_kernreturn.c` keeps darling-lol's `emulation_mutex` and parked-node
  allocation; VibeDarling's `libsimple_lock` conversion of that file was dropped.
- `kern.boottime` keeps darling-lol's once-per-process caching.

### Metal
- For classes both sides implemented, darling-lol's version was kept: blit
  encoder, depth/stencil descriptors and state, sampler descriptor and state,
  texture descriptor, vertex descriptor, and the bulk of `MTLDevice.mm`.
  VibeDarling's `MTLSamplerState.mm` is no longer built. Its
  `MTLSamplerDescriptorInternal.h` and `MTLTextureDescriptorInternal.h` are
  unused.
- `MTLDevice`: VibeDarling's indium-backed `maxBufferLength` and
  `recommendedMaxWorkingSetSize`, `supportsFamily:` (Apple1 only) and
  `supportsTextureSampleCount:` (1 only) were dropped for darling-lol's answers.
  VibeDarling's `newCommandBuffer`, `implicitCommandQueue`,
  `supportsShaderBarycentricCoordinates` and `argumentBuffersSupport` were added
  on top.
- VibeDarling's MSL source compiler hook (`newLibraryWithSource:options:error:`
  through mslc, and `MTLMSLReflection.mm`) is not wired in. It needs the indium
  reflection API, and darling-lol never had this selector. The Riot Client's ANGLE
  works without it, and adding it could move ANGLE onto an untested Metal shader
  path. The mslc library is still built.
- `-[MTLCommandBuffer waitUntilScheduled]` waits for completion, because
  darling-lol's indium does not report scheduling separately.
- VibeDarling's encoder methods that read `MTLSamplerStateInternal.state` use
  darling-lol's `MTLSamplerGetIndium()`.

### indium
- indium is darling-lol's tree in full. The manifest pins VibeDarling's indium
  revision, so the patch reverts VibeDarling's indium changes back to darling-lol's
  version. The two forks had restructured the same encoder, render-pass,
  texture-upload and AIR-translation code. Merging them hunk by hunk left
  VibeDarling's MSAA-resolve paths interleaved with darling-lol's deferred
  encoder, and VibeDarling's SPIR-V `Builder` sizes `float3` as 12 bytes where
  darling-lol's translator assumes AIR's 16. Either can misrender silently, and
  this is the code League is played on.
- VibeDarling indium work this drops:
  - MSAA render passes and resolve attachments, and colour-attachment validation
  - AIR translator fixes: allocation-size GEP scaling, `packed_T3` buffers,
    opaque-pointer diagnostics, integer constant widths, texture arrays,
    single position outputs
  - SPIR-V `SpecConstantTrue/False` and `SConvert`, and vector layout derived
    by the builder
  - catching translation exceptions inside `translate()`
  - libraries from SPIR-V plus reflection (`newLibrary(spirv, length, reflection)`,
    `BindingDescriptor` and related types)
  - `Device::maxBufferLength` and `recommendedMaxWorkingSetSize` from the
    Vulkan memory budget
  - `CommandBuffer::waitUntilScheduled` and the scheduled-handler split
  - `Texture::getBytes`
  - texture usage validation
  - discrete-over-integrated default device ranking
  - the null-instance guard in dynamic Vulkan resolution
  - VibeDarling's indium tests

### darling (superproject)
- CoreAudio HAL: darling-lol's PulseAudio backend (dispatch main loop,
  input/output streams, `AudioHardwareImpl`, `AUHAL`) was kept. VibeDarling's
  `pa_threaded_mainloop` rewrite (`PAThreadedMainLoop`) is no longer built, and
  its changes to those HAL files were dropped. VibeDarling's
  `AudioGetHostClockFrequency` and `AudioGetHostClockMinimumTimeDelta` were added.
- `CVDisplayLink.mm` is darling-lol's file-backed pump. VibeDarling's additional
  APIs were dropped: `CVDisplayLinkCreateWithCGDisplays`,
  `CreateWithOpenGLDisplayMask`, `GetActualOutputVideoRefreshPeriod`,
  `GetCurrentTime`, `GetOutputVideoLatency`, `GetTypeID`, `SetOutputHandler`
  and `TranslateTime`.
- `OpenGL.c` is darling-lol's dynamically loaded EGL implementation. VibeDarling's
  EGL rework was dropped: `CGLRegisterNativeDisplayForPlatform`,
  `CGLGetWindowForContext`, per-context display ownership, swap intervals and
  safer context release. Its simple `CGLGetVersion`, `CGLEnable`, `CGLDisable`,
  `CGLIsEnabled`, `CGLErrorString` and `CGLUpdateContext` were added.
- `shellspawn.c` is darling-lol's file, which has tested stream ownership.
  VibeDarling's shellspawn changes were dropped.
- mldr:
  - Native host threads get no RPC socket and report EPIPE (darling-lol, needed
    by the resize-signal bridge). VibeDarling's per-thread socket allocation for
    them was dropped.
  - The socket bitmap is protected across fork by darling-lol's
    `pthread_atfork` handlers. VibeDarling's manual locking in `native_fork` was
    removed, because the two together would deadlock.
  - darling-lol's `F_DUPFD` socket placement was kept. VibeDarling's `dup2`
    fallback was dropped.
- The x86 commpage CPU capabilities are darling-lol's (XCR0-aware).
  VibeDarling's arm64 capabilities were kept.
- `ODSession.m`: darling-lol's local-directory session.

### cocotron
- `X11Window.m` and `X11Display.m` are darling-lol's files: multi-monitor root
  mapping, League game-window focus and fullscreen, relative mouse, remote
  frames and alpha visuals. VibeDarling's changes in them were dropped: HiDPI
  logical/device pixel scaling, `X11GlobalMenu` registration, input-focus
  requests, the XIM null guard, wheel press/release pairing, warp-motion
  filtering and modifier resynchronisation. Their headers (`X11Display.h`, `X11Window.h`) are
  darling-lol's as well, which also drops VibeDarling's per-button, per-window
  click grouping.
- QuartzCore `CALayer.m`, `CALayerContext.m`, `CAMetalDrawable.mm`,
  `CAMetalLayer.mm`, `CARenderer.m`, `CATransaction.m` and
  `CATransactionGroup.m` are darling-lol's (the presentation path), and
  VibeDarling's changes in them were dropped. `-[CALayer isOpaque]` was added
  for VibeDarling's header.
  `CAMetalDrawableInternal.h` follows them, so VibeDarling's host-visible
  drawable readback (the copy into the layer's GL texture) and drawable
  `getBytes` were dropped.
- `CGDirectDisplay.m`: darling-lol's display-ID mapping and the zero-size
  fallback for League's camera were kept. VibeDarling's device-pixel
  `CGDisplayPixelsWide/High` were dropped. `CGDisplayRotation` returns `double`,
  as in Apple's ABI.
- AppKit:
  - `NSDisplay`'s event queue and `NSApplication`'s last-window termination
    (needed by the Riot launcher splash) are darling-lol's.
  - `NSScreen` backing scale, colour space and screen number are darling-lol's.
  - `NSWindow` titlebar and standard window buttons are darling-lol's.
  - `NSBitmapImageRep` byte order is darling-lol's.
  - `NSView` layer-context creation is darling-lol's.
  - `NSWorkspaceOpenConfiguration` is darling-lol's copying implementation;
    VibeDarling's singleton version was dropped.
  - VibeDarling's simpler `-[NSWorkspace openURL:]` was dropped for
    darling-lol's LaunchServices call.
- CoreText: darling-lol's `normalizedFont` (NSFont to CTFont bridging for
  Chromium), real fontconfig enumeration in
  `CTFontDescriptorCreateMatchingFontDescriptors` and
  `CTFontManagerCopyAvailableFontFamilyNames`, embedded font-data descriptors
  and `CTFontCopyLocalizedName`/`CTFontDescriptorCopyLocalizedAttribute` were
  kept. VibeDarling's fixed family list and its descriptor-returns-itself
  matching were dropped.

### iokitd
- `IOPlatformExpertDevice` keeps darling-lol's per-host UUID and serial and the
  `/private/etc/darling-platform.plist` overrides. VibeDarling's fixed zero UUID,
  serial `C02SG0000000` and fixed clock/bus/timebase frequency properties were
  dropped. VibeDarling's extra `IOPlatformExpert` class match was kept.

### Others
- Libinfo's resolver keeps darling-lol's per-query state with the opt-in
  `RCLOL_CDN_IPV4_ONLY` filter.
- darlingserver's `thread_unblock` keeps darling-lol's version, which also clears
  `TH_WAIT`.

## Dropped from darling-lol (VibeDarling kept)

- cfnetwork: VibeDarling's libcurl-based `NSURLSession` (`NSCFURLSession.h/.m`,
  `NSURLSession.m`) replaces the old NSURLConnection-backed one, together with
  darling-lol's fixes to it (shared-session preservation, invalidation,
  delegate-queue completions). VibeDarling's implementation covers those
  behaviours. darling-lol's CFHost cancellation fix is kept.
- xnu:
  - `ulock_wait2` is VibeDarling's (64-bit and shared variants). darling-lol's
    version, which bounded cancellable waits to 50 ms because darlingserver
    lacks markcancel, was dropped.
  - xattr is VibeDarling's implementation. darling-lol's
    `conversion/xattr/name.h` and its xattr changes were dropped.
  - `file_handle.c` and `audit_addr.c` use VibeDarling's `libsimple_lock`
    instead of darling-lol's `emulation_mutex`.
  - `accept` (NULL address), `recvfrom` flags, sysctl string lengths,
    `sysctl_net` interface flags, `psynch_cvwait` errno and the
    `machdep.cpu.brand_string` handler are VibeDarling's equivalents.
- libkqueue: VibeDarling's read filter (no descriptor duplication), canary
  diagnostics and map bookkeeping were kept. darling-lol's knote lifetime
  (`kq_waiters`) and atomic high-water `map_foreach` were kept on top.
- foundation: VibeDarling's `NSUserActivityTypeBrowsingWeb`. darling-lol's
  duplicate definition with a different value was dropped.
- cocotron:
  - `X11Pasteboard.m` is VibeDarling's ICCCM/INCR implementation. darling-lol's
    TARGETS-based rewrite was dropped; VibeDarling's already guards optional
    `pasteboardChangedOwner:`.
  - `X11Cursor.m` pixel conversion is VibeDarling's.
  - The `O2Surface` pixel-format table is VibeDarling's; darling-lol's XRGB
    writer was dropped.
  - `NSFont` weight mapping, `NSNib`, `NSResponder` touch bar, `CGContext`
    glyph drawing, `CGAffineTransform`, `NSSpeechSynthesizer` and the
    `NSColor` catalog colour conversion are VibeDarling's. The catalog
    conversion keeps darling-lol's rule that a failed conversion returns the
    original colour.
  - The FreeType text rasterizer in `O2Context_builtin_FT.m` is VibeDarling's
    glyph-cache version. darling-lol's font lock around it was dropped, because
    the cache locks internally. darling-lol's FreeType locking was reapplied to
    `CTFontGetAdvancesForGlyphs` and `CTFontCreatePathForGlyph`.
  - CoreText's font creation, metrics and name functions are VibeDarling's,
    with darling-lol's `normalizedFont` call in front.
  - `KTFont_FT.m` stays deleted, as in VibeDarling. darling-lol's
    `@synchronized` changes in it are covered by the CTFont locking above.
- iokitd: VibeDarling's position for `IOPlatformExpertDevice::registerSelf`
  (darling-lol registered it a second time).

## Duplicate implementations that merged cleanly

Both forks often added the same method or function in different places of a
file. Git merged those without a conflict, leaving two definitions, which then
failed to compile. darling-lol's copy was kept in every such case. VibeDarling's
copies of the following were removed:

- AppKit:
  - `+[NSEvent pressedMouseButtons]`
  - `-[NSImage drawInRect:]`
  - `-[NSMenuItem setToolTip:]` and `setView:`
  - `-[NSResponder otherMouseDown:/Up:/Dragged:]`
  - `NSRunningApplication`'s process lookup, `isTerminated` and
    `activateWithOptions:`
  - `-[NSSavePanel beginSheetModalForWindow:completionHandler:]`
  - `NSTextInputContext`
  - `-[NSView wantsUpdateLayer]` and the backing conversions
  - `-[NSWindow occlusionState]`, `tabbingMode` and the screen conversions
- CoreGraphics and Onyx2D:
  - the `CGEventSource` key state, idle time and counter functions
  - `-[O2Font_freetype copyTableForTag:]`
- Metal:
  - `-[MTLCommandBuffer blitCommandEncoder]` and `addScheduledHandler:`
  - the compute encoder's texture and sampler setters
  - the render encoder's texture, sampler, depth-bias, depth-stencil and
    stencil-reference setters
- Other components:
  - iokitd's `is_io_service_get_matching_service_bin`
  - OpenDirectory's `ODNode`, `ODQuery` and `ODRecord` methods
- Duplicate declarations: the `CALayer` ivars and properties keep darling-lol's
  types. Duplicates in `NSWindow`, `NSMenuItem` and `NSView` ivars and in the
  `NSEvent` enumerators were removed. `-[CALayer isGeometryFlipped]` was added
  for Apple's getter name.

## Combined code that needed fixes

- `gettimeofday`: darling-lol's vDSO fast path now also fills VibeDarling's new
  `mach_time` output.
- `-[NSFont _coreTextFont]` (used by darling-lol's CTFont bridging) returns the
  font itself. VibeDarling registers NSFont as CoreText's concrete font class, so
  the separate `_ctFont` darling-lol kept no longer exists.
- `NSOpenGLContext` uses `CGLGetWindow` again, because VibeDarling's
  `CGLGetWindowForContext` was dropped with its EGL rework. That function's
  declaration and `CGLRegisterNativeDisplayForPlatform`'s were removed from
  `CGLInternal.h`; the Wayland backend looks the latter up with `dlsym`.
- VibeDarling's X11 helpers (cursor, drag-and-drop, subwindows) call HiDPI
  methods that darling-lol's X11 classes lack. darling-lol draws at one device
  pixel per point, so `-[X11Display backingScale]` returns 1, and
  `-[X11Window deviceRect:]` and `logicalPoint:` return their input.
  `WaylandDisplay` declares the click-grouping ivars it used to inherit from
  VibeDarling's `X11Display`.
- `X11Window.h` imports `CGWindowPrivate.h`, where VibeDarling moved the
  `CGWindow` class.
- `NSWindow` handles other mouse buttons with darling-lol's per-button down
  locations. VibeDarling's single-location cases were removed as duplicate
  `case` labels.
- Removed duplicate definitions produced by clean merges:
  - syscall 544
  - `CTFontDescriptorCreateWithAttributes`
  - `CGFontCopyPostScriptName`
  - `-[O2Font copyTableTags]`
  - `CGDisplayIsBuiltin`, `CGDisplayRotation`, `CGDisplayCopyColorSpace`
  - `NSWorkspaceOpenConfiguration`
  - `-[KTFont pointSize]`
- The VibeDarling Swift submodule fetches its LFS objects from
  `VibeDarling/darling-swift`.

## Validation status

- All 29 component patches apply to the VibeDarling pins
  (`scripts/prepare.py --check-only`), and `scripts/validate.py` passes.
- The complete Darling build (`cmake --build build/darling-src/build`) succeeds
  from these patches.
- The unit tests show only the two `test_exec_guest` failures that also fail on
  `main`.
- Not yet done: installing the runtime and playing League on it. Check rendering
  (indium is darling-lol's, but Metal and QuartzCore combine both forks),
  audio, clipboard, Riot Client fonts, input and fullscreen before relying on
  this branch.
