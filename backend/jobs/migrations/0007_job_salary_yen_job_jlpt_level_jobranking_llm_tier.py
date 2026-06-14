from django.db import migrations, models


def ensure_columns(apps, schema_editor):
    """Add the new columns only if they don't already exist.

    MySQL DDL is not transactional, so an earlier failed run of this migration
    can leave the columns committed while the migration itself is unrecorded.
    A plain AddField would then fail with 'Duplicate column name' on the next
    deploy and crash the web container. Adding columns idempotently lets the
    migration recover by itself, no manual --fake needed.
    """
    conn = schema_editor.connection

    def columns(table):
        with conn.cursor() as cursor:
            return {d.name for d in conn.introspection.get_table_description(cursor, table)}

    job_cols = columns("jobs_job")
    if "salary_yen" not in job_cols:
        schema_editor.execute("ALTER TABLE jobs_job ADD COLUMN salary_yen INT UNSIGNED NULL")
    if "jlpt_level" not in job_cols:
        schema_editor.execute("ALTER TABLE jobs_job ADD COLUMN jlpt_level SMALLINT UNSIGNED NULL")

    rank_cols = columns("jobs_jobranking")
    if "llm_tier" not in rank_cols:
        schema_editor.execute("ALTER TABLE jobs_jobranking ADD COLUMN llm_tier VARCHAR(2) NULL")


def populate_derived_fields(apps, schema_editor):
    """Backfill salary_yen/jlpt_level for jobs that existed before these columns.

    (llm_tier cannot be backfilled -- the pre-rule tier was never stored, so it
    is populated only as jobs are re-ranked going forward.)
    """
    from jobs.parsers import parse_salary_to_yen, required_jlpt_level

    Job = apps.get_model("jobs", "Job")
    for job in Job.objects.all().iterator():
        # A single malformed row must never abort the migration (and crash the
        # web container at startup), so guard each update independently.
        try:
            level = required_jlpt_level(f"{job.title} {job.description} {job.full_description}")
            if level is None and (job.language or "").upper() == "JP":
                level = 2
            Job.objects.filter(pk=job.pk).update(
                salary_yen=parse_salary_to_yen(job.salary),
                jlpt_level=level,
            )
        except Exception:
            continue


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0006_job_is_ranked_job_jobs_job_is_rank_cac937_idx'),
    ]

    operations = [
        # Keep Django's model state in sync (AddField), but perform the actual
        # schema change idempotently so a half-applied DB can self-heal.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='job',
                    name='salary_yen',
                    field=models.PositiveIntegerField(blank=True, null=True),
                ),
                migrations.AddField(
                    model_name='job',
                    name='jlpt_level',
                    field=models.PositiveSmallIntegerField(blank=True, null=True),
                ),
                migrations.AddField(
                    model_name='jobranking',
                    name='llm_tier',
                    field=models.CharField(
                        blank=True,
                        choices=[('S', 'S Tier'), ('A', 'A Tier'), ('B', 'B Tier'), ('C', 'C Tier'), ('F', 'F Tier')],
                        max_length=2,
                        null=True,
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(ensure_columns, migrations.RunPython.noop),
            ],
        ),
        migrations.RunPython(populate_derived_fields, migrations.RunPython.noop),
    ]
