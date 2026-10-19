import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core import signing
from django.test import TestCase, override_settings

from core import agent_pairing
from core.models import AssistanceSettings, ModuleSettings
from core.tests.test_workflows import Fixtures


@override_settings(DEBUG=True, DEV_LOGIN=True)
class AgentPairing(Fixtures, TestCase):
    def setUp(self):
        self.setup_data()
        self.client.force_login(self.admin, backend="core.auth.DisabledPasswordBackend")
        ModuleSettings.objects.create(pk=1, epi_enabled=True)
        AssistanceSettings.objects.create(pk=1)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = {"application": "arcenal-matos", "key": "test-private-key-never-transmit-to-browser-1234567890",
            "service_url": "https://agent.example.test/arcenal/assistance/service", "sso_url": "https://agent.example.test/arcenal/assistance/"}
        (Path(self.directory.name) / ".assistance.json").write_text(json.dumps(self.config))
        self.setting = override_settings(BASE_DIR=Path(self.directory.name))
        self.setting.enable()
        self.addCleanup(self.setting.disable)

    def ticket(self, module="epi", pair="p" * 43):
        AssistanceSettings.objects.filter(pk=1).update(pair_id=pair)
        return signing.dumps({"user": self.member.username, "module": module, "pair_id": pair}, salt="assistance-v1")

    def callback(self, ticket, **values):
        return self.client.post("/integration/assistance/verify/", data=json.dumps({"ticket": ticket,
            "user": self.member.username, "pair_id": "p" * 43, **values}), content_type="application/json",
            HTTP_AUTHORIZATION="Bearer " + self.config["key"])

    def test_consent_required_admin_only_and_pair_opaque(self):
        with patch.object(agent_pairing, "exchange", return_value={"state": "pending", "pair_id": "p" * 43}) as call:
            self.assertEqual(self.client.post("/integration/pairing/", {"operation": "pair"}).status_code, 409)
            call.assert_not_called()
            response = self.client.post("/integration/pairing/", {"operation": "pair", "confirmed": "on"})
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response["Location"], self.config["sso_url"] + "?pair=" + "p" * 43)
            self.assertNotIn(self.config["key"], str(response.headers))
            self.client.force_login(self.manager, backend="core.auth.DisabledPasswordBackend")
            self.assertEqual(self.client.post("/integration/pairing/", {"operation": "pair", "confirmed": "on"}).status_code, 403)

    def test_callback_rechecks_active_user_role_and_module(self):
        ticket = self.ticket()
        response = self.callback(ticket)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["resource_id"], "epi")
        ModuleSettings.objects.filter(pk=1).update(epi_enabled=False)
        self.assertEqual(self.callback(ticket).status_code, 403)
        ModuleSettings.objects.filter(pk=1).update(epi_enabled=True)
        self.member.role = "unassigned"
        self.member.save()
        self.assertEqual(self.callback(ticket).status_code, 403)

    def test_tampering_expiry_wrong_identity_and_revocation(self):
        ticket = self.ticket()
        self.assertEqual(self.callback(ticket + "x").status_code, 403)
        self.assertEqual(self.callback(ticket, user=self.admin.username).status_code, 403)
        self.assertEqual(self.client.post("/integration/assistance/verify/", data="{}", content_type="application/json").status_code, 403)
        with patch("django.core.signing.time.time", return_value=0):
            old = self.ticket()
        self.assertEqual(self.callback(old).status_code, 403)
        with patch.object(agent_pairing, "exchange", side_effect=agent_pairing.PairingUnavailable("Indisponible")):
            self.client.post("/integration/pairing/", {"operation": "revoke"})
        self.assertEqual(agent_pairing.local_pair(), "")
        self.assertEqual(self.callback(ticket).status_code, 403)

    def test_verified_active_state_and_reference_only_navigation(self):
        self.ticket()
        def exchange(operation, **values):
            if operation == "status":
                return {"state": "active"}
            self.assertEqual(operation, "request")
            self.assertEqual(values["user"], self.admin.username)
            self.assertNotIn("resource_id", values)
            return {"reference": "r" * 43}
        with patch.object(agent_pairing, "exchange", side_effect=exchange):
            self.assertContains(self.client.get("/integration/"), "Liaison active")
            response = self.client.post("/integration/assistance/materiel/")
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response["Location"], self.config["sso_url"] + "?reference=" + "r" * 43)
        with patch.object(agent_pairing, "exchange", side_effect=agent_pairing.PairingUnavailable("Indisponible")):
            self.assertNotContains(self.client.get("/integration/"), "Liaison active")
            self.assertEqual(self.client.post("/integration/assistance/materiel/").status_code, 409)
