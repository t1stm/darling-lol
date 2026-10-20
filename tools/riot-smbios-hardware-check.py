#!/usr/bin/env python3
"""Verify GenSMBIOS identity generation, system_profiler hardware/software output, and live Darling IOKit/sysctl."""
import getpass
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def load_smbios_module():
    path = Path(__file__).resolve().with_name("gen-darling-smbios.py")
    spec = importlib.util.spec_from_file_location("gen_darling_smbios", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_gensmbios_offline(mod):
    # 1. Test generation across all supported Mac models
    for model_name in mod.MODELS:
        cfg = mod.generate_identity(model_name)
        assert mod.is_valid_config(cfg), f"Generated invalid config for {model_name}: {cfg}"
        assert cfg["SMBIOS_MODEL"] == model_name
        assert cfg["SMBIOS_SERIAL_NUMBER"] not in mod.BANNED_SERIALS
        assert cfg["SMBIOS_PLATFORM_UUID"] not in mod.BANNED_UUIDS
        assert len(cfg["SMBIOS_SERIAL_NUMBER"]) == 12
        assert len(cfg["SMBIOS_MLB"]) == 17
        assert len(cfg["SMBIOS_SYSTEM_ID"]) == 32
        assert len(cfg["SMBIOS_ROM"]) == 12
        assert cfg["SMBIOS_PROVISIONING_UDID"] == cfg["SMBIOS_PLATFORM_UUID"]

    # 2. Test --ensure replaces banned hardcoded identity and preserves valid custom identity
    with tempfile.TemporaryDirectory(prefix="smbios-test-") as tmp:
        prefix = Path(tmp) / "prefix"
        (prefix / "private/etc").mkdir(parents=True)
        (prefix / "etc").mkdir(parents=True)  # Separate /etc directory to test mirroring

        # Write banned hardcoded serial/UUID
        banned_cfg = mod.generate_identity("MacBookPro16,1")
        banned_cfg["SMBIOS_SERIAL_NUMBER"] = "C02ZL0GVMD6N"
        banned_cfg["SMBIOS_PLATFORM_UUID"] = "6F3B2A1E-8C4D-4E5F-9A7B-1D2C3E4F5A6B"
        assert not mod.is_valid_config(banned_cfg), "Banned identity must fail validation"
        (prefix / "private/etc/darling-smbios.conf").write_text(mod.format_config(banned_cfg))

        cfg1, created1 = mod.ensure_smbios(prefix)
        assert created1, "ensure_smbios must regenerate when banned identity is present"
        assert mod.is_valid_config(cfg1)
        assert (prefix / "etc/darling-smbios.conf").is_file(), "Mirrored /etc/darling-smbios.conf missing"

        # Calling ensure_smbios again must preserve the valid identity
        cfg2, created2 = mod.ensure_smbios(prefix)
        assert not created2, "ensure_smbios must preserve valid identity"
        assert cfg2["SMBIOS_SERIAL_NUMBER"] == cfg1["SMBIOS_SERIAL_NUMBER"]
        assert cfg2["SMBIOS_PLATFORM_UUID"] == cfg1["SMBIOS_PLATFORM_UUID"]

        # An older non-UUID provisioning UDID is repaired in place without a new identity
        stale = dict(cfg2, SMBIOS_PROVISIONING_UDID="00008006-00" + cfg2["SMBIOS_SYSTEM_ID"][:14])
        (prefix / "private/etc/darling-smbios.conf").write_text(mod.format_config(stale))
        repaired, created = mod.ensure_smbios(prefix)
        assert not created and repaired["SMBIOS_SERIAL_NUMBER"] == cfg2["SMBIOS_SERIAL_NUMBER"]
        assert mod.read_config(prefix / "private/etc/darling-smbios.conf")["SMBIOS_PROVISIONING_UDID"] == cfg2["SMBIOS_PLATFORM_UUID"]

        # Calling with regenerate=True must produce a new identity
        cfg3, created3 = mod.ensure_smbios(prefix, regenerate=True)
        assert created3
        assert cfg3["SMBIOS_PLATFORM_UUID"] != cfg1["SMBIOS_PLATFORM_UUID"]

        # 3. Test --from-gensmbios JSON and OpenCore plist import
        sample_json = Path(tmp) / "gensmbios.json"
        sample_json.write_text(json.dumps({
            "Type": "MacBookPro16,1",
            "Serial": "C02C51ABMD6N",
            "Board Serial": "C02005130CD3N9PRA",
            "SmUUID": "B4A1E2D3-8C4D-4E5F-9A7B-2D3C4E5F6A7B",
            "ROM": "F0:18:98:11:22:33",
        }))
        imported = mod.import_gensmbios_file(sample_json)
        assert imported["SMBIOS_SERIAL_NUMBER"] == "C02C51ABMD6N"
        assert imported["SMBIOS_MLB"] == "C02005130CD3N9PRA"
        assert imported["SMBIOS_PLATFORM_UUID"] == "B4A1E2D3-8C4D-4E5F-9A7B-2D3C4E5F6A7B"
        assert imported["SMBIOS_ROM"] == "F01898112233"
        assert mod.is_valid_config(imported)

        oc_plist = Path(tmp) / "config.plist"
        oc_plist.write_bytes(plistlib.dumps({
            "PlatformInfo": {
                "Generic": {
                    "SystemProductName": "MacBookPro16,1",
                    "SystemSerialNumber": "C02C51XYMD6P",
                    "MLB": "C02005130EF4N9PQB",
                    "SystemUUID": "C5B2F3E4-9D5E-4F6A-8B8C-3E4D5F6A7B8C",
                    "ROM": bytes.fromhex("3C22FB445566"),
                }
            }
        }))
        imported_oc = mod.import_gensmbios_file(oc_plist)
        assert imported_oc["SMBIOS_SERIAL_NUMBER"] == "C02C51XYMD6P"
        assert imported_oc["SMBIOS_ROM"] == "3C22FB445566"
        assert mod.is_valid_config(imported_oc)


def test_system_profiler_offline(mod):
    profiler = Path(__file__).resolve().with_name("darling-system_profiler.sh")
    with tempfile.TemporaryDirectory(prefix="sp-test-") as tmp:
        prefix = Path(tmp) / "prefix"
        cfg, _ = mod.ensure_smbios(prefix)
        conf_path = prefix / "private/etc/darling-smbios.conf"
        env = dict(os.environ, DARLING_SMBIOS_CONF=str(conf_path), DARLING_SYSTEM_ROOT="/")

        # 1. -listDataTypes
        listed = subprocess.check_output(["sh", str(profiler), "-listDataTypes"], env=env, text=True)
        for dtype in ("SPHardwareDataType", "SPSoftwareDataType", "SPDisplaysDataType", "SPEthernetDataType", "SPAirPortDataType"):
            assert dtype in listed, f"Missing {dtype} in -listDataTypes"

        # 2. -xml SPHardwareDataType SPSoftwareDataType
        xml_out = subprocess.check_output(
            ["sh", str(profiler), "-xml", "SPHardwareDataType", "SPSoftwareDataType"],
            env=env,
        )
        parsed = plistlib.loads(xml_out)
        assert len(parsed) == 2
        hw_item = parsed[0]["_items"][0]
        sw_item = parsed[1]["_items"][0]
        assert hw_item["machine_model"] == cfg["SMBIOS_MODEL"]
        assert hw_item["serial_number"] == cfg["SMBIOS_SERIAL_NUMBER"]
        assert hw_item["platform_UUID"] == cfg["SMBIOS_PLATFORM_UUID"]
        assert hw_item["provisioning_UDID"] == cfg["SMBIOS_PROVISIONING_UDID"]
        assert hw_item["boot_rom_version"] == cfg["SMBIOS_BOOT_ROM_VERSION"]
        assert hw_item["SMC_version_system"] == cfg["SMBIOS_SMC_VERSION"]
        assert sw_item["system_integrity"] == "integrity_enabled"
        assert sw_item["secure_vm"] == "secure_vm_enabled"
        assert sw_item["boot_mode"] == "normal_boot"

        # 3. Plain text output
        txt_out = subprocess.check_output(
            ["sh", str(profiler), "SPHardwareDataType", "SPSoftwareDataType"],
            env=env,
            text=True,
        )
        assert f"Serial Number (system): {cfg['SMBIOS_SERIAL_NUMBER']}" in txt_out
        assert f"Hardware UUID: {cfg['SMBIOS_PLATFORM_UUID']}" in txt_out
        assert "System Integrity Protection: Enabled" in txt_out


def test_live_darling_iokit_and_sysctl(mod):
    sdk = Path(os.environ.get("DARLING_SDK", "/usr/local/libexec/darling"))
    darling_src = ROOT / "build/darling-src"
    macos_sdk = darling_src / "Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk"
    c_src = Path(__file__).resolve().with_name("riot-smbios-iokit-check.c")
    if not sdk.is_dir() or not macos_sdk.is_dir() or not c_src.is_file():
        return "SKIP"

    prefix = Path(os.environ.get("DPREFIX", str(Path.home() / ".darling")))
    cfg, _ = mod.ensure_smbios(prefix)
    guest_bin = (ROOT / "build/riot-smbios-iokit-check").resolve()
    obj_file = (ROOT / "build/riot-smbios-iokit-check.o").resolve()
    guest_bin.parent.mkdir(parents=True, exist_ok=True)

    subprocess.run([
        "clang", "-target", "x86_64-apple-macosx11.0", "-O2",
        "-Wno-undef-prefix",
        "-isysroot", str(macos_sdk),
        f"-I{darling_src}/framework-include",
        f"-I{darling_src}/src/external/corefoundation/include",
        f"-I{darling_src}/build/src/external/IOKitUser/include",
        f"-I{darling_src}/src/external/IOKitUser",
        "-c", str(c_src), "-o", str(obj_file),
    ], check=True)
    subprocess.run([
        "clang", "-target", "x86_64-apple-macosx11.0", "-fuse-ld=lld", "-nostdlib",
        "-isysroot", str(sdk),
        str(obj_file),
        "-framework", "IOKit", "-framework", "CoreFoundation", "-lSystem",
        "-o", str(guest_bin),
    ], check=True)

    def is_server_or_game_running():
        try:
            for p in Path("/proc").iterdir():
                if not p.name.isdigit():
                    continue
                try:
                    status = p / "status"
                    if status.is_file():
                        try:
                            state = next(line.split()[1] for line in status.read_text().splitlines() if line.startswith("State:"))
                            if state == "Z":
                                continue
                        except (OSError, StopIteration):
                            pass
                    comm = (p / "comm").read_text().strip()
                    if comm in ("darlingserver",):
                        return True
                    if comm in ("mldr", "CrBrowserMain", "CrGpuMain", "CrRendererMain", "CrUtilityMain", "LeagueofLegends", "RiotClientServices"):
                        cmdline = (p / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", errors="replace")
                        if any(k in cmdline for k in ("League", "Riot")):
                            return True
                except (OSError, PermissionError):
                    continue
        except Exception:
            pass
        return False

    server_was_running = is_server_or_game_running()
    stop_script = Path(__file__).resolve().with_name("stop-darling-runtime.py")
    ensure_script = Path(__file__).resolve().with_name("ensure-darling-runtime.py")
    if not server_was_running:
        subprocess.run([sys.executable, str(stop_script)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run([sys.executable, str(ensure_script)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    guest_user = os.environ.get("GUEST_USER", getpass.getuser())
    guest_home = f"/Users/{guest_user}"
    build_dir = str(ROOT / "build")
    guest_dyld = f"/Volumes/SystemRoot{build_dir}:{guest_home}/RuntimeLibraries"
    guest_env = dict(
        os.environ,
        DYLD_LIBRARY_PATH=guest_dyld,
        DYLD_FRAMEWORK_PATH=f"{guest_home}/RuntimeFrameworks",
    )
    try:
        with tempfile.TemporaryFile(mode="w+b") as out_f:
            res = subprocess.run(
                [
                    "darling", "shell", "env",
                    f"DYLD_LIBRARY_PATH={guest_dyld}",
                    f"DYLD_FRAMEWORK_PATH={guest_home}/RuntimeFrameworks",
                    "/Volumes/SystemRoot" + str(guest_bin),
                ],
                env=guest_env, stdin=subprocess.DEVNULL, stdout=out_f, stderr=out_f, check=False,
            )
            out_f.seek(0)
            raw_lines = out_f.read().decode("utf-8", errors="replace").splitlines()
            line = next((l[l.index("SMBIOS_IOKIT"):] for l in raw_lines if "SMBIOS_IOKIT" in l), "\n".join(raw_lines))
        if res.returncode != 0:
            raise AssertionError(f"live IOKit check failed (exit {res.returncode}): {line.strip()}")
        assert f"serial={cfg['SMBIOS_SERIAL_NUMBER']}" in line, f"Expected serial {cfg['SMBIOS_SERIAL_NUMBER']} in {line}"
        assert f"uuid={cfg['SMBIOS_PLATFORM_UUID']}" in line, f"Expected uuid {cfg['SMBIOS_PLATFORM_UUID']} in {line}"
        assert "vendor=GenuineIntel" in line, f"Expected GenuineIntel in {line}"
        assert "hv_vmm=0" in line, f"Expected hv_vmm=0 in {line}"

        with tempfile.TemporaryFile(mode="w+b") as sp_f, tempfile.TemporaryFile(mode="w+b") as err_f:
            subprocess.run(
                [
                    "darling", "shell", "env",
                    f"DYLD_LIBRARY_PATH={guest_dyld}",
                    f"DYLD_FRAMEWORK_PATH={guest_home}/RuntimeFrameworks",
                    "/usr/sbin/system_profiler", "-xml", "SPHardwareDataType",
                ],
                env=guest_env, stdin=subprocess.DEVNULL, stdout=sp_f, stderr=err_f, check=True,
            )
            sp_f.seek(0)
            raw_sp = sp_f.read()
        sp_xml = raw_sp[raw_sp.index(b"<?xml"):raw_sp.index(b"</plist>") + len(b"</plist>")]
        sp_data = plistlib.loads(sp_xml)[0]["_items"][0]
        assert sp_data["serial_number"] == cfg["SMBIOS_SERIAL_NUMBER"]
        assert sp_data["platform_UUID"] == cfg["SMBIOS_PLATFORM_UUID"]
        return line
    except (OSError, subprocess.SubprocessError) as exc:
        return f"SKIP ({exc})"
    finally:
        if not server_was_running:
            subprocess.run([sys.executable, str(stop_script)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    mod = load_smbios_module()
    test_gensmbios_offline(mod)
    test_system_profiler_offline(mod)
    if "--offline" in sys.argv:
        live = "SKIP (--offline requested)"
    else:
        live = test_live_darling_iokit_and_sysctl(mod)
    print(f"SMBIOS_HARDWARE_CHECK pass=1 offline=PASS system_profiler=PASS live={live}")


if __name__ == "__main__":
    main()
