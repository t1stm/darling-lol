# Handover: launchd crashes at boot after the VibeDarling merge

Status as of 2026-10-18 23:45 EEST: **open**. The merged runtime is installed and
does not boot, so League cannot be started until this is fixed or rolled back.

## Resolution (2026-10-18 23:55 EEST): root cause found, fix built, not installed

- **Cause:** VibeDarling xnu `05a2056` ("mach_init: acquire TASK_BOOTSTRAP_PORT
  …", darling#1162) added a `task_get_special_port` call to `mach_init_doit()` in
  `libsyscall/mach/mach_init.c`, ahead of `_pthread_set_self(0)`.
  `task_get_special_port` is a MIG stub, so it calls `mig_get_reply_port`, which
  reads `%gs:0x10`. In dyld, `_pthread_set_self(0)` (that is,
  `_pthread_set_self_dyld`) is what installs the main thread's TSD base. Until it
  runs, GS is 0 on x86_64, and the read faults at `0x10`. On arm64 the read falls
  back to the shared zero TSD page, so it doesn't crash there. It does write the
  reply port into that shared page, which is wrong too.
  None of the elf_calls, TSD or vDSO hypotheses below turned out to be the cause.
- **Fix:** the bootstrap-port block now runs after `_pthread_set_self(0)`. The
  libsystem_kernel.dylib variant of `_pthread_set_self` is an empty stub
  (`libsyscall/wrappers/_libc_funcptr.c`), so nothing changes there. After a fork,
  `bootstrap_port` is already set, so the block is skipped. The hunk is in
  `patches/xnu.patch`, and `prepare.py --check-only` validates all 29 patches.
- **Verified:** I rebuilt `system_kernel` and `system_loader` (dyld). The
  disassembly shows `__pthread_set_self` now comes before `_task_get_special_port`.
  For an A/B test I ran the build tree's launcher against a copy of the installed
  runtime, with a short `DPREFIX`:
  - Installed (unfixed) dyld and libsystem_kernel: `segfault at 10 ip
    000000001fe90530`, the same crash as above.
  - Rebuilt dyld and libsystem_kernel: `darling shell echo hi` prints `hi` in
    about 2 s.
- **Test pitfall:** a `DPREFIX` under the long Claude scratchpad path fails with
  `darlingserver socket path is too long`, and launchd then exits 1. That
  produces the same shellspawn timeout, so keep the prefix path short.

## Where things stand

- Fork: https://github.com/t1stm/darling-lol. `main` contains PR #1 (truthful
  csops/csrctl/AMFI, from lucannez64/darling-lol#48) and PR #2 (the VibeDarling
  rebase, commit `23fd89e`).
- The merge decisions are recorded in `docs/reviews/vibedarling-merge.md`.
- Build tree: `build/darling-src` is checked out at `VibeDarling/darling@1d451b15`,
  with every submodule at VibeDarling's pin. All 29 darling-lol patches are
  applied, and the full build completes with exit 0.
- `./scripts/update.sh` ran:
  - `sudo cmake --install` finished. The installed
    `/usr/local/libexec/darling/usr/lib/system/libsystem_kernel.dylib` is
    byte-identical to the build output.
  - It needed one manual step first: `sudo rmdir
    /usr/local/libexec/darling/private/tmp`. VibeDarling installs that path as a
    symlink to `../Volumes/SystemRoot/tmp`.
  - `install-runtime.sh` then failed with `Timed out waiting for shellspawn in
    container`.
- The previous (pre-merge) runtime in `/usr/local` was overwritten. There is no
  backup of it. Only the per-user overrides are backed up by `install-runtime.sh`.

## Symptom

Every container start crashes the first guest process (`mldr` running
`/sbin/launchd`) with SIGSEGV. It reproduces on every attempt, which makes it
unlike the intermittent shellspawn timeout that VibeDarling's `CLAUDE.md`
describes:

```
$ darling shutdown            # always first: a stale server stays behind
$ darling shell echo hi
Timed out waiting for shellspawn in container

$ journalctl -k | grep segfault
mldr[2173325]: segfault at 10 ip 000000001fe90530 sp 00007fffffdffd48 error 4 in dyld[90530,1fe00000+ea000]
mldr[2174134]: segfault at 10 ip 000000001fe90530 sp 00007fffffdffd48 error 4 in dyld[90530,1fe00000+ea000]
```

`coredumpctl info` shows `SEGV_MAPERR`, command line `vchroot /home/kris/.darling
/sbin/launchd`, and `Storage: none` (no core file).

## What the evidence says

- `0x1fe90530` is the first instruction of `_mig_get_reply_port` in the
  installed dyld (`llvm-nm -n --defined-only
  /usr/local/libexec/darling/usr/lib/dyld`; dyld's `__text` starts at
  `0x1fe01000`).
- The fault address is `0x10`. `mig_get_reply_port` reads TSD slot 2
  (`__TSD_MIG_REPLY`, offset `0x10`) through `%gs`. A read of address `0x10`
  therefore means **the main thread's GS/TSD base is 0 when dyld makes its first
  Mach RPC**.
- `/tmp/lolsig.log` (darling-lol's fault reporter in `sigexc.c`) was not written,
  so the crash happens before guest signal handling is set up. That is consistent
  with a fault during dyld bootstrap.

## What was already checked

- `src/external/xnu/.../xnu_syscall/machdep/impl/tls.c`: the x86_64
  `sys_thread_set_tsd_base` is still a plain `arch_prctl(ARCH_SET_GS, ptr)`.
  Neither side changed the x86_64 path.
- Callers of `sys_thread_set_tsd_base`:
  - `other/mach/lkm.c` (the `__aarch64__`-only main-thread registration that
    VibeDarling added)
  - `src/startup/mldr/elfcalls/threads.c:247` (new threads only)
  - No x86_64 caller for the main thread was found in xnu or mldr.
- `src/startup/mldr/mldr.c` differs from VibeDarling's HEAD only in darling-lol's
  socket-bitmap fixes (fork prepare/complete, `F_DUPFD` placement, shrink fix).
- **Not yet checked (the interrupted step):** where the x86_64 main thread's TSD
  is set during dyld bootstrap, in `src/external/dyld` and in the dyld variant of
  libsystem_kernel (`VARIANT_DYLD`). Start with:
  ```
  cd build/darling-src/src/external/dyld && git grep -n "tsd_base\|set_tsd\|TSD"
  cd build/darling-src/src/external/xnu && git grep -n "thread_set_tsd_base\|__thread_set_tsd_base" -- libsyscall darling
  ```

## Hypotheses, most likely first

1. **The two forks disagree on the `struct elf_calls` layout.** mldr fills the
   table (`src/startup/mldr/elfcalls/elfcalls.h` and `.c`), and libsystem_kernel
   and dyld read it by offset. The merge appended VibeDarling's arm64 fields
   (`native_tsd_base`, `initial_native_tsd_base`, `native_fork`, …) and then
   darling-lol's `fork` member. A second copy of the struct elsewhere (in xnu's
   emulation headers, or with a size check such as `elfcalls_size_from_apple`)
   would make one side call or read the wrong slot.
   - Check: `grep -rn "struct elf_calls" build/darling-src/src` and compare the
     field order of every definition. Also check how `_elfcalls_size` is
     validated in `lkm.c`.
2. **VibeDarling moved x86_64 main-thread TSD setup to a place darling-lol's
   patch now overrides or skips.** Relevant VibeDarling commits:
   - `1315f6a74` "mldr/dyld/xnu: rewrite ARM64 TPIDRRO_EL0 …"
   - xnu `6b6071b` "Publish Darwin TSD into the native loader dedicated TLS slot"
   - xnu `06a255c` "Register the main thread's TSD base in libsystem_kernel.dylib
     on arm64"

   Check them for any x86_64 side effects. Then diff the darling-lol patch hunks
   in `lkm.c`, `tls.c`, `fork.c`, `sigexc.c` and `bsdthread_*`, which run early in
   dyld.
3. **darling-lol code now runs earlier under VibeDarling.** `mach_driver_init()`
   gained darling-lol's `__darling_vdso_clock_init()` on x86_64, and that also
   runs in the dyld variant. It calls the native loader through `_elfcalls`. If
   the table is misread (hypothesis 1), or this runs before the RPC socket and
   TSD exist, it could leave the thread in a bad state before dyld's first
   `mach_msg`.
   - Quick test: guard the call with `#ifndef VARIANT_DYLD` and rebuild
     libsystem_kernel and dyld.

## Isolating it quickly

- **Fastest bisect:** build VibeDarling without darling-lol's xnu and mldr
  changes and see whether it boots on this host. If it doesn't, the bug is
  VibeDarling's on x86_64 (it develops mainly on arm64). If it does, re-add
  darling-lol hunks file by file, starting with `lkm.c`, then `elfcalls.h`,
  `tls.c`, `fork.c` and `sigexc.c`.
- Only libsystem_kernel and dyld need rebuilding for most experiments:
  ```
  cmake --build build/darling-src/build --target system_kernel dyld
  ```
  `tools/build-riot-security-check.py` shows how to link an isolated
  libsystem_kernel without touching `/usr/local`. VibeDarling's `CLAUDE.md`
  ("Running a locally built runtime without installing it") describes
  `DESTDIR` installs with a disposable `DPREFIX`.
- To get a core file:
  - Run `ulimit -c unlimited` in the shell that starts `darling`.
  - mldr raises only the soft limit up to the hard limit, so the hard limit must
    already allow cores.
  - Check `/etc/systemd/coredump.conf`, because `Storage: none` may be set there.
- Run `darling shutdown` before every attempt; a crashed boot leaves a
  `darlingserver` and a defunct `mldr` behind.

## Rollback

There is no quick rollback. The old runtime files were overwritten, so they have
to be rebuilt:

1. In darling-lol, check out the pre-merge state (`git switch main` on the
   upstream-tracking `main`, or commit `5ed6069`).
2. Point the build tree back at upstream Darling:
   ```
   git -C build/darling-src remote set-url origin https://github.com/darlinghq/darling.git
   ```
   Then revert the current patches. They are recorded in `build/applied-patches`;
   reverse-apply each one, as the earlier switch did.
3. Check out the old pin and its submodules:
   ```
   git -C build/darling-src checkout --detach 60ba801decee7a00782f74f6be4c8ffb013f79ff
   git -C build/darling-src submodule sync --recursive
   git -C build/darling-src submodule update --init --recursive
   ```
   The Swift LFS objects for that pin come from
   `https://github.com/darlinghq/darling-swift.git/info/lfs`.
4. Run `./scripts/update.sh`: prepare, build (a near-full rebuild, which takes
   hours), install.

`build/pre-vibedarling-backup/*.diff` holds the working-tree diffs of every
component as they were before the switch.

## Housekeeping left over from the merge

- Scratch git worktrees used for the conflict resolution were registered in the
  component repositories under `build/darling-src`. Their paths are under the
  Claude scratchpad (`/tmp/claude-1000/.../scratchpad/wt`). Once that directory
  is gone, run `git worktree prune` in each component repository.
- `build/darling-src/src/external/swift` now has Git LFS hooks installed locally
  (`git lfs install --local`).
