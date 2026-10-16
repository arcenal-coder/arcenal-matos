import unicodedata

from django.db import migrations


def seed_references(apps, schema_editor):
    Asset = apps.get_model("core", "Asset")
    Brand = apps.get_model("core", "Brand")
    DeviceModel = apps.get_model("core", "DeviceModel")
    alias = schema_editor.connection.alias
    for old_brand, old_model in Asset.objects.using(alias).exclude(brand="").order_by("brand", "model").values_list("brand", "model").distinct():
        name = " ".join(old_brand.split())
        if not name:
            continue
        key = " ".join(unicodedata.normalize("NFKC", name).casefold().split())
        brand, _ = Brand.objects.using(alias).get_or_create(key=key, defaults={"name": name})
        model = " ".join(old_model.split())
        if model:
            key = " ".join(unicodedata.normalize("NFKC", model).casefold().split())
            DeviceModel.objects.using(alias).get_or_create(brand=brand, key=key, defaults={"name": model})


class Migration(migrations.Migration):
    dependencies = [("core", "0005_assetsequence_assistancesettings_brand_intakerequest_and_more")]
    operations = [migrations.RunPython(seed_references, migrations.RunPython.noop)]
