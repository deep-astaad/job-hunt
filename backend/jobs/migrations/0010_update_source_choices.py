from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0009_recompute_ats_url_hash"),
    ]

    operations = [
        migrations.AlterField(
            model_name="job",
            name="source",
            field=models.CharField(
                choices=[
                    ("indeed", "Indeed"),
                    ("linkedin", "LinkedIn"),
                    ("japan_dev", "Japan Dev"),
                    ("tokyo_dev", "Tokyo Dev"),
                    ("daijob", "Daijob"),
                    ("gaijinpot", "GaijinPot"),
                    ("careercross", "CareerCross"),
                    ("green", "Green"),
                    ("wantedly", "Wantedly"),
                    ("japan-dev", "Japan Dev (legacy)"),
                    ("tokyodev", "TokyoDev (legacy)"),
                    ("custom", "Custom/Other"),
                ],
                default="custom",
                max_length=50,
            ),
        ),
    ]
