import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

import httpx
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections, connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from core.models import Asset, AssistanceSettings, ModuleSettings, Notification, Outbox, User
from core.tests.test_workflows import Fixtures

from . import services
from .models import AssistanceTask, Badge, Laboratory, Movement, Period, Shipment


class DosimetryFixtures(Fixtures):
    def dosimetry_setup(self):
        self.setup_data()
        ModuleSettings.objects.update_or_create(pk=1, defaults={"epi_enabled": True, "dosimeters_enabled": True})
        self.laboratory = Laboratory.objects.create(name="Laboratoire de test", address="Adresse logistique")
        self.period = Period.objects.create(name="Période de test", laboratory=self.laboratory,
            start_on=self.today - timedelta(days=10), end_on=self.today + timedelta(days=20), return_due_on=self.today + timedelta(days=25))

    def receive(self, code="BG-01", **kwargs):
        return services.receive(kwargs.get("actor", self.manager), kwargs.get("site", self.site), kwargs.get("period", self.period),
            [code], kwargs.get("received_on", self.today - timedelta(days=12)), kwargs.get("kind", "personal"),
            assigned_to=kwargs.get("assigned_to"))[0]


@override_settings(DEBUG=True, DEV_LOGIN=True, MCP_TOKEN="dosimetry-test-only-credential")
class PassiveBadgeRules(DosimetryFixtures, TestCase):
    def setUp(self):
        self.dosimetry_setup()
        self.client.force_login(self.manager, backend="core.auth.DisabledPasswordBackend")

    def test_complete_logistic_flow_preserves_history_without_general_assets(self):
        assets = Asset.objects.count()
        badge = self.receive()
        services.preassign(self.manager, badge.pk, self.member)
        services.issue(self.manager, badge.pk, self.today, self.member)
        services.collect(self.manager, [badge.pk], self.today)
        shipment = services.send(self.manager, [badge.pk], self.today, "TRACK-01")
        badge.refresh_from_db()
        self.assertEqual((badge.status, badge.assigned_to_id, badge.shipment_id), ("sent", self.member.pk, shipment.pk))
        self.assertEqual(badge.received_on, self.today - timedelta(days=12))
        self.assertEqual(badge.issued_on, self.today)
        self.assertEqual(badge.collected_on, self.today)
        self.assertEqual(Movement.objects.filter(badge=badge).count(), 5)
        self.assertEqual(Asset.objects.count(), assets)
        self.assertEqual(Outbox.objects.count(), 0)

    def test_number_unique_per_laboratory_period_not_across_periods(self):
        badge = self.receive("AB-01")
        with self.assertRaises(ValidationError):
            self.receive(" ab-01 ")
        another = Period.objects.create(name="Période suivante", laboratory=self.laboratory,
            start_on=self.today + timedelta(days=21), end_on=self.today + timedelta(days=50), return_due_on=self.today + timedelta(days=55))
        other = self.receive("AB-01", period=another)
        self.assertNotEqual(badge.pk, other.pk)
        self.assertEqual(Badge.objects.count(), 2)

    def test_preassignment_is_respected_and_issued_badge_cannot_be_redistributed(self):
        badge = self.receive(assigned_to=self.member)
        colleague = User.objects.create(username="other-person", role="member", site=self.site)
        with self.assertRaises(ValidationError):
            services.preassign(self.manager, badge.pk, colleague)
        with self.assertRaises(ValidationError):
            services.issue(self.manager, badge.pk, self.today, colleague)
        services.issue(self.manager, badge.pk, self.today, self.member)
        with self.assertRaises(ValidationError):
            services.issue(self.manager, badge.pk, self.today, self.member)

    def test_witness_stays_site_based_and_unused_return_is_explicit(self):
        with self.assertRaises(ValidationError):
            self.receive("W-01", kind="witness", assigned_to=self.member)
        witness = self.receive("W-01", kind="witness")
        with self.assertRaises(ValidationError):
            services.issue(self.manager, witness.pk, self.today, self.member)
        services.issue(self.manager, witness.pk, self.today)
        services.collect(self.manager, [witness.pk], self.today)
        witness.refresh_from_db()
        self.assertIsNone(witness.assigned_to_id)
        unused = self.receive("UNUSED")
        with self.assertRaises(ValidationError):
            services.collect(self.manager, [unused.pk], self.today)
        services.collect(self.manager, [unused.pk], self.today, not_worn=True)
        services.send(self.manager, [unused.pk, witness.pk], self.today)
        unused.refresh_from_db()
        self.assertTrue(unused.not_worn)
        self.assertIsNone(unused.issued_on)

    def test_dates_and_expired_period_are_validated(self):
        badge = self.receive()
        with self.assertRaises(ValidationError):
            services.issue(self.manager, badge.pk, self.today + timedelta(days=1), self.member)
        services.issue(self.manager, badge.pk, self.today - timedelta(days=2), self.member)
        with self.assertRaises(ValidationError):
            services.collect(self.manager, [badge.pk], self.today - timedelta(days=3))
        with self.assertRaises(ValidationError):
            services.send(self.manager, [badge.pk], self.today)
        services.collect(self.manager, [badge.pk], self.today)
        with self.assertRaises(ValidationError):
            services.send(self.manager, [badge.pk], self.today - timedelta(days=1))
        old = Period.objects.create(name="Terminée", laboratory=self.laboratory, start_on=self.today - timedelta(days=40),
            end_on=self.today - timedelta(days=10), return_due_on=self.today - timedelta(days=5))
        late = self.receive("OLD", period=old, received_on=self.today - timedelta(days=45))
        with self.assertRaises(ValidationError):
            services.issue(self.manager, late.pk, self.today, self.member)
        services.issue(self.manager, late.pk, self.today - timedelta(days=12), self.member)
        late.refresh_from_db()
        self.assertTrue(late.overdue)

    def test_mixed_shipments_fail_atomically_and_double_send_is_rejected(self):
        one = self.receive("ONE")
        two = self.receive("TWO", actor=self.other_manager, site=self.other)
        services.collect(self.admin, [one.pk], self.today, not_worn=True)
        services.collect(self.admin, [two.pk], self.today, not_worn=True)
        with self.assertRaises(ValidationError):
            services.send(self.admin, [one.pk, two.pk], self.today)
        self.assertEqual(Shipment.objects.count(), 0)
        self.assertEqual(Badge.objects.filter(status="collected").count(), 2)
        services.send(self.manager, [one.pk], self.today)
        with self.assertRaises(ValidationError):
            services.send(self.manager, [one.pk], self.today)
        self.assertEqual(Shipment.objects.count(), 1)

    def test_loss_cancellation_and_replacement_keep_original(self):
        badge = self.receive(assigned_to=self.member)
        with self.assertRaises(ValidationError):
            services.close_badge(self.manager, badge.pk, "lost", self.today, "")
        services.issue(self.manager, badge.pk, self.today, self.member)
        with self.assertRaises(ValidationError):
            services.close_badge(self.manager, badge.pk, "cancelled", self.today, "Ne peut pas effacer une remise")
        services.close_badge(self.manager, badge.pk, "lost", self.today, "Égaré")
        replacement = services.replace(self.manager, badge.pk, "REPLACEMENT", self.today)
        badge.refresh_from_db()
        self.assertEqual((badge.status, replacement.replacement_for_id), ("lost", badge.pk))
        self.assertEqual(replacement.assigned_to_id, self.member.pk)
        self.assertEqual(Badge.objects.count(), 2)
        with self.assertRaises(ValidationError):
            services.issue(self.manager, badge.pk, self.today, self.member)

    def test_period_is_frozen_after_reception_except_return_deadline(self):
        self.receive()
        with self.assertRaises(ValidationError):
            services.save_period(self.admin, {"end_on": self.today + timedelta(days=30)}, self.period.pk)
        services.save_period(self.admin, {"return_due_on": self.today + timedelta(days=40)}, self.period.pk)
        self.period.refresh_from_db()
        self.assertEqual(self.period.return_due_on, self.today + timedelta(days=40))
        with self.assertRaises(ValidationError):
            services.save_period(self.admin, {"return_due_on": self.period.end_on - timedelta(days=1)}, self.period.pk)

    def test_personal_views_and_site_boundaries(self):
        own = self.receive("OWN", assigned_to=self.member)
        other_person = User.objects.create(username="colleague", role="member", site=self.site)
        other = self.receive("PRIVATE-OTHER", assigned_to=other_person)
        self.client.force_login(self.member, backend="core.auth.DisabledPasswordBackend")
        self.assertContains(self.client.get("/dosimeters/mine/"), "OWN")
        self.assertNotContains(self.client.get("/dosimeters/mine/"), "PRIVATE-OTHER")
        self.assertEqual(self.client.get(f"/dosimeters/badges/{own.pk}/").status_code, 200)
        self.assertEqual(self.client.get(f"/dosimeters/badges/{other.pk}/").status_code, 404)
        for path in ("/dosimeters/badges/", "/dosimeters/badges/new/", "/dosimeters/operations/shipment/", "/dosimeters/assistance/", "/dosimeters/configuration/periods/"):
            self.assertEqual(self.client.get(path).status_code, 403, path)
        self.client.force_login(self.other_manager, backend="core.auth.DisabledPasswordBackend")
        self.assertEqual(self.client.get(f"/dosimeters/badges/{own.pk}/").status_code, 404)
        with self.assertRaises(ValidationError):
            services.preassign(self.other_manager, own.pk, self.member)
        with self.assertRaises(PermissionDenied):
            services.issue(self.agent, own.pk, self.today, self.member)

    def test_notifications_are_deduplicated_internal_and_paused_when_disabled(self):
        period = Period.objects.create(name="En retard", laboratory=self.laboratory, start_on=self.today - timedelta(days=30),
            end_on=self.today - timedelta(days=10), return_due_on=self.today - timedelta(days=5))
        badge = self.receive(period=period, received_on=self.today - timedelta(days=35))
        services.issue(self.manager, badge.pk, self.today - timedelta(days=20), self.member)
        ModuleSettings.objects.filter(pk=1).update(dosimeters_enabled=False)
        count = Notification.objects.count()
        services.reminders()
        self.assertEqual(Notification.objects.count(), count)
        ModuleSettings.objects.filter(pk=1).update(dosimeters_enabled=True)
        services.reminders()
        self.assertTrue(Notification.objects.filter(user=self.member, title="Dosimètre attendu au retour").exists())
        count = Notification.objects.count()
        services.reminders()
        self.assertEqual(Notification.objects.count(), count)
        self.assertEqual(Outbox.objects.count(), 0)

    def test_disabled_module_blocks_mutations_and_preserves_badges(self):
        badge = self.receive()
        ModuleSettings.objects.filter(pk=1).update(dosimeters_enabled=False)
        self.assertEqual(self.client.get("/dosimeters/").status_code, 404)
        self.assertEqual(self.client.post(f"/dosimeters/badges/{badge.pk}/issue/", {}).status_code, 404)
        with self.assertRaises(ValidationError):
            services.issue(self.manager, badge.pk, self.today, self.member)
        badge.refresh_from_db()
        self.assertEqual(badge.status, "stock")
        ModuleSettings.objects.filter(pk=1).update(dosimeters_enabled=True)
        self.assertContains(self.client.get("/dosimeters/badges/"), badge.code)

    def test_ai_preparation_has_no_physical_effect_and_human_confirms_assignment(self):
        AssistanceSettings.objects.create(pk=1, enabled=True)
        badge = self.receive()
        task = services.request_assistance(self.manager, self.site, self.period, "assignment", "Badge BG-01 destiné à Alice")
        services.answer_assistance(self.agent, task.pk, "Préaffectation à vérifier", assignments=[{"badge_id": str(badge.pk), "user_id": self.member.pk}])
        badge.refresh_from_db()
        self.assertIsNone(badge.assigned_to_id)
        self.assertEqual(badge.status, "stock")
        self.client.get("/dosimeters/assistance/")
        self.assertRedirects(self.client.post(f"/dosimeters/assistance/{task.pk}/decision/", {"decision": "apply"}), "/dosimeters/assistance/")
        badge.refresh_from_db()
        self.assertEqual((badge.status, badge.assigned_to_id), ("stock", self.member.pk))
        with self.assertRaises(PermissionDenied):
            services.decide_assistance(self.agent, task.pk, True)

    def test_ai_shipping_preparation_is_revalidated_at_physical_confirmation(self):
        AssistanceSettings.objects.create(pk=1, enabled=True)
        badge = self.receive()
        services.collect(self.manager, [badge.pk], self.today, not_worn=True)
        task = services.request_assistance(self.manager, self.site, self.period, "shipment")
        services.answer_assistance(self.agent, task.pk, "Liste des badges collectés", badge_ids=[str(badge.pk)])
        with self.assertRaises(ValidationError):
            services.decide_assistance(self.manager, task.pk, True)
        result = services.send(self.manager, [badge.pk], self.today, "AI-PREP", task.pk)
        task.refresh_from_db()
        self.assertEqual((task.status, result.assistance_id), ("applied", task.pk))

    def test_ai_cannot_suggest_foreign_or_ineligible_badges(self):
        AssistanceSettings.objects.create(pk=1, enabled=True)
        badge = self.receive()
        task = services.request_assistance(self.manager, self.site, self.period, "shipment")
        with self.assertRaises(ValidationError):
            services.answer_assistance(self.agent, task.pk, "Pas encore collecté", badge_ids=[str(badge.pk)])
        foreign = self.receive("FOREIGN", actor=self.other_manager, site=self.other)
        assignment = services.request_assistance(self.manager, self.site, self.period, "assignment")
        with self.assertRaises(ValidationError):
            services.answer_assistance(self.agent, assignment.pk, "Site interdit", assignments=[{"badge_id": str(foreign.pk), "user_id": self.member.pk}])
        self.assertEqual(AssistanceTask.objects.filter(status="pending").count(), 2)

    def test_screens_csrf_invalid_identifiers_and_no_dose_data(self):
        badge = self.receive()
        for path in ("/dosimeters/", "/dosimeters/badges/", "/dosimeters/badges/new/", f"/dosimeters/badges/{badge.pk}/",
                     "/dosimeters/mine/", "/dosimeters/operations/collection/", "/dosimeters/operations/shipment/", "/dosimeters/shipments/",
                     "/dosimeters/history/", "/dosimeters/assistance/"):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.client.force_login(self.admin, backend="core.auth.DisabledPasswordBackend")
        self.assertEqual(self.client.get("/dosimeters/configuration/laboratories/").status_code, 200)
        self.assertEqual(self.client.get("/dosimeters/configuration/periods/").status_code, 200)
        self.assertEqual(self.client.get("/dosimeters/operations/shipment/?assistance=bad").status_code, 404)
        self.assertEqual(self.client.get("/dosimeters/operations/collection/?badge=bad").status_code, 404)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.manager, backend="core.auth.DisabledPasswordBackend")
        self.assertEqual(client.post(f"/dosimeters/badges/{badge.pk}/issue/", {}).status_code, 403)
        self.assertFalse(any("dose" in field.name.lower() for field in Badge._meta.fields))


@override_settings(DEBUG=True, DEV_LOGIN=True, MCP_TOKEN="dosimetry-test-only-credential")
class DosimetryConcurrencyAndMCP(DosimetryFixtures, TransactionTestCase):
    def setUp(self):
        self.dosimetry_setup()

    def race(self, operations):
        barrier = Barrier(2)

        def run(operation):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                operation()
                return True
            except ValidationError:
                return False
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return sorted(pool.map(run, operations))

    def test_duplicate_receipt_is_prevented_under_concurrency(self):
        def receive():
            return self.receive()
        self.assertEqual(self.race([receive, receive]), [False, True])
        self.assertEqual(Badge.objects.count(), 1)

    def test_badge_cannot_be_distributed_twice_concurrently(self):
        badge = self.receive()
        def issue():
            return services.issue(User.objects.get(pk=self.manager.pk), badge.pk, self.today, User.objects.get(pk=self.member.pk))
        self.assertEqual(self.race([issue, issue]), [False, True])
        self.assertEqual(Movement.objects.filter(badge=badge, action="Badge distribué").count(), 1)

    def test_badge_is_not_sent_in_two_parcels(self):
        badge = self.receive()
        services.collect(self.manager, [badge.pk], self.today, not_worn=True)
        def send():
            return services.send(User.objects.get(pk=self.manager.pk), [badge.pk], self.today)
        self.assertEqual(self.race([send, send]), [False, True])
        self.assertEqual(Shipment.objects.count(), 1)

    def test_real_mcp_prepares_without_moving_badges_and_respects_module_switch(self):
        AssistanceSettings.objects.create(pk=1, enabled=True)
        badge = self.receive()
        task = services.request_assistance(self.manager, self.site, self.period, "assignment")

        async def scenario():
            from core.mcp_server import build_server
            from matos.asgi import application
            server = build_server(settings.MCP_ALLOWED_HOSTS, settings.MCP_ALLOWED_ORIGINS)
            with patch("matos.asgi.mcp_http", server.streamable_http_app()):
                async with server.session_manager.run():
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://localhost",
                        headers={"Authorization": "Bearer dosimetry-test-only-credential"}) as client:
                        async with streamable_http_client("http://localhost/mcp", http_client=client) as (read, write, _):
                            async with ClientSession(read, write) as session:
                                await session.initialize()
                                names = {item.name for item in (await session.list_tools()).tools}
                                self.assertNotIn("send_dosimeters", names)
                                self.assertNotIn("collect_dosimeters", names)
                                result = await session.call_tool("read_dosimetry_assistance", {"task_id": str(task.pk)})
                                self.assertEqual(json.loads(result.content[0].text)["badges"][0]["code"], "BG-01")
                                result = await session.call_tool("propose_dosimetry_logistics", {"task_id": str(task.pk), "response": "Préaffectation proposée pour vérification humaine",
                                    "assignments": [{"badge_id": str(badge.pk), "user_id": self.member.pk}]})
                                self.assertFalse(result.isError, result.content)
                                await sync_to_async(ModuleSettings.objects.filter(pk=1).update)(dosimeters_enabled=False)
                                result = await session.call_tool("list_dosimetry_assistance", {})
                                self.assertFalse(json.loads(result.content[0].text)["enabled"])
                                result = await session.call_tool("read_dosimetry_assistance", {"task_id": str(task.pk)})
                                self.assertTrue(result.isError)
        asyncio.run(scenario())
        close_old_connections()
        badge.refresh_from_db()
        task.refresh_from_db()
        self.assertIsNone(badge.assigned_to_id)
        self.assertEqual((badge.status, task.status), ("stock", "ready"))
