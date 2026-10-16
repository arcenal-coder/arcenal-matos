import tempfile

from django.core.files.base import ContentFile
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, override_settings


class UpgradeFromPublishedSchema(TransactionTestCase):
    def test_existing_assets_documents_and_keys_survive_reference_migrations(self):
        old = ("core", "0004_asset_control_hold")
        target = ("core", "0006_seed_device_references")
        self.addCleanup(lambda: MigrationExecutor(connection).migrate([target]))
        executor = MigrationExecutor(connection)
        executor.migrate([old])
        apps = executor.loader.project_state([old]).apps
        site = apps.get_model("core", "Site").objects.create(name="Site existant")
        category = apps.get_model("core", "Category").objects.create(name="Moniteurs", interval_days=365)
        user = apps.get_model("core", "User").objects.create(username="legacy-user", password="!", role="manager")
        asset = apps.get_model("core", "Asset").objects.create(code="LEGACY-42", name="Appareil existant",
            category=category, site=site, brand="Philips", model="MX40", serial="SN-42", custom_fields={"legacy": "kept"})
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            document = apps.get_model("core", "Document").objects.create(asset=asset, uploaded_by=user, name="preuve.txt")
            document.file.save("preuve.txt", ContentFile(b"existing-private-document"))
            MigrationExecutor(connection).migrate([target])
            from core.models import Asset, Brand, DeviceModel, Document
            item = Asset.objects.get(pk=asset.pk)
            self.assertEqual((item.code, item.brand, item.model, item.serial), ("LEGACY-42", "Philips", "MX40", "SN-42"))
            self.assertEqual(item.custom_fields, {"legacy": "kept"})
            self.assertTrue(Brand.objects.filter(key="philips").exists())
            self.assertTrue(DeviceModel.objects.filter(brand__key="philips", key="mx40").exists())
            restored = Document.objects.get(pk=document.pk)
            with restored.file.open("rb") as uploaded:
                self.assertEqual(uploaded.read(), b"existing-private-document")
            self.assertEqual(restored.asset_id, item.pk)
