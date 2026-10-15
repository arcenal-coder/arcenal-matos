import asyncio
import csv
import io
import json
import logging
import tempfile
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import httpx
import yaml
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, connection
from django.test import AsyncClient, Client, TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from core import services
from core.import_export import HEADERS, asset_row, csv_bytes, import_csv, report
from core.models import (
    AgentCommand,
    Asset,
    Category,
    Document,
    Event,
    Intervention,
    License,
    Loan,
    Notification,
    Outbox,
    Reservation,
    Site,
    Supplier,
    User,
)

logging.getLogger("django.request").setLevel(logging.CRITICAL)
logging.getLogger("mcp.server").setLevel(logging.CRITICAL)


class Fixtures:
    def setup_data(self):
        self.today = timezone.localdate()
        self.site = Site.objects.create(name="Paris")
        self.other = Site.objects.create(name="Lyon")
        self.category = Category.objects.create(name="Ordinateurs", interval_days=365)
        self.member = User.objects.create(username="alice", role="member", site=self.site, email="alice@example.invalid")
        self.manager = User.objects.create(username="manager", role="manager", email="manager@example.invalid")
        self.manager.managed_sites.add(self.site)
        self.other_manager = User.objects.create(username="lyon", role="manager")
        self.other_manager.managed_sites.add(self.other)
        self.admin = User.objects.create(username="admin", role="admin")
        self.agent = User.objects.create(username="__hermes_logisticien__", role="agent")
        self.asset = Asset.objects.create(code="PC-1", name="Portable", category=self.category, site=self.site)
        self.foreign = Asset.objects.create(code="PC-2", name="Portable Lyon", category=self.category, site=self.other)
        self.supplier = Supplier.objects.create(name="Contrôles", email="controls@example.invalid")

    def approved(self):
        item = services.reserve(self.member, self.asset.pk, self.today, self.today + timedelta(days=7))
        services.approve_reservation(self.manager, item.pk)
        return item


class Workflows(Fixtures, TestCase):
    def setUp(self):
        self.setup_data()

    def test_complete_loan_with_human_approval_and_agent_movements(self):
        item = self.approved()
        loan = services.checkout(self.agent, item.pk, "Bon état")
        services.return_loan(self.agent, item.pk, "Bon état", "Vérifié")
        loan.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(item.status, "returned")
        self.assertEqual(loan.returned_by, self.agent)
        self.assertTrue(Event.objects.filter(actor=self.agent, action="loan.return").exists())
        self.assertTrue(Notification.objects.filter(user=self.member).exists())
        self.assertTrue(Outbox.objects.filter(recipient=self.member.email).exists())

    def test_agent_and_administrator_cannot_approve(self):
        item = services.reserve(self.member, self.asset.pk, self.today, self.today)
        for actor in (self.agent, self.admin, self.member, self.other_manager):
            with self.assertRaises(PermissionDenied):
                services.approve_reservation(actor, item.pk)
        self.assertFalse(Reservation.objects.get(pk=item.pk).approved_by_id)

    def test_checkout_requires_approval_and_does_not_repeat(self):
        item = services.reserve(self.member, self.asset.pk, self.today, self.today)
        with self.assertRaises(ValidationError):
            services.checkout(self.agent, item.pk, "Bon")
        services.approve_reservation(self.manager, item.pk)
        services.checkout(self.manager, item.pk, "Bon")
        with self.assertRaises(ValidationError):
            services.checkout(self.agent, item.pk, "Bon")
        self.assertEqual(Loan.objects.count(), 1)

    def test_two_overlapping_requests_only_one_approval(self):
        first = services.reserve(self.member, self.asset.pk, self.today, self.today + timedelta(days=3))
        second = services.reserve(self.member, self.asset.pk, self.today, self.today + timedelta(days=3))
        services.approve_reservation(self.manager, first.pk)
        with self.assertRaises(ValidationError):
            services.approve_reservation(self.manager, second.pk)

    def test_nonoverlapping_reservations(self):
        first = self.approved()
        second = services.reserve(self.member, self.asset.pk, self.today + timedelta(days=8), self.today + timedelta(days=10))
        services.approve_reservation(self.manager, second.pk)
        self.assertEqual(Reservation.objects.filter(status="approved").count(), 2)
        self.assertNotEqual(first.pk, second.pk)

    def test_bad_dates_refused(self):
        for start, end in [(self.today, self.today - timedelta(days=1)), (self.today - timedelta(days=1), self.today)]:
            with self.assertRaises(ValidationError):
                services.reserve(self.member, self.asset.pk, start, end)

    def test_intersite_requires_local_unavailability_and_owner_validation(self):
        with self.assertRaises(ValidationError):
            services.reserve(self.member, self.foreign.pk, self.today, self.today)
        self.asset.state = "maintenance"
        self.asset.save()
        item = services.reserve(self.member, self.foreign.pk, self.today, self.today)
        with self.assertRaises(PermissionDenied):
            services.approve_reservation(self.manager, item.pk)
        services.approve_reservation(self.other_manager, item.pk)
        self.assertEqual(Reservation.objects.get(pk=item.pk).approved_by, self.other_manager)

    def test_expired_control_blocks_loan_and_restore(self):
        self.asset.control_required = True
        self.asset.next_control = self.today - timedelta(days=1)
        self.asset.save()
        with self.assertRaises(ValidationError):
            services.reserve(self.member, self.asset.pk, self.today, self.today)
        with self.assertRaises(ValidationError):
            services.restore_asset(self.manager, self.asset.pk)

    def test_control_must_cover_the_reserved_period(self):
        self.asset.control_required = True
        self.asset.next_control = self.today + timedelta(days=2)
        self.asset.save()
        with self.assertRaises(ValidationError):
            services.reserve(self.member, self.asset.pk, self.today, self.today + timedelta(days=3))

    def test_editing_expired_control_does_not_bypass_human_restore(self):
        self.asset.control_required = True
        self.asset.next_control = self.today - timedelta(days=1)
        self.asset.save()
        services.update_asset(self.admin, self.asset.pk, {"next_control": self.today + timedelta(days=365)})
        with self.assertRaises(ValidationError):
            services.reserve(self.member, self.asset.pk, self.today, self.today)
        services.restore_asset(self.manager, self.asset.pk)
        self.assertTrue(services.reserve(self.member, self.asset.pk, self.today, self.today))

    def test_extending_category_interval_keeps_expired_asset_blocked(self):
        self.asset.control_required = True
        self.asset.last_control = self.today - timedelta(days=366)
        self.asset.save()
        self.category.interval_days = 730
        self.category.save()
        self.asset.refresh_from_db()
        self.assertTrue(self.asset.control_hold)
        with self.assertRaises(ValidationError):
            services.reserve(self.member, self.asset.pk, self.today, self.today)
        services.restore_asset(self.manager, self.asset.pk)
        self.assertFalse(Asset.objects.get(pk=self.asset.pk).blocked)

    def test_category_interval_and_override(self):
        self.asset.last_control = self.today
        self.assertEqual(self.asset.control_due, self.today + timedelta(days=365))
        self.asset.interval_days = 30
        self.assertEqual(self.asset.control_due, self.today + timedelta(days=30))

    def test_maintenance_completion_does_not_restore_automatically(self):
        self.asset.control_required = True
        self.asset.save()
        item = services.plan_intervention(self.agent, self.asset.pk, {"scheduled_date": self.today, "description": "Contrôle", "is_control": True, "supplier": self.supplier, "cost": 12})
        services.complete_intervention(self.agent, item.pk, self.today)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.state, "maintenance")
        self.assertEqual(self.asset.next_control, self.today + timedelta(days=365))
        with self.assertRaises(PermissionDenied):
            services.restore_asset(self.agent, self.asset.pk)
        services.restore_asset(self.manager, self.asset.pk)
        self.assertFalse(Asset.objects.get(pk=self.asset.pk).blocked)

    def test_open_intervention_prevents_restore(self):
        services.plan_intervention(self.manager, self.asset.pk, {"scheduled_date": self.today, "description": "Réparer"})
        with self.assertRaises(ValidationError):
            services.restore_asset(self.manager, self.asset.pk)

    def test_checkout_rechecks_blocking(self):
        item = self.approved()
        self.asset.state = "maintenance"
        self.asset.save()
        with self.assertRaises(ValidationError):
            services.checkout(self.manager, item.pk, "Bon")

    def test_return_damaged_blocks_asset(self):
        item = self.approved()
        services.checkout(self.manager, item.pk, "Bon")
        services.return_loan(self.manager, item.pk, "Cassé", damaged=True)
        self.assertTrue(Asset.objects.get(pk=self.asset.pk).blocked)

    def test_agent_cannot_patch_state_or_approval_fields(self):
        for field in ("state", "site", "assigned_to", "control_required", "approved_by"):
            with self.assertRaises(ValidationError):
                services.update_asset(self.agent, self.asset.pk, {field: "available"})
        services.update_asset(self.agent, self.asset.pk, {"location": "Étagère 2"})
        self.assertEqual(Asset.objects.get(pk=self.asset.pk).location, "Étagère 2")

    def test_cross_site_asset_edit_refused(self):
        with self.assertRaises(PermissionDenied):
            services.update_asset(self.manager, self.foreign.pk, {"name": "Autre"})

    def test_assignment_cannot_bypass_reservation(self):
        self.approved()
        with self.assertRaises(ValidationError):
            services.assign_asset(self.agent, self.asset.pk, self.member)

    def test_transfer_and_site_permissions(self):
        item = services.transfer_asset(self.manager, self.asset.pk, self.other)
        services.advance_transfer(self.manager, item.pk)
        with self.assertRaises(PermissionDenied):
            services.advance_transfer(self.manager, item.pk)
        services.advance_transfer(self.other_manager, item.pk)
        self.assertEqual(Asset.objects.get(pk=self.asset.pk).site, self.other)

    def test_supplier_draft_requires_human_before_send(self):
        item = services.prepare_supplier_request(self.agent, self.asset.pk, self.supplier, "Contrôle", "Bonjour")
        self.assertEqual(Outbox.objects.filter(supplier_request=item).count(), 0)
        with self.assertRaises(PermissionDenied):
            services.approve_supplier_request(self.agent, item.pk)
        with self.assertRaises(PermissionDenied):
            services.approve_supplier_request(self.other_manager, item.pk)
        services.approve_supplier_request(self.manager, item.pk)
        with patch("core.services.send_mail", return_value=1) as mail:
            services.send_outbox()
            first_count = mail.call_count
            self.assertTrue(any(call.args[3] == [self.supplier.email] for call in mail.call_args_list))
            services.send_outbox()
            self.assertEqual(mail.call_count, first_count)
        item.refresh_from_db()
        self.assertEqual(item.status, "sent")

    def test_email_failure_is_visible_and_retryable(self):
        item = Outbox.objects.create(key="fail", recipient="x@example.invalid", subject="Test", body="Test")
        with patch("core.services.send_mail", side_effect=OSError("SMTP indisponible")):
            self.assertEqual(services.send_outbox(), 0)
        item.refresh_from_db()
        self.assertEqual(item.attempts, 1)
        self.assertIn("SMTP", item.error)
        self.assertIsNone(item.sent_at)

    def test_transport_zero_does_not_mark_email_sent(self):
        item = Outbox.objects.create(key="not-accepted", recipient="x@example.invalid", subject="Test", body="Test")
        with patch("core.services.send_mail", return_value=0):
            self.assertEqual(services.send_outbox(), 0)
        item.refresh_from_db()
        self.assertIsNone(item.sent_at)
        self.assertTrue(item.error)

    def test_licenses_capacity_and_site(self):
        item = License.objects.create(name="Suite", site=self.site, kind="subscription", seats=1)
        services.allocate_license(self.manager, item.pk, user=self.member)
        with self.assertRaises(ValidationError):
            services.allocate_license(self.manager, item.pk, asset=self.asset)
        self.assertEqual(item.available_seats, 0)

    def test_software_can_be_assigned_to_manager_but_not_inactive_identity(self):
        self.manager.site = self.site
        self.manager.save()
        item = License.objects.create(name="Manager Suite", site=self.site, kind="license", seats=2)
        services.allocate_license(self.manager, item.pk, user=self.manager)
        self.member.is_active = False
        self.member.save()
        with self.assertRaises(ValidationError):
            services.allocate_license(self.manager, item.pk, user=self.member)

    def test_daily_reminders_are_deduplicated(self):
        item = self.approved()
        services.checkout(self.agent, item.pk, "Bon")
        Reservation.objects.filter(pk=item.pk).update(end=self.today - timedelta(days=1), start=self.today - timedelta(days=3))
        services.reminders(self.agent)
        count = Notification.objects.count()
        services.reminders(self.agent)
        self.assertEqual(Notification.objects.count(), count)
        self.assertTrue(Notification.objects.filter(title="Retour en retard").exists())

    def test_agent_idempotence_and_conflict(self):
        def operation():
            services.update_asset(self.agent, self.asset.pk, {"location": "B"})
            return {"ok": True}
        services.agent_command("one", {"location": "B"}, operation)
        services.agent_command("one", {"location": "B"}, operation)
        self.assertEqual(Event.objects.filter(action="asset.updated").count(), 1)
        with self.assertRaises(ValidationError):
            services.agent_command("one", {"location": "C"}, operation)
        self.assertEqual(AgentCommand.objects.count(), 1)


@override_settings(DEV_LOGIN=True, DEBUG=True)
class Screens(Fixtures, TestCase):
    def setUp(self):
        self.setup_data()
        self.client.force_login(self.manager, backend="core.auth.DisabledPasswordBackend")

    def test_all_manager_screens_render(self):
        for url in ["/", "/inventory/", f"/assets/{self.asset.pk}/", f"/assets/{self.asset.pk}/edit/",
                    f"/assets/{self.asset.pk}/assign/", f"/assets/{self.asset.pk}/transfer/",
                    f"/assets/{self.asset.pk}/maintenance/", f"/assets/{self.asset.pk}/supplier-request/",
                    "/assets/new/", "/reservations/", "/transfers/", "/maintenance/", "/suppliers/",
                    "/licenses/", "/licenses/new/", "/reports/", "/import/", "/scan/", "/notifications/", "/journal/"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_administrator_screens_and_yaml(self):
        self.client.force_login(self.admin, backend="core.auth.DisabledPasswordBackend")
        for url in ("/settings/", "/integration/", "/setup/site/", "/setup/category/", f"/setup/user/{self.member.pk}/"):
            self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.get("/integration/?download=1")
        data = yaml.safe_load(response.content)
        self.assertEqual(data["access"]["sites"], "all")
        self.assertIn("supplier_requests.approve", data["access"]["human_only"])
        self.assertNotIn("token", data["mcp"]["authentication"])

    def test_admin_assigns_role_and_multiple_sites(self):
        self.client.force_login(self.admin, backend="core.auth.DisabledPasswordBackend")
        response = self.client.post(reverse("setup-edit", args=["user", self.member.pk]), {
            "role": "manager", "site": self.site.pk, "managed_sites": [self.site.pk, self.other.pk]})
        self.assertEqual(response.status_code, 302)
        self.member.refresh_from_db()
        self.assertEqual(self.member.role, "manager")
        self.assertEqual(set(self.member.managed_sites.values_list("pk", flat=True)), {self.site.pk, self.other.pk})

    def test_movement_attachment_is_private_and_accessible_to_its_borrower(self):
        item = self.approved()
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            response = self.client.post(reverse("movement", args=[item.pk, "checkout"]), {
                "condition": "Bon état", "comment": "Vérifié", "photo": SimpleUploadedFile("etat.txt", b"Sortie verifiee")})
            self.assertEqual(response.status_code, 302)
            document = Document.objects.get(loan__reservation=item)
            self.client.force_login(self.member, backend="core.auth.DisabledPasswordBackend")
            response = self.client.get(reverse("document", args=[document.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), b"Sortie verifiee")

    def test_manager_no_other_site_list_detail_export_or_yaml(self):
        self.assertNotContains(self.client.get("/inventory/"), "Portable Lyon")
        for url in (f"/assets/{self.foreign.pk}/", f"/assets/{self.foreign.pk}/edit/", "/integration/", "/settings/", f"/reports/?format=csv&site={self.other.pk}"):
            self.assertIn(self.client.get(url).status_code, (403, 404))

    def test_member_cost_documents_and_management_hidden(self):
        self.asset.purchase_cost = 9876
        self.asset.save()
        self.client.force_login(self.member, backend="core.auth.DisabledPasswordBackend")
        response = self.client.get(reverse("asset", args=[self.asset.pk]))
        self.assertNotContains(response, "9876")
        self.assertNotContains(response, "Coût")
        for url in ("/maintenance/", "/suppliers/", "/reports/", "/import/", "/journal/", "/integration/"):
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_member_reservation_screen_and_own_loan(self):
        item = self.approved()
        self.client.force_login(self.member, backend="core.auth.DisabledPasswordBackend")
        for url in ("/", "/reservations/", f"/reservations/{item.pk}/", f"/assets/{self.asset.pk}/reserve/"):
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_csrf_enforced_for_mutation(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.manager, backend="core.auth.DisabledPasswordBackend")
        item = services.reserve(self.member, self.asset.pk, self.today, self.today)
        self.assertEqual(client.post(reverse("action", args=["approve", item.pk])).status_code, 403)

    @override_settings(DEV_LOGIN=False, TRUST_YNH_HEADERS=False)
    def test_forged_identity_header_ignored_and_local_session_cleared(self):
        response = self.client.get("/", HTTP_YNH_USER="admin")
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(DEV_LOGIN=False, TRUST_YNH_HEADERS=True)
    def test_sso_header_and_logout_each_request(self):
        self.client.logout()
        response = self.client.get("/", HTTP_YNH_USER=self.manager.username)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/").status_code, 302)

    @override_settings(DEV_LOGIN=False, TRUST_YNH_HEADERS=True)
    async def test_sso_identity_through_asgi_header_normalization(self):
        client = AsyncClient()
        # Exercise Django's ASGI parser, which discards underscore headers.
        response = await client.get("/", headers={"YNH-USER": self.manager.username})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.asgi_request.user.username, self.manager.username)
        self.assertEqual((await client.get("/")).status_code, 302)

    def test_no_password_authentication(self):
        self.assertFalse(self.member.has_usable_password())
        self.assertFalse(self.client.login(username=self.member.username, password="anything"))
        original = self.member.password
        self.member.first_name = "Alice"
        self.member.save()
        self.member.refresh_from_db()
        self.assertEqual(self.member.password, original)

    def test_member_cannot_open_license_allocation(self):
        item = License.objects.create(name="Private", site=self.site, kind="license")
        self.client.force_login(self.member, backend="core.auth.DisabledPasswordBackend")
        self.assertEqual(self.client.get(reverse("license-allocate", args=[item.pk])).status_code, 403)

    def test_invalid_filter_and_action_identifiers(self):
        self.assertEqual(self.client.get("/inventory/?site=bad").status_code, 400)
        self.assertEqual(self.client.get("/inventory/?start=bad").status_code, 400)
        self.assertEqual(self.client.post("/actions/approve/bad/").status_code, 400)

    def test_intersite_dates_preserved_in_the_form(self):
        start = self.today + timedelta(days=20)
        end = start + timedelta(days=2)
        item = services.reserve(self.member, self.asset.pk, start, end)
        services.approve_reservation(self.manager, item.pk)
        self.client.force_login(self.member, backend="core.auth.DisabledPasswordBackend")
        response = self.client.get(f"/assets/{self.foreign.pk}/reserve/?start={start}&end={end}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'value="{start}"')
        self.assertContains(response, f'value="{end}"')

    def test_unassigned_user_no_data(self):
        user = User.objects.create(username="new")
        self.client.force_login(user, backend="core.auth.DisabledPasswordBackend")
        self.assertEqual(self.client.get("/").status_code, 403)
        self.assertEqual(self.client.get("/inventory/").status_code, 403)

    def test_labels_and_documents_authorization(self):
        self.assertTrue(self.client.get(reverse("label", args=[self.asset.pk, "qr"])).content.startswith(b"\x89PNG"))
        self.assertContains(self.client.get(reverse("label", args=[self.asset.pk, "barcode"])), "svg")
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            document = Document.objects.create(asset=self.asset, name="notice.txt", uploaded_by=self.manager,
                                               file=SimpleUploadedFile("notice.txt", b"Private"))
            self.assertEqual(self.client.get(reverse("document", args=[document.pk])).status_code, 200)
            self.client.force_login(self.other_manager, backend="core.auth.DisabledPasswordBackend")
            self.assertEqual(self.client.get(reverse("document", args=[document.pk])).status_code, 403)


class ImportsReports(Fixtures, TestCase):
    def setUp(self):
        self.setup_data()

    def make_csv(self, code="NEW-1", site=None):
        row = asset_row(self.asset)
        row[0] = code
        if site:
            row[6] = site
        return csv_bytes([row])

    def test_csv_valid_and_atomic_on_duplicate(self):
        self.assertEqual(import_csv(self.manager, self.make_csv()), 1)
        before = Asset.objects.count()
        with self.assertRaises(ValidationError):
            import_csv(self.manager, self.make_csv())
        self.assertEqual(Asset.objects.count(), before)

    def test_bad_row_rolls_back_all_rows(self):
        text = self.make_csv().decode("utf-8-sig")
        content = (text + "BROKEN\n").encode("utf-8-sig")
        with self.assertRaises(ValidationError):
            import_csv(self.manager, content)
        self.assertFalse(Asset.objects.filter(code="NEW-1").exists())

    def test_import_wrong_site_refused(self):
        with self.assertRaises(PermissionDenied):
            import_csv(self.manager, self.make_csv(site="Lyon"))

    def test_import_bad_headers_and_json(self):
        with self.assertRaises(ValidationError):
            import_csv(self.manager, b"name,site\nA,Paris")
        row = asset_row(self.asset)
        row[0] = "NEW-2"
        row[-1] = "[]"
        with self.assertRaises(ValidationError):
            import_csv(self.manager, csv_bytes([row]))

    def test_reports_scoped_and_pdf(self):
        data, mime = report(self.manager)
        rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(rows[0], HEADERS)
        self.assertEqual(len(rows), 2)
        self.assertNotIn(b"PC-2", data)
        data, mime = report(self.manager, "pdf")
        self.assertTrue(data.startswith(b"%PDF"))
        with self.assertRaises(PermissionDenied):
            report(self.member)

    def test_csv_formula_injection_escaped(self):
        self.asset.name = "=HYPERLINK(\"bad\")"
        self.asset.save()
        data, _ = report(self.manager)
        self.assertIn(b"'=HYPERLINK", data)


@override_settings(DEV_LOGIN=True, DEBUG=True)
class Volume(Fixtures, TestCase):
    def setUp(self):
        self.setup_data()
        self.asset.state = "maintenance"
        self.asset.save()
        Asset.objects.bulk_create([Asset(code=f"VOL-{number:04}", name=f"Équipement {number}", category=self.category, site=self.other)
                                   for number in range(1498)])
        User.objects.bulk_create([User(username=f"volume-{number}", role="member", site=self.site, password="!") for number in range(296)])

    def test_1500_assets_300_users_intersite_and_export(self):
        self.assertEqual(Asset.objects.count(), 1500)
        self.assertEqual(User.objects.exclude(role="agent").count(), 300)
        self.assertEqual(User.objects.filter(role="agent").count(), 1)
        self.client.force_login(self.member, backend="core.auth.DisabledPasswordBackend")
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/inventory/?intersite=1")
        self.assertEqual(response.status_code, 200)
        self.assertLess(len(queries), 25)
        self.other_manager.managed_sites.add(self.site)
        data, _ = report(self.other_manager, "csv")
        self.assertEqual(len(list(csv.reader(io.StringIO(data.decode("utf-8-sig")), delimiter=";"))), 1501)


@override_settings(MCP_TOKEN="test-only-credential")
class MCPIntegration(Fixtures, TransactionTestCase):
    def setUp(self):
        self.setup_data()

    def test_real_mcp_client_auth_read_write_and_restricted_commands(self):
        async def scenario():
            from matos.asgi import application, mcp_server
            async with mcp_server.session_manager.run():
                transport = httpx.ASGITransport(app=application)
                async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
                    self.assertEqual((await client.post("/mcp", json={})).status_code, 401)
                    self.assertEqual((await client.post("/mcp", json={}, headers=[(b"authorization", b"Bearer \xff")])).status_code, 401)
                    client.headers["Authorization"] = "Bearer test-only-credential"
                    async with streamable_http_client("http://localhost/mcp", http_client=client) as (read, write, _):
                        async with ClientSession(read, write) as session:
                            await session.initialize()
                            names = {item.name for item in (await session.list_tools()).tools}
                            self.assertIn("prepare_supplier_request", names)
                            self.assertNotIn("approve_reservation", names)
                            self.assertNotIn("restore_asset", names)
                            result = await session.call_tool("list_assets", {})
                            self.assertFalse(result.isError, result.content)
                            result = await session.call_tool("update_asset", {"asset_id": str(self.asset.pk), "fields": {"location": "MCP"}, "operation_key": "mcp-1"})
                            self.assertFalse(result.isError, result.content)
                            result = await session.call_tool("update_asset", {"asset_id": str(self.asset.pk), "fields": {"state": "available"}, "operation_key": "mcp-denied"})
                            self.assertTrue(result.isError)
                            result = await session.call_tool("plan_maintenance", {"asset_id": str(self.asset.pk), "scheduled_date": str(self.today),
                                "description": "Contrôle MCP", "cost": 12.35, "operation_key": "mcp-maintenance"})
                            self.assertFalse(result.isError, result.content)
                            result = await session.call_tool("complete_maintenance", {"intervention_id": json.loads(result.content[0].text)["intervention_id"],
                                "completed_date": str(self.today), "cost": 14.37, "operation_key": "mcp-complete"})
                            self.assertFalse(result.isError, result.content)
        asyncio.run(scenario())
        close_old_connections()
        self.assertEqual(Asset.objects.get(pk=self.asset.pk).location, "MCP")
        self.assertTrue(Event.objects.filter(actor=self.agent, action="asset.updated").exists())
        self.assertEqual(Intervention.objects.get(asset=self.asset).cost, Decimal("14.37"))

    def test_concurrent_approvals_have_single_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        first = services.reserve(self.member, self.asset.pk, self.today, self.today)
        second = services.reserve(self.member, self.asset.pk, self.today, self.today)
        barrier = Barrier(2)
        def approve(pk):
            close_old_connections()
            barrier.wait(timeout=10)
            try:
                services.approve_reservation(User.objects.get(pk=self.manager.pk), pk)
                return True
            except ValidationError:
                return False
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(approve, [first.pk, second.pk]))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(Reservation.objects.filter(status="approved").count(), 1)

    def test_concurrent_csv_imports_do_not_duplicate_identifiers(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        row = asset_row(self.asset)
        row[0] = "CONCURRENT-CSV"
        content = csv_bytes([row])
        barrier = Barrier(2)
        def import_one(_):
            close_old_connections()
            barrier.wait(timeout=10)
            try:
                import_csv(User.objects.get(pk=self.manager.pk), content)
                return True
            except ValidationError:
                return False
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(import_one, range(2)))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(Asset.objects.filter(code="CONCURRENT-CSV").count(), 1)

    def test_concurrent_cancellation_checkout_stays_consistent(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        item = self.approved()
        barrier = Barrier(2)
        def operation(kind):
            close_old_connections()
            barrier.wait(timeout=10)
            try:
                if kind == "cancel":
                    services.cancel_reservation(User.objects.get(pk=self.member.pk), item.pk)
                else:
                    services.checkout(User.objects.get(pk=self.manager.pk), item.pk, "Bon")
                return True
            except ValidationError:
                return False
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(operation, ["cancel", "checkout"]))
        self.assertEqual(sorted(results), [False, True])
        item.refresh_from_db()
        self.assertEqual(Loan.objects.filter(reservation=item).exists(), item.status == "out")
