#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/sysctl.h>

/* Code signing constants */
#define CS_VALID                    0x00000001
#define CS_HARD                     0x00000100
#define CS_KILL                     0x00000200
#define CS_RESTRICT                 0x00000800
#define CS_ENFORCEMENT              0x00001000
#define CS_REQUIRE_LV               0x00002000
#define CS_ENTITLEMENTS_VALIDATED   0x00004000
#define CS_RUNTIME                  0x00010000

#define CS_OPS_STATUS               0
#define CS_OPS_MARKINVALID          1
#define CS_OPS_MARKHARD             2
#define CS_OPS_MARKKILL             3
#define CS_OPS_PIDPATH              4
#define CS_OPS_CDHASH               5
#define CS_OPS_PIDOFFSET            6
#define CS_OPS_ENTITLEMENTS_BLOB    7
#define CS_OPS_MARKRESTRICT         8
#define CS_OPS_SET_STATUS           9
#define CS_OPS_BLOB                 10
#define CS_OPS_IDENTITY             11
#define CS_OPS_CLEARINSTALLER       12
#define CS_OPS_CLEARPLATFORM        13
#define CS_OPS_TEAMID               14
#define CS_OPS_CLEAR_LV             15

#define CSMAGIC_EMBEDDED_ENTITLEMENTS 0xfade7171

typedef struct {
    unsigned int val[8];
} audit_token_t;

/* CSR (SIP) constants */
typedef uint32_t csr_config_t;
typedef uint32_t csr_op_t;
#define CSR_SYSCALL_CHECK               0
#define CSR_SYSCALL_GET_ACTIVE_CONFIG   1
#define CSR_ALLOW_UNRESTRICTED_FS       (1 << 1)

/* Syscall declarations */
extern int csops(pid_t pid, unsigned int ops, void *useraddr, size_t usersize);
extern int csops_audittoken(pid_t pid, unsigned int ops, void *useraddr, size_t usersize, audit_token_t *token);
extern int __csrctl(csr_op_t op, void *buffer, size_t size);
extern int csr_get_active_config(csr_config_t *config);
extern int csr_check(csr_config_t mask);
extern int __mac_syscall(const char *policy, int call, void *arg);

struct amfi_trustcache_args {
    unsigned char cdhash[20];
    uint64_t result;
};

int main(void) {
    int failed = 0;

    printf("=== Testing SIP (csr) ===\n");
    csr_config_t config = 0xdeadbeef;
    int rc = csr_get_active_config(&config);
    printf("csr_get_active_config: rc=%d config=0x%x (expected rc=0 config=0x0)\n", rc, config);
    if (rc != 0 || config != 0) {
        printf("FAILED: csr_get_active_config\n");
        failed++;
    }

    /* Size mismatch check for csrctl */
    errno = 0;
    uint64_t oversized_config = 0;
    rc = __csrctl(CSR_SYSCALL_GET_ACTIVE_CONFIG, &oversized_config, sizeof(oversized_config));
    printf("csrctl(GET_ACTIVE_CONFIG, size=8): rc=%d errno=%d (expected rc=-1 errno=EINVAL=%d)\n", rc, errno, EINVAL);
    if (rc != -1 || errno != EINVAL) {
        printf("FAILED: csrctl bad size validation\n");
        failed++;
    }

    rc = csr_check(0);
    printf("csr_check(0): rc=%d (expected 0)\n", rc);
    if (rc != 0) {
        printf("FAILED: csr_check(0)\n");
        failed++;
    }

    errno = 0;
    rc = csr_check(CSR_ALLOW_UNRESTRICTED_FS);
    printf("csr_check(UNRESTRICTED_FS): rc=%d errno=%d (expected rc=-1 errno=EPERM=%d)\n", rc, errno, EPERM);
    if (rc != -1 || errno != EPERM) {
        printf("FAILED: csr_check(UNRESTRICTED_FS)\n");
        failed++;
    }

    printf("\n=== Testing Code Signing (csops) ===\n");
    uint32_t csflags = 0;
    rc = csops(0, CS_OPS_STATUS, &csflags, sizeof(csflags));
    printf("csops(STATUS): rc=%d flags=0x%x\n", rc, csflags);
    if (rc != 0 || !(csflags & CS_VALID) || !(csflags & CS_HARD) || !(csflags & CS_ENFORCEMENT) || !(csflags & CS_ENTITLEMENTS_VALIDATED)) {
        printf("FAILED: csops(STATUS) missing expected flags\n");
        failed++;
    }

    uint8_t cdhash[20] = {0};
    rc = csops(0, CS_OPS_CDHASH, cdhash, sizeof(cdhash));
    printf("csops(CDHASH): rc=%d cdhash=", rc);
    int cdhash_all_zero = 1;
    for (int i = 0; i < 20; i++) {
        printf("%02x", cdhash[i]);
        if (cdhash[i] != 0) cdhash_all_zero = 0;
    }
    printf("\n");
    if (rc != 0 || cdhash_all_zero) {
        printf("FAILED: csops(CDHASH) returned zeroes or error\n");
        failed++;
    }

    char idbuf[128] = {0};
    rc = csops(0, CS_OPS_IDENTITY, idbuf, sizeof(idbuf));
    printf("csops(IDENTITY): rc=%d identity=\"%s\"\n", rc, rc == 0 ? (idbuf + 8) : "");
    if (rc != 0 || strlen(idbuf + 8) == 0) {
        printf("FAILED: csops(IDENTITY)\n");
        failed++;
    }

    char teambuf[64] = {0};
    errno = 0;
    rc = csops(0, CS_OPS_TEAMID, teambuf, sizeof(teambuf));
    printf("csops(TEAMID): rc=%d errno=%d teamid=\"%s\"\n", rc, errno, rc == 0 ? (teambuf + 8) : "");
    if (rc == -1 && errno == ENOENT) {
        printf("csops(TEAMID): correctly returned ENOENT for binary without team ID\n");
    } else if (rc == 0) {
        printf("csops(TEAMID): returned team ID \"%s\"\n", teambuf + 8);
    } else {
        printf("FAILED: csops(TEAMID) unexpected error rc=%d errno=%d\n", rc, errno);
        failed++;
    }

    off_t pidoff = -1;
    rc = csops(0, CS_OPS_PIDOFFSET, &pidoff, sizeof(pidoff));
    printf("csops(PIDOFFSET): rc=%d offset=%lld (expected 0)\n", rc, (long long)pidoff);
    if (rc != 0 || pidoff != 0) {
        printf("FAILED: csops(PIDOFFSET)\n");
        failed++;
    }

    char pathbuf[256] = {0};
    rc = csops(0, CS_OPS_PIDPATH, pathbuf, sizeof(pathbuf));
    printf("csops(PIDPATH): rc=%d path=\"%s\"\n", rc, rc == 0 ? pathbuf : "");
    if (rc != 0 || strlen(pathbuf) == 0) {
        printf("FAILED: csops(PIDPATH)\n");
        failed++;
    }

    /* Entitlements blob probing */
    uint32_t ent_hdr[2] = {0, 0};
    errno = 0;
    rc = csops(0, CS_OPS_ENTITLEMENTS_BLOB, ent_hdr, sizeof(ent_hdr));
    uint32_t ent_magic = __builtin_bswap32(ent_hdr[0]);
    uint32_t ent_len = __builtin_bswap32(ent_hdr[1]);
    printf("csops(ENTITLEMENTS_BLOB probe 8B): rc=%d errno=%d magic=0x%x len=%u\n", rc, errno, ent_magic, ent_len);
    if (rc != -1 || errno != ERANGE || ent_magic != CSMAGIC_EMBEDDED_ENTITLEMENTS || ent_len <= 8) {
        printf("FAILED: csops(ENTITLEMENTS_BLOB) probe\n");
        failed++;
    }

    /* Full entitlements read */
    if (ent_len > 8 && ent_len < 4096) {
        char *ent_buf = calloc(1, ent_len + 1);
        if (ent_buf) {
            rc = csops(0, CS_OPS_ENTITLEMENTS_BLOB, ent_buf, ent_len);
            ent_buf[ent_len] = '\0';
            uint32_t raw_magic = 0;
            memcpy(&raw_magic, ent_buf, sizeof(uint32_t));
            uint32_t full_magic = __builtin_bswap32(raw_magic);
            printf("csops(ENTITLEMENTS_BLOB full): rc=%d magic=0x%x contains_plist=%d\n",
                   rc, full_magic, strstr(ent_buf + 8, "<plist") != NULL);
            if (rc != 0 || full_magic != CSMAGIC_EMBEDDED_ENTITLEMENTS || !strstr(ent_buf + 8, "<plist")) {
                printf("FAILED: csops(ENTITLEMENTS_BLOB) full read\n");
                failed++;
            }
            free(ent_buf);
        }
    }

    rc = csops(0, CS_OPS_MARKRESTRICT, NULL, 0);
    uint32_t csflags2 = 0;
    csops(0, CS_OPS_STATUS, &csflags2, sizeof(csflags2));
    printf("csops(MARKRESTRICT): rc=%d new_flags=0x%x restricted=%d\n", rc, csflags2, !!(csflags2 & CS_RESTRICT));
    if (rc != 0 || !(csflags2 & CS_RESTRICT)) {
        printf("FAILED: csops(MARKRESTRICT)\n");
        failed++;
    }

    /* Test non-existent PID handling (must return ESRCH) */
    errno = 0;
    uint32_t dummy_flags = 0;
    rc = csops(999999, CS_OPS_STATUS, &dummy_flags, sizeof(dummy_flags));
    printf("csops(non-existent PID 999999): rc=%d errno=%d (expected rc=-1 errno=ESRCH=%d)\n", rc, errno, ESRCH);
    if (rc != -1 || errno != ESRCH) {
        printf("FAILED: csops non-existent PID check\n");
        failed++;
    }

    /* Test invalid operation (must return EINVAL) */
    errno = 0;
    rc = csops(0, 99999, NULL, 0);
    printf("csops(invalid op 99999): rc=%d errno=%d (expected rc=-1 errno=EINVAL=%d)\n", rc, errno, EINVAL);
    if (rc != -1 || errno != EINVAL) {
        printf("FAILED: csops invalid op check\n");
        failed++;
    }

    /* Test audit token mismatch with pid=0 */
    audit_token_t bad_token;
    memset(&bad_token, 0, sizeof(bad_token));
    bad_token.val[5] = 987654; /* Mismatched PID */
    errno = 0;
    rc = csops_audittoken(0, CS_OPS_STATUS, &dummy_flags, sizeof(dummy_flags), &bad_token);
    printf("csops_audittoken(mismatched token PID): rc=%d errno=%d (expected rc=-1 errno=ESRCH=%d)\n", rc, errno, ESRCH);
    if (rc != -1 || errno != ESRCH) {
        printf("FAILED: csops_audittoken mismatch check\n");
        failed++;
    }

    /* Test foreign PID target via fork */
    pid_t child = fork();
    if (child == 0) {
        usleep(100000); /* 100ms */
        _exit(0);
    } else if (child > 0) {
        uint32_t child_flags = 0;
        rc = csops(child, CS_OPS_STATUS, &child_flags, sizeof(child_flags));
        printf("csops(live child PID %d): rc=%d flags=0x%x\n", child, rc, child_flags);
        if (rc != 0 || !(child_flags & CS_VALID)) {
            printf("FAILED: csops live child check\n");
            failed++;
        }
        int status;
        waitpid(child, &status, 0);

        /* After child exits, query must fail with ESRCH */
        errno = 0;
        rc = csops(child, CS_OPS_STATUS, &child_flags, sizeof(child_flags));
        printf("csops(dead child PID %d): rc=%d errno=%d (expected rc=-1 errno=ESRCH=%d)\n", child, rc, errno, ESRCH);
        if (rc != -1 || errno != ESRCH) {
            printf("FAILED: csops dead child ESRCH check\n");
            failed++;
        }
    }

    printf("\n=== Testing MAC Policy Syscalls (__mac_syscall) ===\n");
    struct amfi_trustcache_args tc_args;
    memset(&tc_args, 0, sizeof(tc_args));
    memcpy(tc_args.cdhash, cdhash, 20);
    rc = __mac_syscall("AMFI", 95, &tc_args);
    printf("__mac_syscall(AMFI, 95): rc=%d result=%llu (expected rc=0 result=1)\n", rc, (unsigned long long)tc_args.result);
    if (rc != 0 || tc_args.result != 1) {
        printf("FAILED: __mac_syscall AMFI trustcache\n");
        failed++;
    }

    rc = __mac_syscall("Sandbox", 0, NULL);
    printf("__mac_syscall(Sandbox): rc=%d (expected 0)\n", rc);
    if (rc != 0) {
        printf("FAILED: __mac_syscall Sandbox\n");
        failed++;
    }

    rc = __mac_syscall("Quarantine", 0, NULL);
    printf("__mac_syscall(Quarantine): rc=%d (expected 0)\n", rc);
    if (rc != 0) {
        printf("FAILED: __mac_syscall Quarantine\n");
        failed++;
    }

    errno = 0;
    rc = __mac_syscall("FakeUnknownPolicy", 0, NULL);
    printf("__mac_syscall(FakeUnknownPolicy): rc=%d errno=%d (expected rc=-1 errno=ENOSYS=%d)\n", rc, errno, ENOSYS);
    if (rc != -1 || errno != ENOSYS) {
        printf("FAILED: __mac_syscall FakeUnknownPolicy\n");
        failed++;
    }

    printf("\n=== Testing Security Sysctls ===\n");
    char bootargs[128] = "nonempty";
    size_t len = sizeof(bootargs);
    rc = sysctlbyname("kern.bootargs", bootargs, &len, NULL, 0);
    printf("sysctl(kern.bootargs): rc=%d len=%zu bootargs=\"%s\"\n", rc, len, rc == 0 ? bootargs : "");
    if (rc != 0 || strcmp(bootargs, "") != 0) {
        printf("FAILED: kern.bootargs\n");
        failed++;
    }

    int secure_kernel = -1;
    len = sizeof(secure_kernel);
    rc = sysctlbyname("kern.secure_kernel", &secure_kernel, &len, NULL, 0);
    printf("sysctl(kern.secure_kernel): rc=%d secure_kernel=%d\n", rc, secure_kernel);
    if (rc != 0 || secure_kernel != 0) {
        printf("FAILED: kern.secure_kernel\n");
        failed++;
    }

    int cs_proc_enf = -1;
    len = sizeof(cs_proc_enf);
    rc = sysctlbyname("vm.cs_process_enforcement", &cs_proc_enf, &len, NULL, 0);
    printf("sysctl(vm.cs_process_enforcement): rc=%d val=%d (expected 1)\n", rc, cs_proc_enf);
    if (rc != 0 || cs_proc_enf != 1) {
        printf("FAILED: vm.cs_process_enforcement\n");
        failed++;
    }

    int cs_sys_enf = -1;
    len = sizeof(cs_sys_enf);
    rc = sysctlbyname("vm.cs_system_enforcement", &cs_sys_enf, &len, NULL, 0);
    printf("sysctl(vm.cs_system_enforcement): rc=%d val=%d (expected 1)\n", rc, cs_sys_enf);
    if (rc != 0 || cs_sys_enf != 1) {
        printf("FAILED: vm.cs_system_enforcement\n");
        failed++;
    }

    int cs_lib_val = -1;
    len = sizeof(cs_lib_val);
    rc = sysctlbyname("vm.cs_library_validation", &cs_lib_val, &len, NULL, 0);
    printf("sysctl(vm.cs_library_validation): rc=%d val=%d (expected 1)\n", rc, cs_lib_val);
    if (rc != 0 || cs_lib_val != 1) {
        printf("FAILED: vm.cs_library_validation\n");
        failed++;
    }

    int sb_sentinel = -1;
    len = sizeof(sb_sentinel);
    rc = sysctlbyname("security.mac.sandbox.sentinel", &sb_sentinel, &len, NULL, 0);
    printf("sysctl(security.mac.sandbox.sentinel): rc=%d val=%d (expected 1)\n", rc, sb_sentinel);
    if (rc != 0 || sb_sentinel != 1) {
        printf("FAILED: security.mac.sandbox.sentinel\n");
        failed++;
    }

    int qtn_enf = -1;
    len = sizeof(qtn_enf);
    rc = sysctlbyname("security.mac.qtn.sandbox_enforce", &qtn_enf, &len, NULL, 0);
    printf("sysctl(security.mac.qtn.sandbox_enforce): rc=%d val=%d (expected 1)\n", rc, qtn_enf);
    if (rc != 0 || qtn_enf != 1) {
        printf("FAILED: security.mac.qtn.sandbox_enforce\n");
        failed++;
    }

    int amfi_verbose = -1;
    len = sizeof(amfi_verbose);
    rc = sysctlbyname("security.mac.amfi.verbose", &amfi_verbose, &len, NULL, 0);
    printf("sysctl(security.mac.amfi.verbose): rc=%d val=%d (expected 0)\n", rc, amfi_verbose);
    if (rc != 0 || amfi_verbose != 0) {
        printf("FAILED: security.mac.amfi.verbose\n");
        failed++;
    }

    if (failed == 0) {
        printf("\nALL SECURITY PROBES PASSED (failed=0)\n");
        return 0;
    } else {
        printf("\nPROBES FAILED: count=%d\n", failed);
        return 1;
    }
}
