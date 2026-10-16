from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from core.models import ModuleSettings, Notification
from core.modules import enabled
from core.tests.test_workflows import Fixtures
from core.views import agent_yaml
from dosimetry.models import Badge
from epi import services
from epi.models import Allocation, Lot, Reference


@override_settings(DEBUG=True, DEV_LOGIN=True, MCP_TOKEN="modules-test-only-credential")
class OptionalModuleTests(Fixtures, TestCase):
    def setUp(self):
        self.setup_data()
        self.client.force_login(self.admin, backend="core.auth.DisabledPasswordBackend")

    def test_defaults_preserve_epi_and_keep_dosimeters_opt_in(self):
        self.assertTrue(enabled("epi"))
        self.assertFalse(enabled("dosimeters"))
        self.assertEqual(self.client.get("/epi/").status_code, 200)
        self.assertEqual(self.client.get("/dosimeters/").status_code, 404)
        self.assertContains(self.client.get("/settings/modules/"), "Activer le module Dosimètres passifs")

    def test_flags_are_independent_and_both_can_be_off(self):
        self.client.post("/settings/modules/", {"dosimeters_enabled": "on"})
        self.assertFalse(enabled("epi"))
        self.assertTrue(enabled("dosimeters"))
        self.assertEqual(self.client.get("/epi/").status_code, 404)
        self.assertEqual(self.client.get("/dosimeters/").status_code, 200)
        self.client.post("/settings/modules/", {"epi_enabled": "on"})
        self.assertTrue(enabled("epi"))
        self.assertFalse(enabled("dosimeters"))
        self.client.post("/settings/modules/", {})
        self.assertFalse(enabled("epi"))
        self.assertFalse(enabled("dosimeters"))
        self.assertEqual(self.client.get("/inventory/").status_code, 200)
        self.assertEqual(self.client.get("/settings/modules/").status_code, 200)
        self.assertNotContains(self.client.get("/"), 'href="/epi/"')
        self.assertNotContains(self.client.get("/"), 'href="/dosimeters/"')

    def test_only_admin_can_change_activation(self):
        for user in (self.manager, self.member):
            self.client.force_login(user, backend="core.auth.DisabledPasswordBackend")
            self.assertEqual(self.client.get("/settings/modules/").status_code, 403)
            self.assertEqual(self.client.post("/settings/modules/", {"dosimeters_enabled": "on"}).status_code, 403)
        self.assertFalse(enabled("dosimeters"))

    def test_disabled_epi_blocks_mutations_and_reminders_without_deleting_history(self):
        reference = Reference.objects.create(name="EPI conservé", kind="Test")
        lot = services.receive(self.manager, reference, self.site, "LOT", self.today, 4)
        allocation = services.issue(self.manager, lot.pk, self.member, 1, self.today)
        notification_count = Notification.objects.count()
        self.client.post("/settings/modules/", {})
        with self.assertRaises(ValidationError):
            services.issue(self.manager, lot.pk, self.member, 1, self.today)
        with self.assertRaises(ValidationError):
            services.destroy(self.manager, lot.pk, 1, self.today, "Interdit")
        services.reminders()
        self.assertEqual(Notification.objects.count(), notification_count)
        self.assertTrue(Lot.objects.filter(pk=lot.pk, available_quantity=3).exists())
        self.assertTrue(Allocation.objects.filter(pk=allocation.pk).exists())
        self.client.post("/settings/modules/", {"epi_enabled": "on"})
        self.assertContains(self.client.get("/epi/stock/"), "EPI conservé")
        self.assertEqual(Badge.objects.count(), 0)

    def test_yaml_capabilities_follow_enabled_modules(self):
        ModuleSettings.objects.update_or_create(pk=1, defaults={"epi_enabled": False, "dosimeters_enabled": True})
        data = agent_yaml()
        self.assertNotIn("epi.validity.propose", data["access"]["capabilities"])
        self.assertIn("dosimetry.logistics.prepare", data["access"]["capabilities"])
        self.assertIn("dosimetry.send", data["access"]["human_only"])
        self.assertNotIn("epi.requests.approve", data["access"]["human_only"])
