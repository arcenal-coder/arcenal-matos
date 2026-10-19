#!/usr/bin/env python3
"""Cross-repository contract check. Pass the native ARCenal Agent package directory.

Uses a disposable Django test database and real implementations at both ends.
Only the HTTP transports are replaced; route/auth tests run in each repository.
"""
# Django must be initialized before importing application models.
# ruff: noqa: E402
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "matos.settings")
os.environ.setdefault("MATOS_DEBUG", "1")
os.environ.setdefault("MATOS_DEV_LOGIN", "1")

if len(sys.argv) != 2:
    raise SystemExit("Usage: .venv/bin/python scripts/verify_agent_pairing.py <native-ARCenal-Agent-package-directory>")
package = Path(sys.argv.pop())
AGENT = package / "conf/arcenal_assistance/store.py"
SPEC = importlib.util.spec_from_file_location("central_assistance_contract", AGENT)
central = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(central)

import django

django.setup()
from django.test import TestCase, override_settings
from django.test.runner import DiscoverRunner

from core import agent_pairing
from core.models import AssistanceSettings, ModuleSettings
from core.tests.test_workflows import Fixtures


@override_settings(DEBUG=True, DEV_LOGIN=True)
class CrossContract(Fixtures, TestCase):
    def test_pair_open_revalidate_revoke_and_replay(self):
        self.setup_data()
        ModuleSettings.objects.create(pk=1, epi_enabled=True)
        AssistanceSettings.objects.create(pk=1)
        self.client.force_login(self.admin, backend="core.auth.DisabledPasswordBackend")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            key = "isolated-cross-contract-key-123456789012345678901234567890"
            (root / ".assistance.json").write_text(json.dumps({"application": "arcenal-matos", "key": key,
                "service_url": "https://agent.example.test/assistance/service", "sso_url": "https://agent.example.test/assistance/"}))
            config = root / "agent.json"
            config.write_text(json.dumps({"applications": {"arcenal-matos": {"key": key, "verify_url": "https://matos.example.test/integration/assistance/verify/"}},
                "state_dir": str(root / "state"), "proxy_key": "test-only-proxy-key"}))

            def transport(operation, **values):
                entry = central.authenticate("arcenal-matos", "Bearer " + agent_pairing.configuration()["key"])
                return central.exchange("arcenal-matos", entry, {"application": "arcenal-matos", "operation": operation, **values})

            def callback(url, supplied_key, data):
                response = self.client.post("/integration/assistance/verify/", data=json.dumps(data), content_type="application/json", HTTP_AUTHORIZATION="Bearer " + supplied_key)
                if response.status_code != 200:
                    raise central.LinkError("Source authorization denied")
                return response.json()

            with override_settings(BASE_DIR=root), \
                    patch.object(central, "CONFIG", config), patch.object(agent_pairing, "exchange", side_effect=transport), \
                    patch.object(central, "post_json", side_effect=callback):
                response = self.client.post("/integration/pairing/", {"operation": "pair", "confirmed": "on"})
                self.assertEqual(response.status_code, 303)
                pair = agent_pairing.local_pair()
                self.assertEqual(agent_pairing.status(), "pending")
                nonce = central.prepare_confirmation(pair, "central-admin")
                central.confirm(pair, "central-admin", nonce, "approve")
                self.assertEqual(agent_pairing.status(), "active")
                self.client.force_login(self.member, backend="core.auth.DisabledPasswordBackend")
                response = self.client.post("/integration/assistance/epi/")
                reference = response["Location"].split("reference=")[1]
                self.assertEqual(central.receive(reference, self.member.username)["resource_id"], "epi")
                with self.assertRaises(central.LinkError):
                    central.receive(reference, self.member.username)
                response = self.client.post("/integration/assistance/epi/")
                reference = response["Location"].split("reference=")[1]
                ModuleSettings.objects.filter(pk=1).update(epi_enabled=False)
                with self.assertRaises(central.LinkError):
                    central.receive(reference, self.member.username)
                agent_pairing.revoke()
                self.assertEqual(agent_pairing.status(), "disconnected")
                self.assertEqual(transport("status", pair_id=pair)["state"], "revoked")


if __name__ == "__main__":
    failures = DiscoverRunner(verbosity=2, interactive=False).run_tests(["__main__.CrossContract"])
    raise SystemExit(bool(failures))
