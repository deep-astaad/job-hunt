from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("jobs", "0013_alter_job_updated_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="JobApplicationStatus",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_applied", models.BooleanField(db_index=True, default=False)),
                ("applied_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("job", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="application_statuses", to="jobs.job")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="job_application_statuses", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "unique_together": {("user", "job")},
            },
        ),
        migrations.AddIndex(
            model_name="jobapplicationstatus",
            index=models.Index(fields=["user", "is_applied"], name="jobs_jobapp_user_id_c3927d_idx"),
        ),
        migrations.AddIndex(
            model_name="jobapplicationstatus",
            index=models.Index(fields=["job", "user"], name="jobs_jobapp_job_id_1c8b0d_idx"),
        ),
    ]
