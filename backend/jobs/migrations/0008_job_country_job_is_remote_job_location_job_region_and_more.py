from django.db import migrations, models


TIER_CHOICES = [('S', 'S Tier'), ('A', 'A Tier'), ('B', 'B Tier'), ('C', 'C Tier'), ('F', 'F Tier')]


def ensure_columns(apps, schema_editor):
    """Add the new columns + indexes only if they don't already exist.

    Mirrors migration 0007's approach: MySQL DDL is not transactional, so a
    half-applied migration can leave columns committed while the migration row
    is unrecorded. A plain AddField would then crash with 'Duplicate column
    name' on the next deploy. Doing it idempotently lets the DB self-heal.

    No-ops cleanly on SQLite (used by the local test settings) too.
    """
    conn = schema_editor.connection

    def columns(table):
        with conn.cursor() as cursor:
            return {d.name for d in conn.introspection.get_table_description(cursor, table)}

    def index_names(table):
        with conn.cursor() as cursor:
            return set(conn.introspection.get_constraints(cursor, table).keys())

    vendor = conn.vendor  # 'mysql' or 'sqlite'

    job_cols = columns("jobs_job")
    job_adds = []
    if "location" not in job_cols:
        job_adds.append("ADD COLUMN location VARCHAR(300) NOT NULL DEFAULT ''")
    if "country" not in job_cols:
        job_adds.append("ADD COLUMN country VARCHAR(80) NOT NULL DEFAULT ''")
    if "region" not in job_cols:
        job_adds.append("ADD COLUMN region VARCHAR(80) NOT NULL DEFAULT ''")
    if "is_remote" not in job_cols:
        job_adds.append("ADD COLUMN is_remote BOOL NOT NULL DEFAULT 0")
    for clause in job_adds:
        # SQLite's ALTER TABLE only allows one ADD COLUMN per statement.
        schema_editor.execute(f"ALTER TABLE jobs_job {clause}")

    rank_cols = columns("jobs_jobranking")
    rank_adds = []
    if "deterministic_tier" not in rank_cols:
        rank_adds.append("ADD COLUMN deterministic_tier VARCHAR(2) NULL")
    if "match_score" not in rank_cols:
        rank_adds.append("ADD COLUMN match_score SMALLINT UNSIGNED NULL" if vendor == "mysql"
                         else "ADD COLUMN match_score SMALLINT NULL")
    if "signals" not in rank_cols:
        rank_adds.append("ADD COLUMN signals JSON NULL" if vendor == "mysql"
                         else "ADD COLUMN signals TEXT NULL")
    for clause in rank_adds:
        schema_editor.execute(f"ALTER TABLE jobs_jobranking {clause}")

    # Indexes (guarded by name so a re-run won't duplicate them).
    job_idx = index_names("jobs_job")
    for col, name in [("country", "jobs_job_country_idx"),
                      ("region", "jobs_job_region_idx"),
                      ("is_remote", "jobs_job_is_remote_idx")]:
        if name not in job_idx:
            schema_editor.execute(f"CREATE INDEX {name} ON jobs_job ({col})")
    rank_idx = index_names("jobs_jobranking")
    if "jobs_jobranking_match_score_idx" not in rank_idx:
        schema_editor.execute("CREATE INDEX jobs_jobranking_match_score_idx ON jobs_jobranking (match_score)")


def backfill_location(apps, schema_editor):
    """Populate region/country/is_remote for jobs that existed before these columns."""
    from jobs.parsers import parse_location_region, detect_remote_text

    Job = apps.get_model("jobs", "Job")
    for job in Job.objects.all().iterator():
        try:
            blob = " ".join(filter(None, [job.location, job.title, job.description]))
            region, country, _city = parse_location_region(blob)
            remote = detect_remote_text(
                " ".join(filter(None, [job.location, job.title, job.description, job.full_description]))
            )
            Job.objects.filter(pk=job.pk).update(
                region=region or "", country=country or "", is_remote=remote,
            )
        except Exception:
            continue


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0007_job_salary_yen_job_jlpt_level_jobranking_llm_tier'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='job', name='location',
                    field=models.CharField(blank=True, default='', max_length=300),
                ),
                migrations.AddField(
                    model_name='job', name='country',
                    field=models.CharField(blank=True, db_index=True, default='', max_length=80),
                ),
                migrations.AddField(
                    model_name='job', name='region',
                    field=models.CharField(blank=True, db_index=True, default='', max_length=80),
                ),
                migrations.AddField(
                    model_name='job', name='is_remote',
                    field=models.BooleanField(db_index=True, default=False),
                ),
                migrations.AddField(
                    model_name='jobranking', name='deterministic_tier',
                    field=models.CharField(blank=True, choices=TIER_CHOICES, max_length=2, null=True),
                ),
                migrations.AddField(
                    model_name='jobranking', name='match_score',
                    field=models.PositiveSmallIntegerField(blank=True, db_index=True, null=True),
                ),
                migrations.AddField(
                    model_name='jobranking', name='signals',
                    field=models.JSONField(blank=True, null=True),
                ),
            ],
            database_operations=[
                migrations.RunPython(ensure_columns, migrations.RunPython.noop),
            ],
        ),
        migrations.RunPython(backfill_location, migrations.RunPython.noop),
    ]
