"""Exercise the patched per-context CGL swap interval without a GPU."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import test_runtime_compatibility as sources


@unittest.skipUnless(shutil.which('c++'), 'C++ compiler required')
class MetalVSyncChecks(unittest.TestCase):
    patched = sources.CompatibilityChecks.patched

    def test_explicit_vsync_is_scoped_to_each_cgl_context(self):
        source = self.patched('darling', 'src/frameworks/OpenGL/OpenGL.c')
        methods = '\n'.join(sources.function(source, name) for name in ('CGLFlushDrawable', 'CGLSetParameter'))
        fixture = r'''
#include <cassert>
#include <cstdio>
using GLint=int;
using CGLError=int;
using CGLContextParameter=int;
using EGLBoolean=int;
constexpr int kCGLNoError=0, kCGLBadContext=1, kCGLBadState=2, kCGLBadAddress=3, kCGLBadValue=4;
constexpr int kCGLCPSwapInterval=1;
struct Context { int egl_display=1, egl_surface=1, swap_interval=1, swap_interval_requested=0; };
using CGLContextObj=Context*;
static Context* current;
static int display=1, applied=-1;
static bool fail=false;
static int swapInterval(int, int value) { if(fail) return 0; applied=value; return 1; }
static auto p_eglSwapInterval=swapInterval;
static int p_eglSwapBuffers(int,int) { return 1; }
static Context* CGLGetCurrentContext() { return current; }
''' + methods + r'''
int main() {
    Context a, b;
    current=&a;
    int interval=1;
    assert(CGLSetParameter(&a,kCGLCPSwapInterval,&interval)==0 && applied==1);
    CGLFlushDrawable(&a); assert(applied==1);
    current=&b;
    CGLFlushDrawable(&b); assert(applied==0); // Another window retains its default.
    current=&a;
    interval=0;
    assert(CGLSetParameter(&a,kCGLCPSwapInterval,&interval)==0 && applied==0);
    interval=1;
    assert(CGLSetParameter(&a,kCGLCPSwapInterval,&interval)==0 && applied==1);
    current=&b; fail=true;
    assert(CGLSetParameter(&b,kCGLCPSwapInterval,&interval)==kCGLBadValue);
    assert(!b.swap_interval_requested); // Failed requests must not change policy.
    fail=false; CGLFlushDrawable(&b); assert(applied==0);
    assert(CGLFlushDrawable(nullptr)==kCGLBadContext);
}
'''
        self.run_cpp(fixture)

    def run_cpp(self, fixture):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path/'check.cpp').write_text(fixture)
            result = subprocess.run(['c++', '-std=c++17', str(path/'check.cpp'), '-o', str(path/'check')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(path/'check')], check=True, timeout=10)
