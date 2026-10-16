import asyncio
import io
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

import httpx
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from PIL import Image

from core.models import Asset, AssistanceSettings, Brand, Category, DeviceModel, IntakeRequest, User
from core.tests.test_workflows import Fixtures


@override_settings(DEBUG=True, DEV_LOGIN=True, MCP_TOKEN="test-only-credential")
class IntakeTests(Fixtures, TestCase):
    def setUp(self):
        self.setup_data()
        self.client.force_login(self.manager, backend="core.auth.DisabledPasswordBackend")
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.media = override_settings(MEDIA_ROOT=self.directory.name)
        self.media.enable()
        self.addCleanup(self.media.disable)

    def payload(self, **extra):
        return {"name": "Perceuse", "category": self.category.pk, "site": self.site.pk, "state": "available", **extra}

    def test_create_auto_key_return_inventory_edit_preserves_key_and_json(self):
        response = self.client.post("/assets/new/", self.payload(code="FORGED", custom_fields='{"forged":true}'))
        self.assertRedirects(response, "/inventory/")
        item = Asset.objects.get(name="Perceuse")
        self.assertRegex(item.code, r"^ORDINATEURS-\d+-000001$")
        self.assertEqual(item.custom_fields, {})
        original = item.code
        item.custom_fields = {"legacy": "preserved"}
        item.save()
        self.assertRedirects(self.client.post(reverse("asset-edit", args=[item.pk]), self.payload(name="Perceuse révisée")), "/inventory/")
        item.refresh_from_db()
        self.assertEqual(item.code, original)
        self.assertEqual(item.custom_fields, {"legacy": "preserved"})
        response = self.client.get("/assets/new/")
        self.assertNotContains(response, 'name="custom_fields"')
        self.assertNotContains(response, 'name="code"')
        self.assertContains(response, '>Annuler</a>')

    def test_references_remember_brand_model_and_flag_typo(self):
        url = reverse("intake-reference", args=["brand"])
        self.assertEqual(self.client.post(url, {"name": "Philips"}).status_code, 201)
        response = self.client.post(url, {"name": " philips "})
        self.assertEqual(response.json()["value"], "Philips")
        self.assertEqual(Brand.objects.count(), 1)
        typo = self.client.post(url, {"name": "filips"})
        self.assertEqual(typo.status_code, 409)
        self.assertEqual(typo.json()["suggestions"][0]["value"], "Philips")
        response = self.client.post(reverse("intake-reference", args=["model"]), {"name": "MX40", "brand": "Philips"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(DeviceModel.objects.count(), 1)
        response = self.client.post("/assets/new/", self.payload(brand="Philips", model="MX40"))
        self.assertRedirects(response, "/inventory/")
        self.assertEqual(Asset.objects.get(name="Perceuse").model, "MX40")
        invalid = self.client.post("/assets/new/", self.payload(brand="filips", model="MX40"))
        self.assertEqual(invalid.status_code, 200)
        self.assertContains(invalid, "Sélectionnez un choix valide")

    def test_inline_category_and_role_boundaries(self):
        response = self.client.post(reverse("intake-reference", args=["category"]), {"name": "Défibrillateurs"})
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Category.objects.filter(name="Défibrillateurs").exists())
        self.client.force_login(self.member, backend="core.auth.DisabledPasswordBackend")
        for path in ("/assets/new/", "/intake/references/brand/", "/intake/assistance/", "/settings/sites/"):
            self.assertEqual(self.client.post(path, {"name": "Denied"}).status_code, 403)

    def test_settings_sections_and_private_photo_requests(self):
        self.client.force_login(self.admin, backend="core.auth.DisabledPasswordBackend")
        for section, title in (("users", "Gestion des utilisateurs"), ("sites", "Sites"), ("categories", "Catégories &amp; périodicités")):
            response = self.client.get(f"/settings/{section}/")
            self.assertContains(response, f"<h1>{title}</h1>", html=True)
        self.assertEqual(self.client.post("/intake/assistance/", {"category": self.category.pk}).status_code, 409)
        self.client.post("/integration/", {"assistance_enabled": "on"})
        self.client.force_login(self.manager, backend="core.auth.DisabledPasswordBackend")
        image = io.BytesIO()
        Image.new("RGB", (20, 20), "white").save(image, "PNG")
        response = self.client.post("/intake/assistance/", {"category": self.category.pk,
            "photo": SimpleUploadedFile("serial.png", image.getvalue(), content_type="image/png")})
        self.assertEqual(response.status_code, 201)
        item = IntakeRequest.objects.get(pk=response.json()["id"])
        self.assertTrue(item.photo)
        self.assertEqual(self.client.get(reverse("intake-result", args=[item.pk])).json()["status"], "pending")
        self.client.force_login(self.other_manager, backend="core.auth.DisabledPasswordBackend")
        self.assertEqual(self.client.get(reverse("intake-result", args=[item.pk])).status_code, 404)
        self.client.force_login(self.manager, backend="core.auth.DisabledPasswordBackend")
        invalid = self.client.post("/intake/assistance/", {"category": self.category.pk,
            "photo": SimpleUploadedFile("fake.png", b"not an image", content_type="image/png")})
        self.assertEqual(invalid.status_code, 400)

    def test_company_logo_is_configurable_transparent_and_admin_only(self):
        self.assertEqual(self.client.post("/settings/logo/").status_code, 403)
        self.client.force_login(self.admin, backend="core.auth.DisabledPasswordBackend")
        image = io.BytesIO()
        Image.new("RGBA", (20, 20), (10, 20, 30, 0)).save(image, "PNG")
        response = self.client.post("/settings/logo/", {"logo": SimpleUploadedFile("company.png", image.getvalue(), content_type="image/png")})
        self.assertRedirects(response, "/settings/")
        self.client.logout()
        self.assertContains(self.client.get("/login/"), 'class="company-logo"')
        logo = self.client.get("/branding/logo/")
        with Image.open(io.BytesIO(b"".join(logo.streaming_content))) as uploaded:
            self.assertEqual(uploaded.getpixel((0, 0))[3], 0)

    def test_phone_photo_orientation_is_applied_before_agent_reading(self):
        from core.intake import image_file
        image = Image.new("RGB", (40, 20), "white")
        exif = image.getexif()
        exif[274] = 6
        content = io.BytesIO()
        image.save(content, "JPEG", exif=exif)
        converted = image_file(SimpleUploadedFile("phone.jpg", content.getvalue(), content_type="image/jpeg"))
        with Image.open(converted) as result:
            self.assertEqual(result.size, (20, 40))


@override_settings(DEBUG=True, DEV_LOGIN=True, MCP_TOKEN="test-only-credential")
class IntakeConcurrencyAndMCP(Fixtures, TransactionTestCase):
    def setUp(self):
        self.setup_data()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.media = override_settings(MEDIA_ROOT=self.directory.name)
        self.media.enable()
        self.addCleanup(self.media.disable)

    def test_concurrent_auto_identifiers_are_distinct(self):
        barrier = Barrier(2)
        category_id, site_id = self.category.pk, self.site.pk

        def create(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return Asset.objects.create(name="Concurrent", category_id=category_id, site_id=site_id).code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            codes = list(executor.map(create, range(2)))
        self.assertEqual(len(set(codes)), 2)
        self.assertEqual({code.rsplit("-", 1)[1] for code in codes}, {"000001", "000002"})

    def test_mcp_completes_intake_without_creating_asset(self):
        AssistanceSettings.objects.create(pk=1, enabled=True)
        item = IntakeRequest.objects.create(requested_by=self.manager, category=self.category, name="Moniteur")
        photo = io.BytesIO()
        Image.new("RGB", (20, 20), "white").save(photo, "PNG")
        item.photo.save("serial.png", ContentFile(photo.getvalue()))
        total = Asset.objects.count()

        async def scenario():
            from core.mcp_server import build_server
            from matos.asgi import application
            server = build_server(settings.MCP_ALLOWED_HOSTS, settings.MCP_ALLOWED_ORIGINS)
            with patch("matos.asgi.mcp_http", server.streamable_http_app()):
                async with server.session_manager.run():
                    await call_agent(application)

        async def call_agent(application):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://localhost",
                headers={"Authorization": "Bearer test-only-credential"}) as client:
                async with streamable_http_client("http://localhost/mcp", http_client=client) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool("list_intake_requests", {})
                        self.assertFalse(result.isError, result.content)
                        self.assertEqual(json.loads(result.content[0].text)["items"][0]["id"], str(item.pk))
                        result = await session.call_tool("read_intake_request", {"request_id": str(item.pk)})
                        self.assertFalse(result.isError, result.content)
                        self.assertIn("Moniteur", result.content[0].text)
                        self.assertTrue(any(content.type == "image" for content in result.content))
                        result = await session.call_tool("complete_intake_request", {"request_id": str(item.pk),
                            "serial": "SN-123", "interval_days": 365, "explanation": "Plaque lue ; notice fabricant : contrôle annuel."})
                        self.assertFalse(result.isError, result.content)
        asyncio.run(scenario())
        close_old_connections()
        item.refresh_from_db()
        self.assertEqual((item.status, item.serial, item.interval_days), ("done", "SN-123", 365))
        self.assertEqual(Asset.objects.count(), total)
        self.assertEqual(User.objects.filter(role="agent").count(), 1)
