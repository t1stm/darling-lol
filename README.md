Hi, this is a very vibecoded fork of [darling-lol](https://github.com/lucannez64/darling-lol). Generally this will contain mixed commits from multiple other forks of darling-lol to quickly test the changes. Ideally this shouldn't be used by anyone else but me, but I cannot stop anyone.

Implemented here:

- [darling-lol](https://github.com/lucannez64/darling-lol) (upstream `main` up to [#73](https://github.com/lucannez64/darling-lol/pull/73))
- [VibeDarling](https://github.com/VibeDarling/darling): the darling-lol patches rebased onto VibeDarling `1d451b15ffc0` ([t1stm#2](https://github.com/t1stm/darling-lol/pull/2))
- Truthful signing, SIP and AMFI APIs and the CPUID validation from [lucannez64#48](https://github.com/lucannez64/darling-lol/pull/48) ([t1stm#1](https://github.com/t1stm/darling-lol/pull/1))
- Fix for the x86_64 launchd crash in dyld's `mach_init` after the VibeDarling rebase ([5ffb6ac](https://github.com/t1stm/darling-lol/commit/5ffb6acd63f5547953e1fc96ace59660bbdd0d96))
- Linking the Swift re-export of CoreGraphics with lld ([389ece5](https://github.com/t1stm/darling-lol/commit/389ece56c4f225b5bd4f544d62f994361d856da9))
- The unmerged work on [fgeroldi/darling-lol](https://github.com/fgeroldi/darling-lol/commits/main/) `main` up to `d7e3b46`: discrete GPU selection, direct Vulkan swapchain presentation for CAMetalLayer, Linux tray support, borderless/CSD windows, VideoToolbox and video-decode workarounds, `PROC_PIDLISTFDS`, and the lifecycle supervisor. The `DARLING_*` to `RCLOL_*` environment rename (`ba58935`, `7128ace`) and its revert (`847d489`) are left out.
- Enabling `VK_KHR_xlib_surface`, without which fgeroldi's swapchain presentation cannot create a surface ([73bf266](https://github.com/t1stm/darling-lol/commit/73bf2669ecf4cf8493dabe90435ded878aa57e2f))
