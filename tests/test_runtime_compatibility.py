"""Compile actual patched syscall bodies with inert RPC stubs; never start a server."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def function(source, name):
    start = re.search(r'^[\w* ]+\b' + re.escape(name) + r'\([^;]*?\)\s*\{', source, re.M).start()
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end] + '\n'


@unittest.skipUnless(shutil.which('cc') and shutil.which('patch'), 'C compiler and patch required')
class CompatibilityChecks(unittest.TestCase):
    def patched(self, name, path):
        component = next(c for c in json.loads((ROOT / 'upstream/manifest.json').read_text())['components']
                         if c['patch'] == 'patches/' + name + '.patch')
        repo = ROOT / 'build/darling-src' / component['path']
        if not (repo / '.git').exists():
            self.skipTest('prepared Darling sources required')
        original = (None if path in component['new_files'] else
                    subprocess.check_output(['git', '-C', str(repo), 'show', component['revision'] + ':' + path]))
        marker = 'diff --git a/' + path + ' b/' + path + '\n'
        patch_text = (ROOT / component['patch']).read_text()
        if marker not in patch_text:
            return original.decode()
        patch = patch_text.split(marker, 1)[1].split('\ndiff --git ', 1)[0]
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / path
            target.parent.mkdir(parents=True, exist_ok=True)
            if original is not None:
                target.write_bytes(original)
            subprocess.run(['patch', '--silent', '-p1', '-d', folder], input=marker + patch + ("" if patch.endswith("\n") else "\n"),
                           text=True, check=True, capture_output=True)
            return target.read_text()

    def run_c(self, source):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / 'check.c'
            file.write_text(source)
            binary = Path(folder) / 'check'
            result = subprocess.run(['cc', '-std=c11', '-O0', str(file), '-o', str(binary)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_unsupported_mach_calls_return_errors_and_initialize_outputs(self):
        bodies = []
        for path, names in {
            'duct-tape/src/memory.c': ['mach_vm_page_info', 'mach_vm_page_query', 'mach_vm_page_range_query'],
            'duct-tape/src/task.c': ['task_set_exc_guard_behavior', 'task_set_phys_footprint_limit'],
            'duct-tape/src/stubs.c': ['PE_i_can_has_debugger'],
        }.items():
            source = self.patched('darlingserver', path)
            bodies.extend(function(source, name) for name in names)
        self.run_c('''
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <assert.h>
typedef int kern_return_t;
typedef void *vm_map_t;
typedef void *vm_page_info_t;
typedef void *task_t;
typedef uint64_t mach_vm_address_t;
typedef uint64_t mach_vm_offset_t;
typedef uint64_t mach_vm_size_t;
typedef unsigned mach_msg_type_number_t;
typedef int vm_page_info_flavor_t;
typedef unsigned task_exc_guard_behavior_t;
#define KERN_NOT_SUPPORTED 46
#define dtape_stub_unsafe(...) abort()
''' + ''.join(bodies) + '''
int main(void) {
    mach_msg_type_number_t count = 123;
    assert(mach_vm_page_info(NULL, 0, 0, NULL, &count) == KERN_NOT_SUPPORTED && count == 0);
    assert(mach_vm_page_info(NULL, 0, 0, NULL, NULL) == KERN_NOT_SUPPORTED);
    int disposition = 123, refs = 123, old = 123;
    assert(mach_vm_page_query(NULL, 0, &disposition, &refs) == KERN_NOT_SUPPORTED);
    assert(disposition == 0 && refs == 0);
    assert(mach_vm_page_query(NULL, 0, NULL, NULL) == KERN_NOT_SUPPORTED);
    mach_vm_size_t rangeCount = 123;
    assert(mach_vm_page_range_query(NULL, 0, 4096, 0, &rangeCount) == KERN_NOT_SUPPORTED && rangeCount == 0);
    assert(mach_vm_page_range_query(NULL, 0, 4096, 0, NULL) == KERN_NOT_SUPPORTED);
    assert(task_set_exc_guard_behavior(NULL, 0) == KERN_NOT_SUPPORTED);
    assert(task_set_phys_footprint_limit(NULL, 100, &old) == KERN_NOT_SUPPORTED && old == 0);
    assert(task_set_phys_footprint_limit(NULL, 100, NULL) == KERN_NOT_SUPPORTED);
    uint32_t debugger = 123;
    assert(PE_i_can_has_debugger(&debugger) == 0 && debugger == 0);
    assert(PE_i_can_has_debugger(NULL) == 0);
}
''')

    def test_ptrace_unknown_request_and_existing_requests(self):
        base = 'darling/src/libsystem_kernel/emulation/'
        source = self.patched('xnu', base + 'src/xnu_syscall/bsd/impl/misc/ptrace.c')
        header = self.patched('xnu', base + 'include/xnu_syscall/bsd/impl/misc/ptrace.h')
        self.run_c('''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <signal.h>
#include <stddef.h>
#include <stdlib.h>
#include <unistd.h>
#define __simple_printf(...) ((void)0)
#define __simple_kprintf(...) ((void)0)
#define __simple_abort() abort()
static int calls;
static int sys_getppid(void) { return 1; }
static int errno_linux_to_bsd(int value) { return value; }
static int dserver_rpc_set_tracer(int a, int b) { ++calls; return 0; }
static int sys_kill(int a, int b, int c) { ++calls; return 0; }
static int dserver_rpc_ptrace_sigexc(int a, bool b) { ++calls; return 0; }
static int dserver_rpc_tid_for_thread(void *a, int *b) { ++calls; *b = 1; return 0; }
static int dserver_rpc_ptrace_thupdate(int a, int b) { ++calls; return 0; }
static bool dc_cs_target_allows_debug(int pid) { return true; }
''' + header + function(source, 'sys_ptrace') + '''
int main(void) {
    for (int i = 0; i < 1000; ++i) assert(sys_ptrace(0x7fffffff, 0, NULL, 0) == -EINVAL);
    assert(calls == 0);
    assert(sys_ptrace(XNU_PT_ATTACH, 0, NULL, 0) == -ENOSYS && calls == 0);
    assert(sys_ptrace(XNU_PT_DENY_ATTACH, 0, NULL, 0) == 0 && calls == 0);
    assert(sys_ptrace(XNU_PT_PTRACE_ME, 0, NULL, 0) == 0 && calls == 1);
}
''')

    def test_proc_pidinfo_listfds_and_hw_packages(self):
        base = 'darling/src/libsystem_kernel/emulation/'
        pi_source = self.patched('xnu', base + 'src/xnu_syscall/bsd/impl/misc/proc_info.c')
        hw_source = self.patched('xnu', base + 'src/xnu_syscall/bsd/helper/misc/sysctl_hw.c')
        start = hw_source.index('\nsysctl_handler(handle_packages)') + 1
        opening = hw_source.index('{', start)
        depth = 1
        end = opening + 1
        while depth:
            depth += (hw_source[end] == '{') - (hw_source[end] == '}')
            end += 1
        handle_packages_fn = hw_source[start:end]
        self.run_c('''
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <dirent.h>
#include <sys/syscall.h>

#define BSD_O_RDONLY 0
#define BSD_O_DIRECTORY 0x100000
#define PROX_FDTYPE_VNODE 1
#define PROC_PIDLISTFDS 1
#define isdigit(c) ((c) >= '0' && (c) <= '9')

struct proc_fdinfo {
    int32_t proc_fd;
    uint32_t proc_fdtype;
};

struct bsd_dirent {
    uint64_t d_ino;
    uint64_t d_seekoff;
    uint16_t d_reclen;
    uint16_t d_namlen;
    uint8_t d_type;
    char d_name[1024];
};

static int sys_open_nocancel(const char *path, int flags, int mode) {
    return open(path, O_RDONLY | O_DIRECTORY);
}

static int close_internal(int fd) {
    return close(fd);
}

static long sys_getdirentries(int fd, char *buf, int nbytes, long *basep) {
    struct linux_dirent64 {
        uint64_t d_ino;
        int64_t d_off;
        unsigned short d_reclen;
        unsigned char d_type;
        char d_name[];
    };
    char kbuf[1024];
    long nread = syscall(SYS_getdents64, fd, kbuf, sizeof(kbuf));
    if (nread <= 0) return nread;
    int pos = 0, outpos = 0;
    while (pos < nread) {
        struct linux_dirent64 *ld = (struct linux_dirent64*)(kbuf + pos);
        struct bsd_dirent *bd = (struct bsd_dirent*)(buf + outpos);
        bd->d_ino = ld->d_ino;
        bd->d_seekoff = ld->d_off;
        bd->d_reclen = sizeof(struct bsd_dirent);
        bd->d_namlen = strlen(ld->d_name);
        bd->d_type = ld->d_type;
        strcpy(bd->d_name, ld->d_name);
        outpos += bd->d_reclen;
        pos += ld->d_reclen;
    }
    return outpos;
}

#define LINUX_SYSCALL0(nr) syscall(nr)
#define __simple_sprintf sprintf
#define __simple_atoi(s, end) atoi(s)

#define sysctl_handle_size(size) \
    if (old == NULL) { \
        *oldlen = size; \
        return 0; \
    } else if (*oldlen < size) \
        return -EINVAL; \
    else \
        *oldlen = size;

#define sysctl_handler(_hname) long _hname(const int* name, int nlen, void* old, unsigned long* oldlen, void* _new, unsigned long newlen)

''' + function(pi_source, '_proc_pidinfo_listfds') + '\n' + handle_packages_fn + '''
int main(void) {
    // 1. Test buffer discovery
    long req_bytes = _proc_pidinfo_listfds(0, NULL, 0);
    assert(req_bytes > 0);
    assert(req_bytes % sizeof(struct proc_fdinfo) == 0);
    int count = req_bytes / sizeof(struct proc_fdinfo);
    assert(count >= 3); // stdin, stdout, stderr

    // 2. Test buffer population
    struct proc_fdinfo fds[64];
    long filled_bytes = _proc_pidinfo_listfds(0, fds, sizeof(fds));
    assert(filled_bytes == req_bytes);
    for (int i = 0; i < count; ++i) {
        assert(fds[i].proc_fd >= 0);
        assert(fds[i].proc_fdtype == PROX_FDTYPE_VNODE);
    }

    // 3. Test partial buffer
    long partial = _proc_pidinfo_listfds(0, fds, sizeof(struct proc_fdinfo));
    assert(partial == sizeof(struct proc_fdinfo));
    assert(fds[0].proc_fdtype == PROX_FDTYPE_VNODE);

    // 4. Test non-existent pid
    assert(_proc_pidinfo_listfds(9999999, NULL, 0) == -ESRCH);

    // 5. Test hw.packages sysctl handler
    int val = 0;
    unsigned long len = sizeof(val);
    assert(handle_packages(NULL, 0, &val, &len, NULL, 0) == 0);
    assert(val == 1);
    assert(len == sizeof(int));

    len = 0;
    assert(handle_packages(NULL, 0, NULL, &len, NULL, 0) == 0);
    assert(len == sizeof(int));
    return 0;
}
''')

