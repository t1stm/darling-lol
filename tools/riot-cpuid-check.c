#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <pthread.h>

static inline void run_cpuid(uint32_t leaf, uint32_t subleaf,
                             uint32_t* a, uint32_t* b, uint32_t* c, uint32_t* d)
{
    __asm__ __volatile__(
        "cpuid"
        : "=a"(*a), "=b"(*b), "=c"(*c), "=d"(*d)
        : "a"(leaf), "c"(subleaf)
    );
}

static void* thread_cpuid_worker(void* arg)
{
    int* res = (int*) arg;
    uint32_t eax, ebx, ecx, edx;
    run_cpuid(0, 0, &eax, &ebx, &ecx, &edx);
    char vendor[13] = {0};
    memcpy(vendor + 0, &ebx, sizeof(uint32_t));
    memcpy(vendor + 4, &edx, sizeof(uint32_t));
    memcpy(vendor + 8, &ecx, sizeof(uint32_t));
    if (strcmp(vendor, "GenuineIntel") != 0) {
        *res = 1;
        return NULL;
    }
    run_cpuid(1, 0, &eax, &ebx, &ecx, &edx);
    uint32_t family = ((eax >> 8) & 0xF) + ((eax >> 20) & 0xFF);
    uint32_t model = ((eax >> 4) & 0xF) | (((eax >> 16) & 0xF) << 4);
    if (family != 6 || model != 158) {
        *res = 2;
        return NULL;
    }
    *res = 0;
    return NULL;
}

int main(void)
{
    uint32_t eax, ebx, ecx, edx;
    int failed = 0;

    printf("=== Testing Userspace CPUID Virtualization ===\n");

    /* 1. Leaf 0: Vendor String & Max Basic Leaf */
    run_cpuid(0, 0, &eax, &ebx, &ecx, &edx);
    char vendor[13] = {0};
    memcpy(vendor + 0, &ebx, sizeof(uint32_t));
    memcpy(vendor + 4, &edx, sizeof(uint32_t));
    memcpy(vendor + 8, &ecx, sizeof(uint32_t));

    printf("cpuid(0): max_basic=%u vendor=\"%s\"\n", eax, vendor);
    if (strcmp(vendor, "GenuineIntel") != 0) {
        printf("FAIL: Expected vendor GenuineIntel, got %s\n", vendor);
        failed++;
    } else {
        printf("PASS: Vendor is GenuineIntel\n");
    }
    if (eax < 22) {
        printf("FAIL: Expected max_basic >= 22, got %u\n", eax);
        failed++;
    } else {
        printf("PASS: Max basic leaf is %u (>= 22)\n", eax);
    }

    /* 2. Leaf 1: Family, Model, Stepping & Hypervisor Bit */
    run_cpuid(1, 0, &eax, &ebx, &ecx, &edx);
    uint32_t stepping = eax & 0xF;
    uint32_t model = ((eax >> 4) & 0xF) | (((eax >> 16) & 0xF) << 4);
    uint32_t family = ((eax >> 8) & 0xF) + ((eax >> 20) & 0xFF);
    int hypervisor = (ecx >> 31) & 1;

    printf("cpuid(1): eax=0x%08x (family=%u, model=%u, stepping=%u) hv=%d\n",
           eax, family, model, stepping, hypervisor);
    if (family != 6 || model != 158 || stepping != 13) {
        printf("FAIL: Expected Family 6, Model 158, Stepping 13 (Coffee Lake Refresh); got %u, %u, %u\n",
               family, model, stepping);
        failed++;
    } else {
        printf("PASS: Coffee Lake Refresh Signature (Family 6, Model 158, Stepping 13)\n");
    }
    if (hypervisor != 0) {
        printf("FAIL: Hypervisor bit is set (%d), expected 0 (bare-metal Mac)\n", hypervisor);
        failed++;
    } else {
        printf("PASS: Bare-metal flag confirmed (hypervisor bit = 0)\n");
    }

    /* 3. Extended Leaves 0x80000002..4: Processor Brand String */
    char brand[49] = {0};
    uint32_t brand_regs[4];
    run_cpuid(0x80000002, 0, &brand_regs[0], &brand_regs[1], &brand_regs[2], &brand_regs[3]);
    memcpy(brand + 0, brand_regs, sizeof(brand_regs));
    run_cpuid(0x80000003, 0, &brand_regs[0], &brand_regs[1], &brand_regs[2], &brand_regs[3]);
    memcpy(brand + 16, brand_regs, sizeof(brand_regs));
    run_cpuid(0x80000004, 0, &brand_regs[0], &brand_regs[1], &brand_regs[2], &brand_regs[3]);
    memcpy(brand + 32, brand_regs, sizeof(brand_regs));

    printf("cpuid(0x80000002..4): brand=\"%s\"\n", brand);
    const char* expected_brand = "Intel(R) Core(TM) i9-9980HK CPU @ 2.40GHz";
    if (strcmp(brand, expected_brand) != 0) {
        printf("FAIL: Expected brand \"%s\", got \"%s\"\n", expected_brand, brand);
        failed++;
    } else {
        printf("PASS: Brand string matches \"%s\"\n", brand);
    }

    /* 4. Leaf 0x16: Processor Frequency */
    run_cpuid(0x16, 0, &eax, &ebx, &ecx, &edx);
    printf("cpuid(0x16): base=%u MHz max=%u MHz bus=%u MHz\n", eax, ebx, ecx);
    if (eax != 2400) {
        printf("FAIL: Expected base frequency 2400 MHz, got %u\n", eax);
        failed++;
    } else {
        printf("PASS: Base frequency is 2400 MHz (2.40 GHz)\n");
    }

    /* 5. Leaf 0x80000007: Advanced Power Management (Invariant TSC) */
    run_cpuid(0x80000007, 0, &eax, &ebx, &ecx, &edx);
    int invariant_tsc = (edx >> 8) & 1;
    printf("cpuid(0x80000007): edx=0x%08x (invariant_tsc=%d)\n", edx, invariant_tsc);
    if (invariant_tsc != 1) {
        printf("FAIL: Expected Invariant TSC (edx bit 8 = 1), got %d\n", invariant_tsc);
        failed++;
    } else {
        printf("PASS: Invariant TSC confirmed (edx bit 8 = 1)\n");
    }

    /* 6. Multithreaded CPUID Trapping & Emulation */
    pthread_t thread;
    int thread_result = -1;
    if (pthread_create(&thread, NULL, thread_cpuid_worker, &thread_result) == 0) {
        pthread_join(thread, NULL);
        if (thread_result == 0) {
            printf("PASS: Multithreaded CPUID query verified in secondary thread\n");
        } else {
            printf("FAIL: Secondary thread failed CPUID verification (code=%d)\n", thread_result);
            failed++;
        }
    } else {
        printf("FAIL: Unable to spawn test thread\n");
        failed++;
    }

    if (failed == 0) {
        printf("\nALL CPUID VIRTUALIZATION CHECKS PASSED (failed=0)\n");
        return 0;
    } else {
        printf("\nCPUID VIRTUALIZATION CHECKS FAILED (failed=%d)\n", failed);
        return 1;
    }
}
