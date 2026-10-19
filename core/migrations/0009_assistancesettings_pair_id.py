from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0008_assistancesettings_sso_url")]
    operations = [migrations.AddField(model_name="assistancesettings", name="pair_id",
        field=models.CharField(blank=True, editable=False, max_length=43))]
