#!/usr/bin/env python3
"""Install the host-backed system_profiler and SMBIOS identity into the Darling prefix (no sudo)."""
import importlib.util
import os
from pathlib import Path
import shutil

root = Path(__file__).resolve().parent
prefix = Path(os.environ.get("DPREFIX", str(Path.home() / ".darling")))
target = prefix / "usr/sbin/system_profiler"
target.parent.mkdir(parents=True, exist_ok=True)
staged = target.with_name(target.name + ".new")
shutil.copyfile(root / "darling-system_profiler.sh", staged)
staged.chmod(0o755)
staged.replace(target)
print(f"installed {target}")

smbios_helper = root / "gen-darling-smbios.py"
if smbios_helper.is_file():
    spec = importlib.util.spec_from_file_location("gen_darling_smbios", smbios_helper)
    if spec and spec.loader:
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        cfg, created = mod.ensure_smbios(prefix)
        status = "generated" if created else "verified"
        print(f"smbios {status}: {cfg['SMBIOS_MODEL']} serial={cfg['SMBIOS_SERIAL_NUMBER']} uuid={cfg['SMBIOS_PLATFORM_UUID']}")

