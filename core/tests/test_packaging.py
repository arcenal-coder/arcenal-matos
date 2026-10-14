import json
import subprocess
import tomllib
from pathlib import Path

from django.test import SimpleTestCase

from matos.version import VERSION, YUNOHOST_VERSION


class PackagingStructure(SimpleTestCase):
    def test_release_versions_are_consistent(self):
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(json.loads((root / "package.json").read_text())["version"], VERSION)
        lock = json.loads((root / "package-lock.json").read_text())
        self.assertEqual(lock["version"], VERSION)
        self.assertEqual(lock["packages"][""]["version"], VERSION)
        self.assertEqual(tomllib.loads((root / "packaging/ynh/manifest.toml").read_text())["version"], YUNOHOST_VERSION)

    def test_human_route_private_and_agent_route_distinct(self):
        package = Path(__file__).resolve().parents[2] / "packaging" / "ynh"
        manifest = tomllib.loads((package / "manifest.toml").read_text())
        self.assertEqual(manifest["packaging_format"], 2)
        self.assertEqual(manifest["integration"]["helpers_version"], "2.1")
        self.assertEqual(manifest["install"]["init_main_permission"]["default"], "all_users")
        self.assertEqual(manifest["resources"]["database"]["type"], "postgresql")
        self.assertTrue(manifest["resources"]["permissions"]["main"]["protected"])
        self.assertFalse(manifest["resources"]["permissions"]["mcp"]["auth_header"])
        env = (package / "conf/.env").read_text()
        self.assertIn("MATOS_DEV_LOGIN=0", env)
        self.assertIn("MATOS_DEBUG=0", env)
        self.assertIn("MATOS_MCP_TOKEN=__MCP_TOKEN__", env)

    def test_lifecycle_scripts_parse_and_use_official_helpers(self):
        package = Path(__file__).resolve().parents[2] / "packaging" / "ynh"
        for name in ("install", "remove", "upgrade", "backup", "restore", "_common.sh"):
            script = package / "scripts" / name
            result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('ynh_setup_source --dest_dir="$install_dir"', (package / "scripts/install").read_text())
