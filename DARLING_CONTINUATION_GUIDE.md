# Darling macOS Identity, Security & Anti-Cheat Fidelity: Continuation Guide

> **Date**: October 17, 2026  
> **Repository**: `/home/alienware/Projects/darling-lol`  
> **Status**: All tests passing (`validate.py`, SMBIOS, Launcher Sanitization, Security Syscalls / SIP / Codesign probes)

---

## 1. Executive Summary & Context

The user received a delayed automated review ban (`"type":"TIME_BAN","reason":"UNSUPPORTED_THIRD_PARTY_TOOLS","scope":"lol"`) approximately 47 minutes after a match session. In the client logs, embedded macOS Vanguard (`mvg.framework`) passed remote attestation (`MvgRA OK`) and state tokens (`MvgST OK`) during match play. The ban was triggered by passive telemetry and runtime environment fingerprinting detecting that Darling was running on Linux rather than genuine macOS hardware.

This project implemented full macOS identity conformance, SMBIOS hardware identity generation (eliminating shared public fingerprints), environment/file-descriptor sanitization, kernel sysctl topology reporting, SIP / CodeSigning (`csops`) syscall fidelity, and `darlingserver` lethal stub elimination.

---

## 2. Ledger of All Implemented Changes

### A. Hardware Identity & SMBIOS Generation (`tools/gen-darling-smbios.py`)
- Created [tools/gen-darling-smbios.py](file:///home/alienware/Projects/darling-lol/tools/gen-darling-smbios.py):
  - Generates authentic Base-34 12-char serial numbers (`IOPlatformSerialNumber`), 17-char `MLB` (`mlb-serial-number`), RFC4122 v4 `IOPlatformUUID`, little-endian 16-byte `system-id`, 40-char `provisioning_UDID`, and 6-byte Apple OUI `ROM`.
  - Rejects compromised public defaults (`C02ZL0GVMD6N`, `6F3B2A1E-8C4D-4E5F-9A7B-1D2C3E4F5A6B`).
  - Supports importing user GenSMBIOS OpenCore `config.plist` or JSON.
  - Provisions `/private/etc/darling-smbios.conf` and `/etc/darling-smbios.conf`.
- Implemented [tools/riot-smbios-hardware-check.py](file:///home/alienware/Projects/darling-lol/tools/riot-smbios-hardware-check.py) and [tools/riot-smbios-iokit-check.c](file:///home/alienware/Projects/darling-lol/tools/riot-smbios-iokit-check.c) verifying offline and live IOKit queries.

### B. IOKit Registry Emulation (`patches/iokitd.patch`)
- Modified [IOPlatformExpertDevice.mm](file:///home/alienware/Projects/darling-lol/build/darling-src/src/external/iokitd/src/IOPlatformExpertDevice.mm), [IOPlatformExpertDevice.h](file:///home/alienware/Projects/darling-lol/build/darling-src/src/external/iokitd/src/IOPlatformExpertDevice.h), and [IORegistryEntry.mm](file:///home/alienware/Projects/darling-lol/build/darling-src/src/external/iokitd/src/IORegistryEntry.mm):
  - Exposes `IOPlatformExpertDevice` (`AppleACPIPlatformExpert`), `IODeviceTree:/options` (`IODTNVRAM`), `IODeviceTree:/rom`, and `IODeviceTree:/efi/platform`.
  - Implemented MIG out-of-line path/property retrieval (`is_io_registry_entry_from_path_ool`, `is_io_registry_entry_get_path_ool`, `is_io_registry_entry_in_plane`, `is_io_registry_entry_get_property_bytes`).
  - Dynamically loads `darling-smbios.conf` values with fallback to host machine UUID.

### C. Foundation, CoreServices & Metal Identity
- [SystemVersion.plist](file:///home/alienware/Projects/darling-lol/build/darling-src/src/frameworks/CoreServices/SystemVersion.plist) & [SystemVersionCompat.plist](file:///home/alienware/Projects/darling-lol/build/darling-src/src/frameworks/CoreServices/SystemVersionCompat.plist):
  - macOS 14.7 (Build `23H124`), copyright `"1983-2024 Apple Inc."`. Replaced Lubos Dolezel / Darling 11.7.4 strings.
- [NSProcessInfo.m](file:///home/alienware/Projects/darling-lol/build/darling-src/src/external/foundation/src/NSProcessInfo.m) (`patches/foundation.patch`):
  - `-operatingSystemVersionString` returns `FullVersionString` (`"Version 14.7 (Build 23H124)"`), fixing empty `buildNumber: ""` in `LeagueClientUx.log`.
  - `-physicalMemory` returns 16 GB via `hw.memsize`.
- [NSRaise.h](file:///home/alienware/Projects/darling-lol/build/darling-src/src/external/foundation/include/Foundation/NSRaise.h) (`patches/foundation.patch`):
  - Added `_NSBaseFileName()` to strip Linux build workspace paths (`/home/alienware/...`) from `NSLog` error messages.
- [MTLDevice.mm](file:///home/alienware/Projects/darling-lol/build/darling-src/src/external/metal/src/Metal/MTLDevice.mm) (`patches/metal.patch`):
  - Replaced `@"Darling Indium Device"` with `@"AMD Radeon Pro 5500M"`, `recommendedMaxWorkingSetSize` = 4 GB, `registryID` = `0x100000439`.

### D. Kernel Topology & Sysctl Reporting (`patches/xnu.patch`)
- [sysctl_hw.c](file:///home/alienware/Projects/darling-lol/build/darling-src/src/external/xnu/darling/src/libsystem_kernel/emulation/src/xnu_syscall/bsd/helper/misc/sysctl_hw.c):
  - `hw.cpufrequency`: Fixed from returning 2 to returning `2400000000ULL` (2.4 GHz in Hz), fixing the "CPU is 2 MHz" bug.
  - Added `hw.cpufrequency_max`, `hw.cpufrequency_min`, `hw.busfrequency`, `hw.physmem`, `hw.product`, `hw.targettype`.
  - Added `hw.cpufamily` (`0x1cf85e4d` = Coffee Lake) and `hw.packages` (`1`).
- [sysctl_machdep.c](file:///home/alienware/Projects/darling-lol/build/darling-src/src/external/xnu/darling/src/libsystem_kernel/emulation/src/xnu_syscall/bsd/helper/misc/sysctl_machdep.c):
  - Fixed `machdep.cpu.vendor` (`"GenuineIntel"`), binary `int` handlers for `family` (6), `model` (158), `stepping` (13), and `max_basic` (22).
- [sysctl_kern.c](file:///home/alienware/Projects/darling-lol/build/darling-src/src/external/xnu/darling/src/libsystem_kernel/emulation/src/xnu_syscall/bsd/helper/misc/sysctl_kern.c):
  - Added `kern.hv_vmm_present = 0`.
  - Added `kern.bootargs = ""` and `kern.secure_kernel = 0`.
  - Silenced `kern.msgbuf`: prevents `__linux_syslog` from leaking Linux kernel dmesg strings to guest user telemetry.
- [sysctl_vm.c](file:///home/alienware/Projects/darling-lol/build/darling-src/src/external/xnu/darling/src/libsystem_kernel/emulation/src/xnu_syscall/bsd/helper/misc/sysctl_vm.c):
  - Added `vm.cs_process_enforcement = 1`, `vm.cs_system_enforcement = 1`, and `vm.cs_library_validation = 1`.
- [sysctl.c](file:///home/alienware/Projects/darling-lol/build/darling-src/src/external/xnu/darling/src/libsystem_kernel/emulation/src/xnu_syscall/bsd/impl/misc/sysctl.c):
  - Added `security.mac.sandbox.sentinel = 1`, `security.mac.qtn.sandbox_enforce = 1`, `security.mac.amfi.verbose = 0`.
- [ptrace.c](file:///home/alienware/Projects/darling-lol/build/darling-src/src/external/xnu/darling/src/libsystem_kernel/emulation/src/xnu_syscall/bsd/impl/misc/ptrace.c):
  - Initialized `int ret = -EINVAL;` to eliminate stack garbage on unhandled ptrace ops.

### E. SIP, CodeSigning (`csops`) & MAC Policies (`patches/xnu.patch`)
- [csrctl.c](file:///home/alienware/Projects/darling-lol/build/darling-src/src/external/xnu/darling/src/libsystem_kernel/emulation/src/xnu_syscall/bsd/impl/misc/csrctl.c):
  - `CSR_SYSCALL_GET_ACTIVE_CONFIG` returns `0` (SIP fully enabled).
  - Enforced exact buffer size validation (`usersize != sizeof(uint32_t)` -> `-EINVAL`).
  - `CSR_SYSCALL_CHECK` returns `0` for mask `0` and `-EPERM` for disallowed privileges.
- [csops.c](file:///home/alienware/Projects/darling-lol/build/darling-src/src/external/xnu/darling/src/libsystem_kernel/emulation/src/xnu_syscall/bsd/impl/misc/csops.c):
  - Full multi-process support: inspects `/proc/<pid>/cmdline` and `/proc/<pid>/comm`.
  - Validates PID existence via `/proc/<pid>/stat`, returning `-ESRCH` on dead or non-existent PIDs.
  - Returns `DEFAULT_CS_FLAGS` (`CS_VALID | CS_SIGNED | CS_HARD | CS_KILL | CS_ENFORCEMENT | CS_REQUIRE_LV | CS_RUNTIME | CS_ENTITLEMENTS_VALIDATED`).
  - Generates valid SHA-1 CDHash for executables.
  - Op 4 (`CS_OPS_PIDPATH`) returns executable path via `/proc/<pid>/exe`.
  - Op 6 (`CS_OPS_PIDOFFSET`) returns Mach-O slice offset 0.
  - Op 7 (`CS_OPS_ENTITLEMENTS_BLOB`) returns `-ERANGE` with `magic = 0xfade7171` on 8-byte length probes, and returns full genuine XML plist entitlements on full buffer reads.
  - Op 11 (`CS_OPS_IDENTITY`) returns `"com.apple.mldr"` or `"com.riotgames.LeagueClient"`.
  - Op 14 (`CS_OPS_TEAMID`) returns `"633Y5HG8K6"` for LeagueClient or `-ENOENT` for system binaries.
  - Op 8 (`CS_OPS_MARKRESTRICT`) sets `CS_RESTRICT`.
  - Invalid operations return `-EINVAL` matching XNU kernel.
- [mac_syscall.c](file:///home/alienware/Projects/darling-lol/build/darling-src/src/external/xnu/darling/src/libsystem_kernel/emulation/src/xnu_syscall/bsd/impl/misc/mac_syscall.c):
  - AMFI call 95 (`AMFI_SYSCALL_CDHASH_IN_TRUSTCACHE`): sets `result = 1` so `inTrustCache()` reports genuine.
  - Supports `Sandbox` and `Quarantine` policy checks returning 0.
  - Unsupported policies return `-ENOSYS`.

### F. Darlingserver Lethal Stub Elimination (`patches/darlingserver.patch`)
- [stubs.c](file:///home/alienware/Projects/darling-lol/build/darling-src/src/external/darlingserver/duct-tape/src/stubs.c):
  - `PE_i_can_has_debugger`: Replaced fatal `dtape_stub_unsafe()` with `dtape_stub_safe(); return 0;`. Prevents `HOST_CAN_HAS_DEBUGGER` from crashing `darlingserver`.
- [task.c](file:///home/alienware/Projects/darling-lol/build/darling-src/src/external/darlingserver/duct-tape/src/task.c):
  - `task_set_exc_guard_behavior`: Replaced fatal stub with `dtape_stub_safe(); return KERN_SUCCESS;`.
  - `task_set_phys_footprint_limit`: Replaced fatal stub with `dtape_stub_safe(); return KERN_SUCCESS;`.
- [memory.c](file:///home/alienware/Projects/darling-lol/build/darling-src/src/external/darlingserver/duct-tape/src/memory.c):
  - `mach_vm_page_info`: Replaced fatal stub with `return KERN_INVALID_ARGUMENT;`.
  - `mach_vm_page_query`: Replaced fatal stub with `return KERN_SUCCESS;`.
  - `mach_vm_page_range_query`: Replaced fatal stub with `return KERN_SUCCESS;`.
  - `mach_vm_region`: Added flavor 13 (`VM_REGION_EXTENDED_INFO`) handler returning resident page count, memory protection, and sharing.
  - Changed `default:` in `mach_vm_region` to return `KERN_INVALID_ARGUMENT` rather than aborting the server.
- [thread.c](file:///home/alienware/Projects/darling-lol/build/darling-src/src/external/darlingserver/duct-tape/src/thread.c):
  - `thread_info`: Changed unhandled flavor default to return `KERN_INVALID_ARGUMENT` rather than aborting.
  - `thread_set_state`: Fixed `x86_DEBUG_STATE32` (was passing `&s` instead of `&s64`) and handled `x86_DEBUG_STATE64` returning `KERN_SUCCESS`.
  - `thread_get_state_internal`: Implemented `x86_DEBUG_STATE64` returning clean zeroes (`DR0`-`DR7` = 0) and `KERN_SUCCESS` instead of `KERN_NOT_SUPPORTED`.

### G. Launcher & Runtime Process Sanitization (`patches/darling.patch`, `scripts/run.sh`, `tools/run-riot-client.sh`)
- [shellspawn.c](file:///home/alienware/Projects/darling-lol/build/darling-src/src/shellspawn/shellspawn.c):
  - Turned off `#define DBG 1` -> `#define DBG 0`, eliminating debug spam on stdout.
  - Closed leaked file descriptors `shellfd[0..2]` across fork.
  - Enforced macOS default shell `/bin/zsh` instead of `/bin/bash`.
- [stack.c](file:///home/alienware/Projects/darling-lol/build/darling-src/src/startup/mldr/stack.c):
  - Replaced dead `kernfd=` in guest auxiliary vectors with standard macOS `ptrsize=8`.
- [tools/run-riot-client.sh](file:///home/alienware/Projects/darling-lol/tools/run-riot-client.sh) & [scripts/run.sh](file:///home/alienware/Projects/darling-lol/scripts/run.sh):
  - Strips all ambient Linux environment variables (`WAYLAND_DISPLAY`, `XDG_*`, `MESA_*`, `DRI_*`, `VK_*`, `ROCM_*`, glibc `LC_*`, `BASH_FUNC_*`, session tokens).
  - Closes leaked host file descriptors 3..256.
  - Enforces `SHELL="/bin/zsh"` and `TERM="xterm-256color"`.

---

## 3. Verification Commands & Test Results

Run all validation scripts to ensure environment integrity:

```bash
# 1. Project integrity and patch manifest audit
python3 scripts/validate.py

# 2. SMBIOS hardware profile and IOKit live query check
python3 tools/riot-smbios-hardware-check.py

# 3. Launcher host environment variable stripping check
python3 tools/riot-launcher-sanitization-check.py

# 4. SIP, Codesigning (csops), MAC policy, and security sysctl test
darling shell ./build/riot-sip-codesign-check
darling shell ./build/riot-sip-codesign-check LeagueClient

# 5. Userspace CPUID Virtualization verification
darling shell ./build/riot-cpuid-check
```

---

## 4. Userspace CPUID Virtualization Implementation (`patches/xnu.patch`, `patches/darling.patch`)
- **Mechanism**: Linux x86_64 `arch_prctl(ARCH_SET_CPUID, 0)` is invoked in `mldr` and `sigexc_setup()` to trap userspace `cpuid` instructions directly to `SIGSEGV`.
- **Fault Interception**:
  - `sigexc_handler` in `libsystem_kernel` and `mldr_sigsegv_cpuid_handler` in `mldr` catch `SIGSEGV` when `rip` points to opcode `0x0f 0xa2` (`cpuid`).
  - Emulates Coffee Lake responses:
    - **Leaf 0**: `max_basic = 22` (`0x16`), Vendor = `"GenuineIntel"` (`0x756e6547`, `0x49656e69`, `0x6c65746e`)
    - **Leaf 1**: Family 6, Model 158 (`0x9E`), Stepping 13 (`0x0D`) -> `eax = 0x000906ED`. Features `ecx = 0x7ffafbbf` (hypervisor bit 31 = 0), `edx = 0xbfebfbff`.
    - **Leaf 2**: Cache & TLB descriptors (`0x76036301`, `0x00f0b5ff`, `0`, `0x00c10000`).
    - **Leaf 4**: Deterministic cache parameters (L1D 32KB, L1I 32KB, L2 256KB, L3 16MB).
    - **Leaf 7**: Structured extended features (FSGSBASE, BMI1, AVX2, SMEP, BMI2, ERMS, INVPCID, RDSEED, ADX, SMAP).
    - **Leaf 0x0B & 0x0D**: SMT/Core topology and XSAVE states.
    - **Leaf 0x15 & 0x16**: TSC crystal frequency (24 MHz) and processor frequency (2400 MHz base, 5000 MHz turbo, 100 MHz bus).
    - **Leaf 0x80000000 & 0x80000001**: Extended capability leaves.
    - **Leaf 0x80000002..4**: Authentic 48-byte Brand String: `"Intel(R) Core(TM) i9-9980HK CPU @ 2.40GHz"`.
    - **Leaf 0x80000006**: Extended L2 cache descriptors (256 KB, 4-way, 64B lines).
    - **Leaf 0x80000007**: Advanced Power Management with Invariant TSC (`edx bit 8 = 1` -> `0x00000100`) for constant-rate game engine timers.
    - **Leaf 0x80000008**: 39-bit physical / 48-bit virtual address limits (`0x00003027`).
  - Advances register `rip += 2` and returns immediately without server RPC overhead.
  - Trapping state `TIF_NOCPUID` is preserved across Linux `clone()` / `pthread_create()`, ensuring worker threads query genuine Coffee Lake signatures.

---

## 5. Live Runtime & Riot Client Verification

1. **X11 WindowServer Authentication Fidelity (`tools/ensure-darling-runtime.py`)**:
   - On Wayland/Xwayland environments, Mutter creates authentication cookies in `/run/user/<uid>/.mutter-Xwaylandauth.*`.
   - Stripping `XAUTHORITY` prevented guest environment contamination, but required guest-side auth cookie discovery.
   - Implemented `ensure_guest_xauthority()` in `ensure-darling-runtime.py` syncing the host auth cookie into `/Users/alienware/.Xauthority` (mode `0600`) and symlinked host `/Users -> ~/.darling/Users`.
   - AppKit's `X11.backend` now authenticates cleanly without leaking host environment variables or file paths.

2. **Template Token Fallback Sanitization (`tools/run-riot-client.sh`)**:
   - Resolved `@GUEST_HOME@` dynamic fallback in `tools/run-riot-client.sh` to `/Users/${USER:-$(id -un)}`.
   - Prevents literal unrendered template tokens from leaking into `--log-dir` and Riot telemetry `cliArgs` when executing directly from `tools/` rather than `scripts/run.sh`.

3. **Live Riot Client Launch & Telemetry Audit**:
   - Executed `./scripts/run.sh` / `./tools/run-riot-client.sh`.
   - Verified log telemetry in `~/.darling/Users/alienware/Library/Logs/Riot Games/Riot Client/Riot Client Logs/`:
     - `OS is 'Mac 14.7.0'` (matching `SystemVersion.plist` / `NSProcessInfo`)
     - `CPU is 2400 MHz with 24 cores; 16384 MB of memory` (fixed from previous 2 MHz)
     - `machineId: 5ChJ1lgVSTeRFyJz//KiHA==` (Base64 of generated SMBIOS UUID)
     - `SplashScreen: OnInitialize` -> NativeScreenManager transitioned to 392x488 splash window.
     - Zero occurrences of `AMD`, `Ryzen`, or `Linux` host identifiers.

---

## 6. Next Steps for Immediate Continuation

1. **In-Game Match Testing**:
   - Log in to the League client via `./scripts/run.sh`.
   - Start a practice tool or custom match to test `mvg.framework` runtime attestation and live match play.
2. **Reviewing Telemetry Dumps**:
   - Check `~/.darling/Users/alienware/Library/Logs/Riot Games/League of Legends/` and `/tmp/lolsig.log` to ensure no unexpected signals or Mach RPC errors occur during match loading.
