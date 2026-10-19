from urllib.parse import urlsplit

import yaml
from django.test import Client, TestCase, override_settings

from core.agent_links import context_for, validate_destination
from core.models import Asset, AssistanceSettings, Event, ModuleSettings, User
from core.tests.test_workflows import Fixtures


@override_settings(DEBUG=True, DEV_LOGIN=True, MCP_TOKEN="private-sso-fixture-never-transmit")
class AgentAssistanceSSO(Fixtures, TestCase):
    def setUp(self):
        self.setup_data()
        self.client.force_login(self.admin, backend="core.auth.DisabledPasswordBackend")
        ModuleSettings.objects.create(pk=1, epi_enabled=True, dosimeters_enabled=True)
        self.config = AssistanceSettings.objects.create(pk=1, sso_url="", enabled=True)

    def configure(self, value="https://agent.example.test/"):
        self.config.sso_url = value
        self.config.save(update_fields=["sso_url"])

    def test_no_destination_means_disabled_controls_and_no_invented_localhost(self):
        page = self.client.get("/integration/")
        self.assertContains(page, "Demander à ARCenal Agent", count=3)
        self.assertContains(page, "Liaison d’assistance à activer", count=3)
        self.assertEqual(self.client.post("/integration/assistance/materiel/").status_code, 409)
        self.assertFalse(Event.objects.filter(action="agent.assistance_opened").exists())

    def test_server_derived_context_and_session_only_navigation_without_payload(self):
        self.configure()
        context = context_for(self.admin, "epi")
        self.assertEqual((context.application, context.user_id, context.intention, context.resource_type, context.resource_id),
            ("arcenal-matos", self.admin.pk, "read_only_help", "module", "epi"))
        response = self.client.post("/integration/assistance/epi/")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response["Location"], "https://agent.example.test/")
        self.assertEqual(urlsplit(response["Location"]).query, "")
        self.assertEqual(urlsplit(response["Location"]).fragment, "")
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        self.assertEqual(response["Cache-Control"], "private, no-store")
        event = Event.objects.get(action="agent.assistance_opened")
        self.assertEqual(set(event.details), {"application", "intention", "resource_type", "module", "delivery"})
        self.assertNotIn(self.admin.username, str(event.details))
        self.assertNotIn("https://", str(event.details))
        self.assertNotIn("private-sso-fixture-never-transmit", str(event.details))

    def test_forged_expired_context_and_central_actions_are_not_accepted(self):
        self.configure()
        before = list(Asset.objects.values_list("code", "name"))
        for body in ({"user_id": self.member.pk}, {"context": "forged"}, {"context_ref": "expired", "expires": "2000-01-01"},
                     {"action": "update_asset", "target": "PC-1"}, {"next": "https://other.example.test/"}):
            self.assertEqual(self.client.post("/integration/assistance/materiel/", body).status_code, 400)
        self.assertEqual(self.client.post("/integration/assistance/materiel/?context_ref=expired").status_code, 400)
        self.assertEqual(list(Asset.objects.values_list("code", "name")), before)
        self.assertFalse(Event.objects.filter(action="agent.assistance_opened").exists())

    def test_roles_and_module_activation_are_rechecked(self):
        self.configure("/published-agent/")
        for user in (self.admin, self.manager, self.member):
            self.client.force_login(user, backend="core.auth.DisabledPasswordBackend")
            self.assertEqual(self.client.post("/integration/assistance/materiel/").status_code, 303)
        for user in (self.agent, User.objects.create(username="unassigned-help", role="unassigned")):
            self.client.force_login(user, backend="core.auth.DisabledPasswordBackend")
            self.assertEqual(self.client.post("/integration/assistance/materiel/").status_code, 403)
        self.client.force_login(self.admin, backend="core.auth.DisabledPasswordBackend")
        ModuleSettings.objects.filter(pk=1).update(epi_enabled=False, dosimeters_enabled=False)
        self.assertEqual(self.client.post("/integration/assistance/epi/").status_code, 404)
        self.assertEqual(self.client.post("/integration/assistance/dosimetres/").status_code, 404)
        self.assertEqual(self.client.post("/integration/assistance/unknown/").status_code, 404)

    def test_destination_rejects_credentials_parameters_fragments_and_browser_loopback(self):
        invalid = ["http://localhost:8000/", "https://localhost/", "https://127.0.0.1/", "https://[::1]/", "//other.example.test/",
                   "https://user:private-password-value@agent.example.test/", "https://agent.example.test/?token=private-password-value",
                   "https://agent.example.test/#dossier", "/agent/%3Ftoken", "/agent/\\other", "javascript:alert(1)"]
        for value in invalid:
            response = self.client.post("/integration/", {"form": "sso", "sso_url": value})
            self.assertEqual(response.status_code, 200)
            self.config.refresh_from_db()
            self.assertEqual(self.config.sso_url, "")
            self.assertNotContains(response, "private-password-value")
        self.assertEqual(validate_destination("/published-agent/"), "/published-agent/")
        self.assertEqual(validate_destination("https://agent.example.test/"), "https://agent.example.test/")

    def test_configuration_is_admin_only_and_does_not_change_legacy_mcp_setting(self):
        self.assertRedirects(self.client.post("/integration/", {"form": "sso", "sso_url": "/published-agent/"}), "/integration/")
        self.config.refresh_from_db()
        self.assertTrue(self.config.enabled)
        self.client.post("/integration/", {"form": "mcp"})
        self.config.refresh_from_db()
        self.assertFalse(self.config.enabled)
        self.assertEqual(self.config.sso_url, "/published-agent/")
        response = self.client.get("/integration/?download=1")
        self.assertEqual(yaml.safe_load(response.content)["agent_profile"]["name"], "logisticien-arcenal-matos")
        for user in (self.manager, self.member):
            self.client.force_login(user, backend="core.auth.DisabledPasswordBackend")
            self.assertEqual(self.client.post("/integration/", {"form": "sso", "sso_url": "/other/"}).status_code, 403)

    def test_csrf_and_expired_session_cannot_open_assistance(self):
        self.configure()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin, backend="core.auth.DisabledPasswordBackend")
        self.assertEqual(client.post("/integration/assistance/materiel/").status_code, 403)
        session = self.client.session
        session.set_expiry(-1)
        session.save()
        self.assertEqual(self.client.post("/integration/assistance/materiel/").status_code, 302)
        self.assertFalse(Event.objects.filter(action="agent.assistance_opened").exists())
