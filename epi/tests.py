import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

import httpx
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections, connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from core.models import Asset, AssistanceSettings, Notification, Outbox, User
from core.tests.test_workflows import Fixtures

from . import services
from .models import Allocation, Destruction, Lot, Movement, Reference


class EPIFixtures(Fixtures):
    def epi_setup(self):
        self.setup_data()
        self.bulk = Reference.objects.create(name="Gants de test", kind="Gants", size="M", tracking="bulk", unit="pair", usage_days=30)
        self.individual = Reference.objects.create(name="Harnais de test", kind="Harnais", tracking="individual", usage_days=365)

    def receive(self, reference=None, quantity=20, **extra):
        return services.receive(self.manager, reference or self.bulk, self.site, "LOT-TEST", self.today - timedelta(days=70), quantity,
            manufacturer_expiry=extra.get("expiry", self.today + timedelta(days=365)), unit_price=extra.get("price", Decimal("12.50")))


@override_settings(DEBUG=True, DEV_LOGIN=True, MCP_TOKEN="epi-test-only-credential")
class EPIRules(EPIFixtures, TestCase):
    def setUp(self):
        self.epi_setup()
        self.client.force_login(self.manager, backend="core.auth.DisabledPasswordBackend")

    def test_epi_stock_is_separate_and_twenty_pairs_minus_three_equals_seventeen(self):
        before = Asset.objects.count()
        lot = self.receive()
        allocation = services.issue(self.manager, lot.pk, self.member, 3, self.today)
        lot.refresh_from_db()
        self.assertEqual((lot.available_quantity, allocation.active_quantity), (17, 3))
        self.assertEqual(allocation.cost, Decimal("37.50"))
        self.assertEqual(Asset.objects.count(), before)
        self.assertEqual(Movement.objects.count(), 2)

    def test_accepting_request_does_not_touch_stock_and_partial_issues_keep_remainder(self):
        lot = self.receive()
        request = services.request_epi(self.member, self.bulk, 3, "Renouvellement", self.site)
        services.decide(self.manager, request.pk, True)
        lot.refresh_from_db()
        self.assertEqual(lot.available_quantity, 20)
        services.issue(self.manager, lot.pk, self.member, 2, self.today, request_id=request.pk)
        request.refresh_from_db()
        self.assertEqual((request.status, request.remaining), ("partial", 1))
        services.issue(self.manager, lot.pk, self.member, 1, self.today, request_id=request.pk)
        request.refresh_from_db()
        self.assertEqual((request.status, request.remaining), ("fulfilled", 0))
        with self.assertRaises(ValidationError):
            services.issue(self.manager, lot.pk, self.member, 1, self.today, request_id=request.pk)

    def test_request_refusal_and_cancellation_are_traced(self):
        request = services.request_epi(self.member, self.bulk, 1, "Besoin", self.site)
        with self.assertRaises(ValidationError):
            services.decide(self.manager, request.pk, False)
        services.decide(self.manager, request.pk, False, "Référence à adapter")
        request.refresh_from_db()
        self.assertEqual(request.status, "rejected")
        second = services.request_epi(self.member, self.bulk, 1, "Besoin", self.site)
        with self.assertRaises(ValidationError):
            services.cancel_request(self.manager, second.pk)
        services.cancel_request(self.member, second.pk)
        second.refresh_from_db()
        self.assertEqual(second.status, "cancelled")

    def test_individual_codes_are_unique_and_one_unit_cannot_be_issued_twice(self):
        lot = self.receive(self.individual, 2)
        first, second = list(lot.units.order_by("code"))
        self.assertNotEqual(first.code, second.code)
        services.issue(self.manager, lot.pk, self.member, 1, self.today, unit_id=first.pk)
        with self.assertRaises(ValidationError):
            services.issue(self.manager, lot.pk, self.member, 1, self.today, unit_id=first.pk)
        self.assertEqual(Allocation.objects.filter(unit=first).count(), 1)

    def test_earliest_of_manufacturer_and_usage_deadlines_is_used(self):
        lot = self.receive(expiry=self.today + timedelta(days=10))
        item = services.issue(self.manager, lot.pk, self.member, 1, self.today)
        self.assertEqual(item.valid_until, self.today + timedelta(days=10))
        other = self.receive(expiry=self.today + timedelta(days=300))
        item = services.issue(self.manager, other.pk, self.member, 1, self.today)
        self.assertEqual(item.valid_until, self.today + timedelta(days=30))

    def test_first_use_is_not_reset_and_historical_allocations_keep_real_dates(self):
        lot = self.receive(self.individual, 1)
        unit = lot.units.get()
        unit.first_use_on = self.today - timedelta(days=20)
        unit.save(update_fields=["first_use_on"])
        with self.assertRaises(ValidationError):
            services.issue(self.manager, lot.pk, self.member, 1, self.today, first_use_on=self.today, unit_id=unit.pk)
        allocation = services.issue(self.manager, lot.pk, self.member, 1, self.today, unit_id=unit.pk)
        self.assertEqual(allocation.first_use_on, self.today - timedelta(days=20))
        old = services.issue(self.manager, self.receive().pk, self.member, 1, self.today - timedelta(days=50))
        self.assertTrue(old.expired)
        with self.assertRaises(ValidationError):
            services.issue(self.manager, self.receive().pk, self.member, 1, self.today + timedelta(days=1))

    def test_expired_stock_is_not_distributable_and_unknown_validity_is_explicit(self):
        expired = self.receive(expiry=self.today - timedelta(days=1))
        with self.assertRaises(ValidationError):
            services.issue(self.manager, expired.pk, self.member, 1, self.today)
        self.bulk.usage_days = None
        self.bulk.save()
        unknown = self.receive(expiry=None)
        item = services.issue(self.manager, unknown.pk, self.member, 1, self.today)
        self.assertIsNone(item.valid_until)
        response = self.client.get(f"/epi/lots/{unknown.pk}/")
        self.assertContains(response, "Non renseignée")

    def test_destruction_in_stock_and_in_hands_never_returns_items_to_stock(self):
        lot = self.receive()
        services.destroy(self.manager, lot.pk, 2, self.today, "Emballage dégradé")
        allocation = services.issue(self.manager, lot.pk, self.member, 3, self.today)
        services.destroy(self.manager, lot.pk, 1, self.today, "Usure", allocation_id=allocation.pk)
        lot.refresh_from_db()
        allocation.refresh_from_db()
        self.assertEqual((lot.available_quantity, allocation.active_quantity), (15, 2))
        self.assertEqual(Destruction.objects.count(), 2)
        with self.assertRaises(ValidationError):
            services.destroy(self.manager, lot.pk, 3, self.today, "Trop", allocation_id=allocation.pk)
        with self.assertRaises(ValidationError):
            services.destroy(self.manager, lot.pk, 1, self.today, "")

    def test_destroyed_individual_is_not_destroyed_twice(self):
        lot = self.receive(self.individual, 2)
        unit = lot.units.order_by("code").first()
        allocation = services.issue(self.manager, lot.pk, self.member, 1, self.today, unit_id=unit.pk)
        services.destroy(self.manager, lot.pk, 1, self.today, "Retrait", allocation_id=allocation.pk)
        with self.assertRaises(ValidationError):
            services.destroy(self.manager, lot.pk, 1, self.today, "Encore", unit_id=unit.pk)
        self.assertEqual(Destruction.objects.filter(unit=unit).count(), 1)

    def test_prices_are_snapshots_and_unknown_is_not_zero(self):
        lot = self.receive()
        allocation = services.issue(self.manager, lot.pk, self.member, 3, self.today)
        Lot.objects.filter(pk=lot.pk).update(unit_price=Decimal("99.99"))
        destroyed = services.destroy(self.manager, lot.pk, 1, self.today, "Usure", allocation_id=allocation.pk)
        allocation.refresh_from_db()
        self.assertEqual(allocation.cost, Decimal("37.50"))
        self.assertEqual(destroyed.cost, Decimal("12.50"))
        self.assertIsNone(self.receive(price=None).stock_value)
        self.assertEqual(self.receive(price=Decimal("0.00")).stock_value, Decimal("0.00"))

    def test_foreign_sites_and_agent_cannot_manage_stock(self):
        lot = self.receive()
        for actor in (self.member, self.agent, self.other_manager):
            with self.assertRaises((PermissionDenied, ValidationError)):
                services.issue(actor, lot.pk, self.member, 1, self.today)
            with self.assertRaises((PermissionDenied, ValidationError)):
                services.destroy(actor, lot.pk, 1, self.today, "Tentative interdite")
        with self.assertRaises(ValidationError):
            services.request_epi(self.member, self.bulk, 1, "Autre site", self.other)

    def test_member_never_sees_prices_or_other_peoples_equipment(self):
        lot = self.receive()
        services.issue(self.manager, lot.pk, self.member, 3, self.today)
        colleague = User.objects.create(username="colleague", role="member", site=self.site)
        request = services.request_epi(colleague, self.bulk, 1, "Privé", self.site)
        self.client.force_login(self.member, backend="core.auth.DisabledPasswordBackend")
        response = self.client.get("/epi/mine/")
        self.assertContains(response, "Gants de test")
        self.assertNotContains(response, "37,50")
        self.assertNotContains(response, "Coût historique")
        for path in ("/epi/stock/", f"/epi/lots/{lot.pk}/", "/epi/distributed/", "/epi/destroyed/", "/epi/history/", "/epi/validity/"):
            self.assertEqual(self.client.get(path).status_code, 403)
        self.assertEqual(self.client.get(f"/epi/requests/{request.pk}/").status_code, 404)
        self.client.force_login(self.other_manager, backend="core.auth.DisabledPasswordBackend")
        self.assertEqual(self.client.get(f"/epi/lots/{lot.pk}/").status_code, 404)

    def test_reminders_are_internal_and_deduplicated(self):
        lot = self.receive(expiry=self.today + timedelta(days=5))
        services.issue(self.manager, lot.pk, self.member, 1, self.today)
        services.reminders()
        count = Notification.objects.count()
        self.assertGreater(count, 0)
        services.reminders()
        self.assertEqual(Notification.objects.count(), count)
        self.assertTrue(Notification.objects.filter(user=self.member, title="EPI : échéance proche").exists())
        self.assertEqual(Outbox.objects.count(), 0)

    def test_proposals_are_conditional_human_applied_and_cannot_extend_manufacturer_date(self):
        lot = self.receive(expiry=self.today + timedelta(days=10))
        with self.assertRaises(ValidationError):
            services.create_proposal(self.manager, self.bulk, lot)
        AssistanceSettings.objects.create(pk=1, enabled=True)
        proposal = services.create_proposal(self.manager, self.bulk, lot)
        with self.assertRaises(ValidationError):
            services.answer_proposal(self.agent, proposal.pk, self.today + timedelta(days=11), explanation="Notice", source="Fabricant")
        services.answer_proposal(self.agent, proposal.pk, self.today + timedelta(days=5), usage_days=20, explanation="Selon la référence", source="Notice fabricant")
        lot.refresh_from_db()
        self.assertIsNone(lot.assessed_expiry)
        with self.assertRaises(PermissionDenied):
            services.apply_proposal(self.agent, proposal.pk)
        services.apply_proposal(self.manager, proposal.pk)
        lot.refresh_from_db()
        self.bulk.refresh_from_db()
        self.assertEqual(lot.valid_until, self.today + timedelta(days=5))
        self.assertEqual(lot.effective_usage_days, 20)
        self.assertEqual(self.bulk.usage_days, 30)

    def test_unknown_ai_answer_stays_unknown_and_global_duration_needs_admin(self):
        AssistanceSettings.objects.create(pk=1, enabled=True)
        proposal = services.create_proposal(self.manager, self.bulk)
        with self.assertRaises(ValidationError):
            services.answer_proposal(self.agent, proposal.pk, proposed_date=self.today + timedelta(days=30), explanation="Type seulement", source="Notice sans date de début")
        services.answer_proposal(self.agent, proposal.pk, explanation="La notice exacte manque", missing_information="Référence du fabricant")
        with self.assertRaises(ValidationError):
            services.apply_proposal(self.admin, proposal.pk)
        self.bulk.refresh_from_db()
        self.assertEqual(self.bulk.usage_days, 30)
        another = services.create_proposal(self.manager, self.bulk)
        services.answer_proposal(self.agent, another.pk, usage_days=90, explanation="Durée fabricant", source="Notice exacte")
        with self.assertRaises(ValidationError):
            services.apply_proposal(self.manager, another.pk)
        services.apply_proposal(self.admin, another.pk)
        self.bulk.refresh_from_db()
        self.assertEqual(self.bulk.usage_days, 90)

    def test_reference_mode_cannot_change_after_receipt(self):
        self.receive()
        with self.assertRaises(ValidationError):
            services.save_reference(self.admin, {"tracking": "individual"}, self.bulk.pk)

    def test_manual_validity_updates_preserve_stock_price_code_and_first_use(self):
        lot = self.receive(self.individual, 1)
        unit = lot.units.get()
        unit.first_use_on = self.today - timedelta(days=5)
        unit.save(update_fields=["first_use_on"])
        original_code = unit.code
        services.set_validity(self.manager, lot.pk, {"manufacturer_expiry": self.today + timedelta(days=90), "usage_days": 100})
        services.set_validity(self.manager, lot.pk, {"serial": "CORRECT-SERIAL", "assessed_expiry": self.today + timedelta(days=30), "usage_days": 20}, unit.pk)
        lot.refresh_from_db()
        unit.refresh_from_db()
        self.assertEqual((lot.available_quantity, lot.unit_price), (1, Decimal("12.50")))
        self.assertEqual(unit.code, original_code)
        self.assertEqual(unit.first_use_on, self.today - timedelta(days=5))
        self.assertEqual(unit.valid_until, self.today + timedelta(days=15))
        with self.assertRaises(ValidationError):
            services.set_validity(self.manager, lot.pk, {"first_use_on": self.today}, unit.pk)
        with self.assertRaises(ValidationError):
            services.set_validity(self.manager, lot.pk, {"assessed_expiry": self.today + timedelta(days=100)}, unit.pk)
        with self.assertRaises(PermissionDenied):
            services.set_validity(self.agent, lot.pk, {"usage_days": 10})

    def test_screens_and_csrf_and_disabled_profiles(self):
        lot = self.receive()
        for path in ("/epi/", "/epi/catalogue/", "/epi/catalogue/new/", "/epi/stock/", "/epi/stock/new/", f"/epi/lots/{lot.pk}/",
                     "/epi/requests/", "/epi/requests/new/", "/epi/mine/", "/epi/distributed/", "/epi/destroyed/", "/epi/history/", "/epi/validity/", "/epi/validity/new/"):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(self.client.get(f"/epi/lots/{lot.pk}/issue/?request=bad").status_code, 404)
        self.assertEqual(self.client.get(f"/epi/lots/{lot.pk}/destroy/?allocation=bad").status_code, 404)
        client.force_login(self.manager, backend="core.auth.DisabledPasswordBackend")
        self.assertEqual(client.post(f"/epi/lots/{lot.pk}/issue/", {}).status_code, 403)
        user = User.objects.create(username="not-configured", role="unassigned")
        self.client.force_login(user, backend="core.auth.DisabledPasswordBackend")
        self.assertEqual(self.client.get("/epi/").status_code, 403)


@override_settings(DEBUG=True, DEV_LOGIN=True, MCP_TOKEN="epi-test-only-credential")
class EPIConcurrentAndMCP(EPIFixtures, TransactionTestCase):
    def setUp(self):
        self.epi_setup()

    def race(self, operations):
        barrier = Barrier(2)

        def execute(operation):
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
            return sorted(pool.map(execute, operations))

    def test_concurrent_individual_receipts_have_unique_codes(self):
        def operation():
            return self.receive(self.individual, 1)
        self.assertEqual(self.race([operation, operation]), [True, True])
        codes = list(self.individual.lots.values_list("units__code", flat=True))
        self.assertEqual(len(set(codes)), 2)

    def test_same_unit_cannot_be_issued_concurrently_when_other_units_remain(self):
        lot = self.receive(self.individual, 2)
        unit = lot.units.order_by("code").first()
        def operation():
            return services.issue(User.objects.get(pk=self.manager.pk), lot.pk, User.objects.get(pk=self.member.pk), 1, self.today, unit_id=unit.pk)
        self.assertEqual(self.race([operation, operation]), [False, True])
        self.assertEqual(Allocation.objects.filter(unit=unit).count(), 1)

    def test_concurrent_issue_and_destruction_do_not_double_consume_stock(self):
        lot = self.receive(quantity=1)
        def issue():
            return services.issue(User.objects.get(pk=self.manager.pk), lot.pk, User.objects.get(pk=self.member.pk), 1, self.today)

        def destroy():
            return services.destroy(User.objects.get(pk=self.manager.pk), lot.pk, 1, self.today, "Retrait du stock")
        self.assertEqual(self.race([issue, destroy]), [False, True])
        lot.refresh_from_db()
        self.assertEqual(lot.available_quantity, 0)
        self.assertEqual(Allocation.objects.count() + Destruction.objects.count(), 1)

    def test_concurrent_issues_do_not_make_stock_negative(self):
        lot = self.receive(quantity=1)
        barrier = Barrier(2)
        manager_id, member_id = self.manager.pk, self.member.pk

        def issue(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                services.issue(User.objects.get(pk=manager_id), lot.pk, User.objects.get(pk=member_id), 1, self.today)
                return True
            except ValidationError:
                return False
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(issue, [1, 2]))
        self.assertEqual(sorted(outcomes), [False, True])
        lot.refresh_from_db()
        self.assertEqual(lot.available_quantity, 0)
        self.assertEqual(Allocation.objects.count(), 1)

    def test_real_mcp_returns_proposal_only_and_preserves_stock(self):
        AssistanceSettings.objects.create(pk=1, enabled=True)
        lot = self.receive(expiry=self.today + timedelta(days=50))
        proposal = services.create_proposal(self.manager, self.bulk, lot, first_use_on=self.today)

        async def scenario():
            from core.mcp_server import build_server
            from matos.asgi import application
            server = build_server(settings.MCP_ALLOWED_HOSTS, settings.MCP_ALLOWED_ORIGINS)
            with patch("matos.asgi.mcp_http", server.streamable_http_app()):
                async with server.session_manager.run():
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://localhost",
                        headers={"Authorization": "Bearer epi-test-only-credential"}) as client:
                        async with streamable_http_client("http://localhost/mcp", http_client=client) as (read, write, _):
                            async with ClientSession(read, write) as session:
                                await session.initialize()
                                names = {item.name for item in (await session.list_tools()).tools}
                                self.assertNotIn("issue_epi", names)
                                self.assertNotIn("destroy_epi", names)
                                result = await session.call_tool("list_epi_validity_requests", {})
                                self.assertEqual(json.loads(result.content[0].text)["items"][0]["id"], str(proposal.pk))
                                result = await session.call_tool("read_epi_validity_request", {"proposal_id": str(proposal.pk)})
                                self.assertEqual(json.loads(result.content[0].text)["type"], "Gants")
                                result = await session.call_tool("propose_epi_validity", {"proposal_id": str(proposal.pk),
                                    "usage_days": 20, "proposed_date": str(self.today + timedelta(days=20)), "explanation": "Durée selon la référence", "source": "Notice fabricant de test"})
                                self.assertFalse(result.isError, result.content)
        asyncio.run(scenario())
        close_old_connections()
        proposal.refresh_from_db()
        lot.refresh_from_db()
        self.assertEqual(proposal.status, "ready")
        self.assertIsNone(lot.assessed_expiry)
        self.assertEqual(lot.available_quantity, 20)
        self.assertEqual(Allocation.objects.count(), 0)
        self.client.force_login(self.manager, backend="core.auth.DisabledPasswordBackend")
        response = self.client.get("/epi/validity/")
        self.assertContains(response, "Notice fabricant de test")
        self.assertContains(response, "Appliquer la proposition")
        self.assertRedirects(self.client.post(f"/epi/validity/{proposal.pk}/decision/", {"decision": "apply"}), "/epi/validity/")
        lot.refresh_from_db()
        self.assertEqual(lot.assessed_expiry, self.today + timedelta(days=20))
