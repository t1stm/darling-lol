#!/usr/bin/env python3
"""GenSMBIOS / macserial-compatible SMBIOS identity generator for Darling prefixes."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import re
import secrets
import sys
import uuid

# Apple Base-34 serial alphabet (excludes I and O; macserial also omits B/U in random slots)
BASE34_ALPHABET = "0123456789CDFGHJKLMNPQRSTVWXYZ"
WEEK_CHARS = "123456789CDFGHJKLMNPQRSTVWXY"  # 26 week codes per half-year (index 0..25 -> week 1..26)

# Known hardcoded / compromised identities that must never be used or retained
BANNED_SERIALS = frozenset({
    "C02ZL0GVMD6N",
    "C02000000000",
    "W88000000000",
})
BANNED_UUIDS = frozenset({
    "6F3B2A1E-8C4D-4E5F-9A7B-1D2C3E4F5A6B",
    "00000000-0000-0000-0000-000000000000",
})

# Authentic Apple OUI prefixes used by macserial / GenSMBIOS for 6-byte ROM generation
APPLE_ROM_OUIS = (
    "F01898",
    "3C22FB",
    "8C8590",
    "A483E7",
    "DC86D8",
    "F8FF0B",
)

MLB_LINE_CODES = ("104", "108", "130", "200", "301", "401", "500", "600", "700", "800")

# Half-year code -> (MLB single-digit year, week offset 0 or 26)
YEAR_CODE_MAP = {
    "Y": ("9", 0),   # 2019 H1 (weeks 01..26)
    "Z": ("9", 26),  # 2019 H2 (weeks 27..52)
    "C": ("0", 0),   # 2020 H1 (weeks 01..26)
    "D": ("0", 26),  # 2020 H2 (weeks 27..52)
    "H": ("8", 0),   # 2018 H1 (weeks 01..26)
    "J": ("8", 26),  # 2018 H2 (weeks 27..52)
}

MODELS = {
    "MacBookPro16,1": {
        "model": "MacBookPro16,1",
        "product_name": "MacBookPro16,1",
        "machine_name": "MacBook Pro",
        "board_id": "Mac-E1008331FDC96864",
        "bridge_model": "j152f",
        "boot_rom_version": "2020.41.1.0.0 (iBridge: 21.16.1069.0.0,0)",
        "smc_version": "2.58f15",
        "cpu_type": "8-Core Intel Core i9",
        "cpu_brand": "Intel(R) Core(TM) i9-9980HK CPU @ 2.40GHz",
        "cpu_speed": "2.4 GHz",
        "packages": "1",
        "cores": "8",
        "memory": "16 GB",
        "locations": ("C02",),
        "year_codes": ("Z", "C", "D"),
        "model_codes": ("MD6N", "MD6P", "MD6Q", "MD6R", "MMG0"),
        "eee_codes": ("N9PR", "N9PQ", "N9PP", "M779", "N9PN"),
    },
    "MacBookPro16,4": {
        "model": "MacBookPro16,4",
        "product_name": "MacBookPro16,4",
        "machine_name": "MacBook Pro",
        "board_id": "Mac-A61BADE1FDAD7B05",
        "bridge_model": "j215",
        "boot_rom_version": "2020.41.1.0.0 (iBridge: 21.16.1069.0.0,0)",
        "smc_version": "2.62f12",
        "cpu_type": "8-Core Intel Core i9",
        "cpu_brand": "Intel(R) Core(TM) i9-9980HK CPU @ 2.40GHz",
        "cpu_speed": "2.4 GHz",
        "packages": "1",
        "cores": "8",
        "memory": "16 GB",
        "locations": ("C02",),
        "year_codes": ("C", "D"),
        "model_codes": ("PG9X", "PG9Y", "PH00"),
        "eee_codes": ("PJ4D", "PJ4F", "PJ4G"),
    },
    "iMac20,1": {
        "model": "iMac20,1",
        "product_name": "iMac20,1",
        "machine_name": "iMac",
        "board_id": "Mac-CFF7D910A743CAAF",
        "bridge_model": "j185",
        "boot_rom_version": "2020.41.1.0.0 (iBridge: 21.16.1069.0.0,0)",
        "smc_version": "2.60f19",
        "cpu_type": "8-Core Intel Core i7",
        "cpu_brand": "Intel(R) Core(TM) i9-9980HK CPU @ 2.40GHz",
        "cpu_speed": "2.4 GHz",
        "packages": "1",
        "cores": "8",
        "memory": "16 GB",
        "locations": ("C02",),
        "year_codes": ("C", "D"),
        "model_codes": ("PN5T", "PN5U", "PN5V", "PN5W"),
        "eee_codes": ("P02J", "P02K", "P02L"),
    },
    "MacPro7,1": {
        "model": "MacPro7,1",
        "product_name": "MacPro7,1",
        "machine_name": "Mac Pro",
        "board_id": "Mac-27AD2F918AE68F61",
        "bridge_model": "j160",
        "boot_rom_version": "2020.41.1.0.0 (iBridge: 21.16.1069.0.0,0)",
        "smc_version": "2.56f18",
        "cpu_type": "8-Core Intel Xeon W",
        "cpu_brand": "Intel(R) Core(TM) i9-9980HK CPU @ 2.40GHz",
        "cpu_speed": "2.4 GHz",
        "packages": "1",
        "cores": "8",
        "memory": "16 GB",
        "locations": ("F5K",),
        "year_codes": ("Z", "C", "D"),
        "model_codes": ("P7QM", "N5RH", "PLXV"),
        "eee_codes": ("K3F7", "K3F8", "K3FC"),
    },
    "Macmini8,1": {
        "model": "Macmini8,1",
        "product_name": "Macmini8,1",
        "machine_name": "Mac mini",
        "board_id": "Mac-7BA5B2DFE22DDD8C",
        "bridge_model": "j174",
        "boot_rom_version": "2020.41.1.0.0 (iBridge: 21.16.1069.0.0,0)",
        "smc_version": "2.46f18",
        "cpu_type": "6-Core Intel Core i7",
        "cpu_brand": "Intel(R) Core(TM) i9-9980HK CPU @ 2.40GHz",
        "cpu_speed": "2.4 GHz",
        "packages": "1",
        "cores": "8",
        "memory": "16 GB",
        "locations": ("C07",),
        "year_codes": ("H", "J", "Y", "Z"),
        "model_codes": ("JYVX", "JYVY", "JYVZ"),
        "eee_codes": ("K67X", "K67Y", "K67Z"),
    },
}

CONFIG_KEYS = (
    "SMBIOS_MODEL",
    "SMBIOS_PRODUCT_NAME",
    "SMBIOS_MACHINE_NAME",
    "SMBIOS_MANUFACTURER",
    "SMBIOS_BOARD_ID",
    "SMBIOS_BRIDGE_MODEL",
    "SMBIOS_TARGET_TYPE",
    "SMBIOS_SERIAL_NUMBER",
    "SMBIOS_MLB",
    "SMBIOS_PLATFORM_UUID",
    "SMBIOS_SYSTEM_ID",
    "SMBIOS_PROVISIONING_UDID",
    "SMBIOS_ROM",
    "SMBIOS_BOOT_ROM_VERSION",
    "SMBIOS_SMC_VERSION",
    "SMBIOS_CPU_TYPE",
    "SMBIOS_CPU_BRAND",
    "SMBIOS_CPU_SPEED",
    "SMBIOS_PACKAGES",
    "SMBIOS_CORES",
    "SMBIOS_MEMORY",
)

UUID_V4_RE = re.compile(r"^[0-9A-F]{8}-[0-9A-F]{4}-4[0-9A-F]{3}-[89AB][0-9A-F]{3}-[0-9A-F]{12}$")
HEX32_RE = re.compile(r"^[0-9A-F]{32}$")
HEX12_RE = re.compile(r"^[0-9A-F]{12}$")


def _random_chars(alphabet: str, count: int) -> str:
    return "".join(secrets.choice(alphabet) for _ in range(count))


def generate_serial_and_mlb(model_name: str = "MacBookPro16,1") -> tuple[str, str]:
    spec = MODELS.get(model_name, MODELS["MacBookPro16,1"])
    for _ in range(64):
        ppp = secrets.choice(spec["locations"])
        year_code = secrets.choice(spec["year_codes"])
        week_idx = secrets.randbelow(26)  # 0..25 -> weeks 1..26 in half-year
        week_char = WEEK_CHARS[week_idx]
        unique = _random_chars(BASE34_ALPHABET, 3)
        model_code = secrets.choice(spec["model_codes"])
        serial = f"{ppp}{year_code}{week_char}{unique}{model_code}"
        if serial not in BANNED_SERIALS and len(serial) == 12:
            break
    else:
        raise RuntimeError("Failed to generate unbanned serial number")

    year_digit, week_offset = YEAR_CODE_MAP[year_code]
    week_num = week_offset + week_idx + 1
    line_code = secrets.choice(MLB_LINE_CODES)
    copy_code = _random_chars(BASE34_ALPHABET, 3)
    eee_code = secrets.choice(spec["eee_codes"])
    check_char = secrets.choice(BASE34_ALPHABET)
    mlb = f"{ppp}{year_digit}{week_num:02d}{line_code}{copy_code}{eee_code}{check_char}"
    return serial, mlb


def generate_identity(model_name: str = "MacBookPro16,1") -> dict[str, str]:
    if model_name not in MODELS:
        raise ValueError(f"Unsupported model {model_name!r}; choose from {', '.join(MODELS)}")
    spec = MODELS[model_name]
    serial, mlb = generate_serial_and_mlb(model_name)
    for _ in range(64):
        u = uuid.uuid4()
        platform_uuid = str(u).upper()
        if platform_uuid not in BANNED_UUIDS:
            break
    else:
        raise RuntimeError("Failed to generate unbanned UUID")

    system_id = u.bytes_le.hex().upper()
    provisioning_udid = f"00008006-00{system_id[:14]}"
    rom = secrets.choice(APPLE_ROM_OUIS) + secrets.token_bytes(3).hex().upper()

    return {
        "SMBIOS_MODEL": spec["model"],
        "SMBIOS_PRODUCT_NAME": spec["product_name"],
        "SMBIOS_MACHINE_NAME": spec["machine_name"],
        "SMBIOS_MANUFACTURER": "Apple Inc.",
        "SMBIOS_BOARD_ID": spec["board_id"],
        "SMBIOS_BRIDGE_MODEL": spec["bridge_model"],
        "SMBIOS_TARGET_TYPE": "Mac",
        "SMBIOS_SERIAL_NUMBER": serial,
        "SMBIOS_MLB": mlb,
        "SMBIOS_PLATFORM_UUID": platform_uuid,
        "SMBIOS_SYSTEM_ID": system_id,
        "SMBIOS_PROVISIONING_UDID": provisioning_udid,
        "SMBIOS_ROM": rom,
        "SMBIOS_BOOT_ROM_VERSION": spec["boot_rom_version"],
        "SMBIOS_SMC_VERSION": spec["smc_version"],
        "SMBIOS_CPU_TYPE": spec["cpu_type"],
        "SMBIOS_CPU_BRAND": spec["cpu_brand"],
        "SMBIOS_CPU_SPEED": spec["cpu_speed"],
        "SMBIOS_PACKAGES": spec["packages"],
        "SMBIOS_CORES": spec["cores"],
        "SMBIOS_MEMORY": spec["memory"],
    }


def is_valid_config(cfg: dict[str, str]) -> bool:
    if not all(cfg.get(k) for k in CONFIG_KEYS):
        return False
    serial = cfg["SMBIOS_SERIAL_NUMBER"]
    mlb = cfg["SMBIOS_MLB"]
    platform_uuid = cfg["SMBIOS_PLATFORM_UUID"]
    system_id = cfg["SMBIOS_SYSTEM_ID"]
    rom = cfg["SMBIOS_ROM"]

    if len(serial) != 12 or serial in BANNED_SERIALS:
        return False
    if any(ch in ("I", "O") or not (ch.isdigit() or ch.isupper()) for ch in serial):
        return False
    if len(mlb) != 17 or any(ch in ("I", "O") or not (ch.isdigit() or ch.isupper()) for ch in mlb):
        return False
    # Verify factory prefix and manufacturing year/week consistency when year code is standard
    if mlb[:3] != serial[:3]:
        return False
    year_code = serial[3]
    week_char = serial[4]
    if year_code in YEAR_CODE_MAP and week_char in WEEK_CHARS[:26]:
        expected_year_digit, week_offset = YEAR_CODE_MAP[year_code]
        expected_week = f"{week_offset + WEEK_CHARS.index(week_char) + 1:02d}"
        if mlb[3] != expected_year_digit or mlb[4:6] != expected_week:
            return False

    if platform_uuid in BANNED_UUIDS or not UUID_V4_RE.match(platform_uuid):
        return False
    if not HEX32_RE.match(system_id):
        return False
    try:
        if uuid.UUID(platform_uuid).bytes_le.hex().upper() != system_id:
            return False
    except ValueError:
        return False
    if not HEX12_RE.match(rom):
        return False
    return True


def read_config(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        result[key] = value
    return result


SYSTEM_VERSION_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
\t<key>ProductBuildVersion</key>
\t<string>23H124</string>
\t<key>ProductCopyright</key>
\t<string>1983-2024 Apple Inc.</string>
\t<key>ProductName</key>
\t<string>macOS</string>
\t<key>ProductUserVisibleVersion</key>
\t<string>14.7</string>
\t<key>ProductVersion</key>
\t<string>14.7</string>
\t<key>iOSSupportVersion</key>
\t<string>14.7</string>
</dict>
</plist>
"""

SYSTEM_VERSION_COMPAT_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
\t<key>ProductBuildVersion</key>
\t<string>23H124</string>
\t<key>ProductCopyright</key>
\t<string>1983-2024 Apple Inc.</string>
\t<key>ProductName</key>
\t<string>Mac OS X</string>
\t<key>ProductUserVisibleVersion</key>
\t<string>10.16</string>
\t<key>ProductVersion</key>
\t<string>10.16</string>
\t<key>iOSSupportVersion</key>
\t<string>14.7</string>
</dict>
</plist>
"""


def sync_system_version_plists(prefix: Path) -> None:
    cs_dir = prefix / "System/Library/CoreServices"
    if cs_dir.is_dir():
        sys_ver = cs_dir / "SystemVersion.plist"
        try:
            sys_ver.write_text(SYSTEM_VERSION_PLIST, encoding="utf-8")
        except Exception:
            pass
        sys_compat = cs_dir / "SystemVersionCompat.plist"
        try:
            sys_compat.write_text(SYSTEM_VERSION_COMPAT_PLIST, encoding="utf-8")
        except Exception:
            pass


def format_config(cfg: dict[str, str]) -> str:
    lines = [
        "# Generated by tools/gen-darling-smbios.py (GenSMBIOS / macserial compatible)",
        "# Used by Darling iokitd (IOPlatformExpertDevice / IODeviceTree) and system_profiler.",
    ]
    for key in CONFIG_KEYS:
        val = cfg.get(key, "")
        if any(c in val for c in " ();"):
            lines.append(f'{key}="{val}"')
        else:
            lines.append(f"{key}={val}")
    return "\n".join(lines) + "\n"


def write_config_to_prefix(prefix: Path, cfg: dict[str, str]) -> Path:
    private_etc = prefix / "private/etc"
    private_etc.mkdir(parents=True, exist_ok=True)
    target = private_etc / "darling-smbios.conf"
    staged = private_etc / f".darling-smbios.conf.tmp-{os.getpid()}"
    content = format_config(cfg)
    staged.write_text(content, encoding="utf-8")
    staged.chmod(0o644)
    os.replace(staged, target)

    # Mirror into prefix/etc when prefix/etc is a real directory shadowing private/etc
    etc_dir = prefix / "etc"
    if etc_dir.is_dir() and not etc_dir.is_symlink():
        etc_target = etc_dir / "darling-smbios.conf"
        etc_staged = etc_dir / f".darling-smbios.conf.tmp-{os.getpid()}"
        etc_staged.write_text(content, encoding="utf-8")
        etc_staged.chmod(0o644)
        os.replace(etc_staged, etc_target)

    sync_system_version_plists(prefix)

    return target


def import_gensmbios_file(source_path: Path, default_model: str = "MacBookPro16,1") -> dict[str, str]:
    raw = source_path.read_bytes()
    data = None
    try:
        data = plistlib.loads(raw)
    except Exception:
        data = json.loads(raw.decode("utf-8"))

    # Support OpenCore PlatformInfo -> Generic plist/JSON or flat GenSMBIOS JSON
    generic = data
    if isinstance(data, dict):
        if "PlatformInfo" in data and isinstance(data["PlatformInfo"], dict):
            generic = data["PlatformInfo"].get("Generic", data["PlatformInfo"])
        elif "Generic" in data and isinstance(data["Generic"], dict):
            generic = data["Generic"]

    if not isinstance(generic, dict):
        raise ValueError(f"Unrecognized GenSMBIOS / OpenCore structure in {source_path}")

    model_name = (
        generic.get("SystemProductName")
        or generic.get("Type")
        or generic.get("model")
        or default_model
    )
    if model_name not in MODELS:
        raise ValueError(f"Unsupported model {model_name!r} in {source_path}; choose from {', '.join(MODELS)}")
    cfg = generate_identity(model_name)

    serial = generic.get("SystemSerialNumber") or generic.get("Serial") or generic.get("SMBIOS_SERIAL_NUMBER")
    mlb = generic.get("MLB") or generic.get("Board Serial") or generic.get("SMBIOS_MLB")
    smuuid = generic.get("SystemUUID") or generic.get("SmUUID") or generic.get("SMBIOS_PLATFORM_UUID")
    rom = generic.get("ROM") or generic.get("SMBIOS_ROM")

    if serial:
        cfg["SMBIOS_SERIAL_NUMBER"] = str(serial).strip().upper()
    if mlb:
        cfg["SMBIOS_MLB"] = str(mlb).strip().upper()
    if smuuid:
        u = uuid.UUID(str(smuuid).strip())
        cfg["SMBIOS_PLATFORM_UUID"] = str(u).upper()
        cfg["SMBIOS_SYSTEM_ID"] = u.bytes_le.hex().upper()
        cfg["SMBIOS_PROVISIONING_UDID"] = f"00008006-00{cfg['SMBIOS_SYSTEM_ID'][:14]}"
    if isinstance(rom, (bytes, bytearray)):
        cfg["SMBIOS_ROM"] = bytes(rom[:6]).hex().upper()
    elif isinstance(rom, str) and rom.strip():
        clean_rom = rom.strip().replace(":", "").replace("-", "").upper()
        if len(clean_rom) == 12:
            cfg["SMBIOS_ROM"] = clean_rom
    if not is_valid_config(cfg):
        raise ValueError(f"Imported SMBIOS identity from {source_path} is invalid and would be regenerated on next start")
    return cfg


def ensure_smbios(prefix: Path, model_name: str = "MacBookPro16,1", regenerate: bool = False) -> tuple[dict[str, str], bool]:
    conf_path = prefix / "private/etc/darling-smbios.conf"
    if not regenerate:
        existing = read_config(conf_path)
        if is_valid_config(existing):
            sync_system_version_plists(prefix)
            etc_dir = prefix / "etc"
            need_sync = (
                etc_dir.is_dir() and not etc_dir.is_symlink() and not (etc_dir / "darling-smbios.conf").is_file()
            )
            if need_sync:
                write_config_to_prefix(prefix, existing)
            return existing, False
    cfg = generate_identity(model_name)
    write_config_to_prefix(prefix, cfg)
    return cfg, True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prefix",
        type=Path,
        default=Path(os.environ.get("DPREFIX", str(Path.home() / ".darling"))),
        help="Darling prefix path (default: $DPREFIX or ~/.darling)",
    )
    parser.add_argument(
        "--model",
        default="MacBookPro16,1",
        help="Mac model identifier to generate (default: MacBookPro16,1)",
    )
    parser.add_argument(
        "--ensure",
        action="store_true",
        help="Provision SMBIOS config only if missing or using a banned/invalid identity",
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Force generation of a new SMBIOS serial, MLB, UUID, and ROM",
    )
    parser.add_argument(
        "--from-gensmbios",
        type=Path,
        metavar="FILE",
        help="Import SMBIOS fields from a GenSMBIOS JSON or OpenCore config.plist",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Display the active SMBIOS identity without modifying it",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print SMBIOS configuration as JSON",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List supported Mac models",
    )
    args = parser.parse_args(argv)

    if args.list_models:
        for name, spec in MODELS.items():
            print(f"{name:16s}  board-id={spec['board_id']}  cpu={spec['cpu_type']}")
        return 0

    prefix = args.prefix.expanduser()
    conf_path = prefix / "private/etc/darling-smbios.conf"

    if args.show and not args.regenerate and not args.ensure and not args.from_gensmbios:
        cfg = read_config(conf_path)
        if not cfg:
            cfg = generate_identity(args.model)
    elif args.from_gensmbios:
        cfg = import_gensmbios_file(args.from_gensmbios, default_model=args.model)
        write_config_to_prefix(prefix, cfg)
    else:
        cfg, created = ensure_smbios(prefix, model_name=args.model, regenerate=args.regenerate)
        if created and not args.json:
            print(
                f"Provisioned Darling SMBIOS ({cfg['SMBIOS_MODEL']} serial={cfg['SMBIOS_SERIAL_NUMBER']} uuid={cfg['SMBIOS_PLATFORM_UUID']})",
                flush=True,
            )

    if args.json:
        print(json.dumps(cfg, indent=2))
    elif args.show or args.regenerate or args.from_gensmbios:
        for key in CONFIG_KEYS:
            if key in cfg:
                print(f"{key}={cfg[key]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
