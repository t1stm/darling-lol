Hi, this is a very vibecoded fork of [darling-lol](https://github.com/lucannez64/darling-lol). Generally this will contain mixed commits from multiple other forks of darling-lol to quickly test the changes. Ideally this shouldn't be used by anyone else but me, but I cannot stop anyone.

Implemented here:

- [darling-lol](https://github.com/lucannez64/darling-lol) (upstream `main` up to [#96](https://github.com/lucannez64/darling-lol/pull/96)) on the [darlinghq/darling](https://github.com/darlinghq/darling) base
- Truthful signing, SIP and AMFI APIs and the CPUID validation from [lucannez64#48](https://github.com/lucannez64/darling-lol/pull/48), now taken from fgeroldi's `main`
- The unmerged work on [fgeroldi/darling-lol](https://github.com/fgeroldi/darling-lol/commits/main/) `main` up to `1581867`: discrete GPU selection, direct Vulkan swapchain presentation for CAMetalLayer and its frame pacing, the dynamic display link refresh rate, Linux tray support, borderless/CSD windows, VideoToolbox and video-decode workarounds, `PROC_PIDLISTFDS`, and the lifecycle supervisor. Its `cocotron.patch` had lost three new headers, which are restored from upstream.
- Enabling `VK_KHR_xlib_surface`, without which fgeroldi's swapchain presentation cannot create a surface ([3473a47](https://github.com/t1stm/darling-lol/commit/3473a4767dd061fa575894bea957570e379a9a43))
