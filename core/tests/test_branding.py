import io
import json
import tempfile
from contextlib import contextmanager
from unittest.mock import patch
from urllib.error import URLError

from django.core.management import call_command
from django.test import TestCase, override_settings
from PIL import Image

from core import branding
from core.models import User


class BrandingTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.directory.name, YNH_PORTAL_URL="https://portal.example.invalid",
                                          DEBUG=True, DEV_LOGIN=True)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(self.directory.cleanup)
        self.user = User.objects.create(username="branding-admin", role="admin")

    def response(self, request, timeout):
        @contextmanager
        def context():
            if request.full_url.endswith("/public"):
                data = json.dumps({"portal_logo": "company.png", "portal_title": "Entreprise"}).encode()
            else:
                buffer = io.BytesIO()
                Image.new("RGBA", (120, 50), "white").save(buffer, "PNG")
                data = buffer.getvalue()
            response = io.BytesIO(data)
            response.url = request.full_url
            yield response
        return context()

    def test_logo_cache_and_signature_on_pages(self):
        with patch("core.branding.urlopen", side_effect=self.response) as opener:
            self.assertTrue(branding.refresh(force=True))
            self.assertTrue(branding.refresh())
            self.assertEqual(opener.call_count, 2)
        self.client.force_login(self.user, backend="core.auth.DisabledPasswordBackend")
        for path in ("/", "/inventory/", "/integration/", "/settings/"):
            response = self.client.get(path)
            self.assertContains(response, 'alt="Logo de la société"')
            self.assertContains(response, "Par ARCenal")
        logo = self.client.get("/branding/logo/")
        self.assertEqual(logo.status_code, 200)
        self.assertTrue(b"".join(logo.streaming_content).startswith(b"\x89PNG"))
        self.client.logout()
        self.assertContains(self.client.get("/login/"), 'alt="Logo de la société"')
        self.assertEqual(self.client.get("/branding/logo/").status_code, 200)

    def test_portal_failure_keeps_existing_logo(self):
        with patch("core.branding.urlopen", side_effect=self.response):
            branding.refresh(force=True)
        before = (branding.directory() / "logo.png").read_bytes()
        with patch("core.branding.urlopen", side_effect=OSError("Unavailable")):
            with self.assertRaises(OSError):
                branding.refresh(force=True)
        self.assertEqual(before, (branding.directory() / "logo.png").read_bytes())

    def test_invalid_portal_origin_refused(self):
        with override_settings(YNH_PORTAL_URL="http://portal.example.invalid"):
            with self.assertRaises(ValueError):
                branding.refresh(force=True)

    def test_dark_logo_retains_transparency_and_brand_colors(self):
        branding.directory().mkdir(parents=True, exist_ok=True)
        image = Image.new("RGBA", (3, 1))
        image.putdata([(12, 12, 12, 255), (20, 100, 220, 255), (0, 0, 0, 0)])
        image.save(branding.directory() / "company.png")
        response = self.client.get("/branding/logo/?mode=dark")
        with Image.open(io.BytesIO(response.content)) as result:
            self.assertGreater(result.getpixel((0, 0))[0], 200)
            self.assertEqual(result.getpixel((1, 0)), (20, 100, 220, 255))
            self.assertEqual(result.getpixel((2, 0))[3], 0)

    def test_refresh_command_handles_untrusted_certificate_without_traceback(self):
        output = io.StringIO()
        with patch("core.branding.urlopen", side_effect=URLError("certificate verify failed")):
            call_command("refresh_branding", stdout=output)
        self.assertIn("cache/logo de secours conservé", output.getvalue())
        self.assertFalse((branding.directory() / "logo.png").exists())
