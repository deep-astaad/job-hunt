import json
from celery_app import app
from ranker import JobRankerAI


@app.task(
    bind=True,
    name='tasks.ranking.rank_batch',
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=180,
)
def rank_batch(self, batch_jobs, profile_id):
    """Rank a batch of up to 10 jobs against a profile. Returns parsed table rows."""
    ranker = JobRankerAI()

    system_prompt = ranker._read_file("prompts/ranker.txt")
    profiles = ranker._load_json("user-profiles.json")
    selected_profile = next((p for p in profiles if p["id"] == profile_id), profiles[0])
    selected_profile["experience_years"] = ranker._parse_experience_years(selected_profile["experience"])

    try:
        table = ranker._rank_batch(batch_jobs, selected_profile, system_prompt)
        rows = ranker._parse_ranking_table(table)
        rows = ranker._apply_hard_rules(rows)
        return rows
    except Exception as exc:
        print(f"  Ranking batch failed for {profile_id}: {exc}")
        return []
