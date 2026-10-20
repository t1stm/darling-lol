import os
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestLeagueLauncher(unittest.TestCase):
    def setUp(self):
        self.desktop_repo = REPO_ROOT / "launchers/league.desktop"
        self.launch_script = REPO_ROOT / "scripts/launch-fork.sh"

    def test_launch_script_exists_and_executable(self):
        """Verify launch script exists and is executable."""
        self.assertTrue(self.launch_script.is_file(), "scripts/launch-fork.sh must exist")
        self.assertTrue(os.access(self.launch_script, os.X_OK), "scripts/launch-fork.sh must be executable")

    def test_desktop_file_exists_and_valid(self):
        """Verify launchers/league.desktop has Name=League and required fields."""
        self.assertTrue(self.desktop_repo.is_file(), "launchers/league.desktop must exist")
        content = self.desktop_repo.read_text()
        self.assertIn("Name=League", content)
        self.assertIn("Icon=league", content)
        self.assertIn("StartupWMClass=Riot Client", content)

    def test_fork_launcher_dry_run(self):
        """Verify running launch script with --dry-run passes without executing game."""
        res = subprocess.run([str(self.launch_script), "--dry-run"], capture_output=True, text=True, check=False)
        self.assertEqual(res.returncode, 0, f"--dry-run failed: {res.stderr}")
        self.assertIn("[DRY-RUN] Fork Launcher Validation", res.stdout)

    def test_upstream_launcher_blocks_unshielded_by_default(self):
        """Verify launch-upstream.sh blocks execution by default to protect against bans."""
        upstream_script = REPO_ROOT / "scripts/launch-upstream.sh"
        self.assertTrue(upstream_script.is_file())
        self.assertTrue(os.access(upstream_script, os.X_OK))
        res = subprocess.run([str(upstream_script)], capture_output=True, text=True, check=False)
        self.assertEqual(res.returncode, 1)
        self.assertIn("CRITICAL SAFETY WARNING: UNSHIELDED UPSTREAM LAUNCHER BLOCKED", res.stderr)

    def test_upstream_launcher_dry_run(self):
        """Verify launch-upstream.sh --dry-run succeeds without unshielded execution."""
        upstream_script = REPO_ROOT / "scripts/launch-upstream.sh"
        res = subprocess.run([str(upstream_script), "--dry-run"], capture_output=True, text=True, check=False)
        self.assertEqual(res.returncode, 0)
        self.assertIn("[DRY-RUN] Upstream Main Launcher Validation", res.stdout)

    def test_upstream_launcher_help(self):
        """Verify launch-upstream.sh --help outputs usage without blocking."""
        upstream_script = REPO_ROOT / "scripts/launch-upstream.sh"
        res = subprocess.run([str(upstream_script), "--help"], capture_output=True, text=True, check=False)
        self.assertEqual(res.returncode, 0)
        self.assertIn("League of Legends - Darling Upstream Main Launcher", res.stdout)
        self.assertIn("--allow-unshielded-telemetry", res.stdout)

    def test_desktop_launchers_exist_and_warn(self):
        """Verify desktop launcher entries exist and upstream contains anti-cheat warning."""
        upstream_desktop = REPO_ROOT / "launchers/league-of-legends-upstream.desktop"
        fork_desktop = REPO_ROOT / "launchers/league-of-legends-fork.desktop"
        self.assertTrue(upstream_desktop.is_file())
        self.assertTrue(fork_desktop.is_file())
        up_text = upstream_desktop.read_text()
        fork_text = fork_desktop.read_text()
        self.assertIn("Warning: Upstream Main lacks anti-cheat spoofing", up_text)
        self.assertIn("with Spoofing & Stealth", fork_text)


if __name__ == "__main__":
    unittest.main()
