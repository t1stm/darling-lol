#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/sysctl.h>

static int copy_cfstring(CFTypeRef ref, char* out, size_t out_size)
{
    if (!ref || CFGetTypeID(ref) != CFStringGetTypeID())
        return 0;
    return CFStringGetCString((CFStringRef)ref, out, out_size, kCFStringEncodingUTF8) ? 1 : 0;
}

static int copy_cfdata_str(CFTypeRef ref, char* out, size_t out_size)
{
    if (!ref || CFGetTypeID(ref) != CFDataGetTypeID())
        return 0;
    CFIndex len = CFDataGetLength((CFDataRef)ref);
    const UInt8* ptr = CFDataGetBytePtr((CFDataRef)ref);
    if (len <= 0 || !ptr)
        return 0;
    size_t copy_len = (size_t)len < (out_size - 1) ? (size_t)len : (out_size - 1);
    memcpy(out, ptr, copy_len);
    out[copy_len] = '\0';
    return 1;
}

int main(void)
{
    char vendor[64] = {0};
    char brand[128] = {0};
    char model[64] = {0};
    char product[64] = {0};
    char targettype[64] = {0};
    size_t len;
    int cpu_family = -1, cpu_model = -1, cpu_stepping = -1, cpu_max_basic = -1, hv_vmm = -1;

    len = sizeof(vendor);
    if (sysctlbyname("machdep.cpu.vendor", vendor, &len, NULL, 0) != 0 || strcmp(vendor, "GenuineIntel") != 0) {
        fprintf(stderr, "FAIL: machdep.cpu.vendor=%s\n", vendor);
        return 1;
    }

    len = sizeof(brand);
    if (sysctlbyname("machdep.cpu.brand_string", brand, &len, NULL, 0) != 0 || strstr(brand, "Intel") == NULL) {
        fprintf(stderr, "FAIL: machdep.cpu.brand_string=%s\n", brand);
        return 1;
    }

    len = sizeof(model);
    if (sysctlbyname("hw.model", model, &len, NULL, 0) != 0 || strcmp(model, "MacBookPro16,1") != 0) {
        fprintf(stderr, "FAIL: hw.model=%s\n", model);
        return 1;
    }

    len = sizeof(product);
    if (sysctlbyname("hw.product", product, &len, NULL, 0) != 0 || strcmp(product, "MacBookPro16,1") != 0) {
        fprintf(stderr, "FAIL: hw.product=%s\n", product);
        return 1;
    }

    len = sizeof(targettype);
    if (sysctlbyname("hw.targettype", targettype, &len, NULL, 0) != 0 || strcmp(targettype, "Mac") != 0) {
        fprintf(stderr, "FAIL: hw.targettype=%s\n", targettype);
        return 1;
    }

    len = sizeof(cpu_family);
    if (sysctlbyname("machdep.cpu.family", &cpu_family, &len, NULL, 0) != 0 || len != sizeof(int) || cpu_family != 6) {
        fprintf(stderr, "FAIL: machdep.cpu.family=%d len=%zu\n", cpu_family, len);
        return 1;
    }

    len = sizeof(cpu_model);
    if (sysctlbyname("machdep.cpu.model", &cpu_model, &len, NULL, 0) != 0 || len != sizeof(int) || cpu_model != 158) {
        fprintf(stderr, "FAIL: machdep.cpu.model=%d len=%zu\n", cpu_model, len);
        return 1;
    }

    len = sizeof(cpu_stepping);
    if (sysctlbyname("machdep.cpu.stepping", &cpu_stepping, &len, NULL, 0) != 0 || len != sizeof(int) || cpu_stepping != 13) {
        fprintf(stderr, "FAIL: machdep.cpu.stepping=%d len=%zu\n", cpu_stepping, len);
        return 1;
    }

    len = sizeof(cpu_max_basic);
    if (sysctlbyname("machdep.cpu.max_basic", &cpu_max_basic, &len, NULL, 0) != 0 || len != sizeof(int) || cpu_max_basic != 22) {
        fprintf(stderr, "FAIL: machdep.cpu.max_basic=%d len=%zu\n", cpu_max_basic, len);
        return 1;
    }

    len = sizeof(hv_vmm);
    if (sysctlbyname("kern.hv_vmm_present", &hv_vmm, &len, NULL, 0) != 0 || len != sizeof(int) || hv_vmm != 0) {
        fprintf(stderr, "FAIL: kern.hv_vmm_present=%d len=%zu errno=%d\n", hv_vmm, len, errno);
        return 1;
    }

    io_service_t pe = IOServiceGetMatchingService(kIOMasterPortDefault, IOServiceMatching("IOPlatformExpertDevice"));
    if (pe == IO_OBJECT_NULL) {
        fprintf(stderr, "FAIL: IOServiceMatching(IOPlatformExpertDevice) returned NULL\n");
        return 2;
    }

    char uuid_pe[64] = {0}, serial_pe[64] = {0}, board_pe[64] = {0}, mlb_pe[64] = {0};
    CFTypeRef cf_uuid = IORegistryEntryCreateCFProperty(pe, CFSTR("IOPlatformUUID"), kCFAllocatorDefault, 0);
    CFTypeRef cf_serial = IORegistryEntryCreateCFProperty(pe, CFSTR("IOPlatformSerialNumber"), kCFAllocatorDefault, 0);
    CFTypeRef cf_board = IORegistryEntryCreateCFProperty(pe, CFSTR("board-id"), kCFAllocatorDefault, 0);
    CFTypeRef cf_mlb = IORegistryEntryCreateCFProperty(pe, CFSTR("mlb-serial-number"), kCFAllocatorDefault, 0);
    CFTypeRef cf_sysid = IORegistryEntryCreateCFProperty(pe, CFSTR("system-id"), kCFAllocatorDefault, 0);
    CFTypeRef cf_rom = IORegistryEntryCreateCFProperty(pe, CFSTR("rom"), kCFAllocatorDefault, 0);

    if (!copy_cfstring(cf_uuid, uuid_pe, sizeof(uuid_pe)) ||
        !copy_cfstring(cf_serial, serial_pe, sizeof(serial_pe)) ||
        !copy_cfdata_str(cf_board, board_pe, sizeof(board_pe)) ||
        !copy_cfdata_str(cf_mlb, mlb_pe, sizeof(mlb_pe)) ||
        !cf_sysid || CFGetTypeID(cf_sysid) != CFDataGetTypeID() || CFDataGetLength((CFDataRef)cf_sysid) != 16 ||
        !cf_rom || CFGetTypeID(cf_rom) != CFDataGetTypeID() || CFDataGetLength((CFDataRef)cf_rom) != 6) {
        fprintf(stderr, "FAIL: missing or invalid IOPlatformExpertDevice properties\n");
        return 2;
    }

    if (strcmp(serial_pe, "C02ZL0GVMD6N") == 0 || strcmp(uuid_pe, "6F3B2A1E-8C4D-4E5F-9A7B-1D2C3E4F5A6B") == 0) {
        fprintf(stderr, "FAIL: banned identity returned: serial=%s uuid=%s\n", serial_pe, uuid_pe);
        return 2;
    }

    // Check IORegistryEntryGetProperty (raw bytes MIG call)
    io_struct_inband_t prop_bytes = {0};
    uint32_t prop_size = sizeof(prop_bytes);
    if (IORegistryEntryGetProperty(pe, "board-id", prop_bytes, &prop_size) != KERN_SUCCESS ||
        strcmp(prop_bytes, board_pe) != 0) {
        fprintf(stderr, "FAIL: IORegistryEntryGetProperty(board-id) failed\n");
        return 2;
    }

    // Check IODeviceTree:/ via both C string and CFString ool path lookup
    io_registry_entry_t dt_root = IORegistryEntryFromPath(kIOMasterPortDefault, "IODeviceTree:/");
    io_registry_entry_t dt_root_cf = IORegistryEntryCopyFromPath(kIOMasterPortDefault, CFSTR("IODeviceTree:/"));
    io_registry_entry_t dt_options = IORegistryEntryFromPath(kIOMasterPortDefault, "IODeviceTree:/options");
    io_registry_entry_t dt_rom = IORegistryEntryFromPath(kIOMasterPortDefault, "IODeviceTree:/rom");
    io_registry_entry_t dt_efi_plat = IORegistryEntryFromPath(kIOMasterPortDefault, "IODeviceTree:/efi/platform");

    if (!dt_root || !dt_root_cf || !dt_options || !dt_rom || !dt_efi_plat) {
        fprintf(stderr, "FAIL: IODeviceTree path lookup failed (root=%u cf=%u options=%u rom=%u efi=%u)\n",
                dt_root, dt_root_cf, dt_options, dt_rom, dt_efi_plat);
        return 3;
    }

    if (!IORegistryEntryInPlane(dt_options, kIODeviceTreePlane)) {
        fprintf(stderr, "FAIL: IORegistryEntryInPlane(dt_options, IODeviceTree) returned false\n");
        return 3;
    }

    CFStringRef opt_path = IORegistryEntryCopyPath(dt_options, kIODeviceTreePlane);
    if (!opt_path) {
        fprintf(stderr, "FAIL: IORegistryEntryCopyPath(dt_options) returned NULL\n");
        return 3;
    }
    CFRelease(opt_path);

    char uuid_dt[64] = {0};
    CFTypeRef cf_uuid_dt = IORegistryEntryCreateCFProperty(dt_root_cf, CFSTR("IOPlatformUUID"), kCFAllocatorDefault, 0);
    if (!copy_cfstring(cf_uuid_dt, uuid_dt, sizeof(uuid_dt)) || strcmp(uuid_dt, uuid_pe) != 0) {
        fprintf(stderr, "FAIL: IODeviceTree:/ IOPlatformUUID=%s != %s\n", uuid_dt, uuid_pe);
        return 3;
    }

    printf("SMBIOS_IOKIT pass=1 serial=%s mlb=%s uuid=%s board=%s vendor=%s hv_vmm=%d\n",
           serial_pe, mlb_pe, uuid_pe, board_pe, vendor, hv_vmm);
    return 0;
}
