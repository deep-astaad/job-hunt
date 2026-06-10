import requests
from datetime import datetime
from config import DISCORD_WEBHOOK_URL, DISCORD_TOP_N_JOBS, DJANGO_API_URL

class ExportHandler:
    @classmethod
    def post_single_job_to_discord(cls, job_data, s_a_rankings):
        """Send a single job to Discord if it has S/A rankings."""
        if not DISCORD_WEBHOOK_URL:
            return

        color_map = {"S": 3066993, "A": 3447003}
        best_tier = "A"
        if any(r["match_tier"] == "S" for r in s_a_rankings):
            best_tier = "S"

        matched_profiles = ", ".join(r["profile_id"] for r in s_a_rankings)
        jd_summary = s_a_rankings[0]["jd_summary"] if s_a_rankings else "—"

        embed = {
            "title": f"{job_data.get('title', 'Unknown')} — {job_data.get('company', '')}",
            "description": (job_data.get("description", "") or "")[:300] or "No description",
            "url": job_data.get("url", ""),
            "color": color_map.get(best_tier, 8421504),
            "fields": [
                {"name": "🎯 Match Tier", "value": f"**{best_tier}**", "inline": True},
                {"name": "🌐 Language", "value": job_data.get("language", "—") or "—", "inline": True},
                {"name": "💰 Salary", "value": job_data.get("salary", "—") or "—", "inline": True},
                {"name": "💼 Exp. Req", "value": job_data.get("experience_required", "—") or "—", "inline": True},
                {"name": "👤 Matched Profile(s)", "value": matched_profiles or "—", "inline": False},
                {"name": "📝 Summary", "value": jd_summary or "—", "inline": False},
            ],
            "footer": {"text": f"Auto-ranked by AI | {datetime.now().strftime('%Y-%m-%d %H:%M')}"},
        }

        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]}, timeout=10)
        except requests.RequestException as e:
            print(f"⚠️ Failed to send job {job_data.get('id')} to Discord: {e}")

    @classmethod
    def post_tiered_jobs_from_api(cls, profile_id=None):
        """Fetch S/A ranked jobs from the today-ranked API and send to Discord."""
        if not DISCORD_WEBHOOK_URL:
            print("⚠️ Skipping Discord: DISCORD_WEBHOOK_URL not set.")
            return

        params = {"tiers": "S,A", "alert_sent": "False"}
        if profile_id:
            params["profile_id"] = profile_id

        try:
            response = requests.get(
                f"{DJANGO_API_URL}/api/jobs/today-ranked/",
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            print(f"⚠️ Failed to fetch today-ranked jobs: {e}")
            return

        jobs = data.get("results", [])
        if not jobs:
            print("ℹ️ No S/A ranked jobs found for today. Skipping Discord.")
            return

        color_map = {"S": 3066993, "A": 3447003}

        # Header message
        header = f"🔔 **Today's Top-Ranked Jobs** ({data['date']})"
        if profile_id:
            header += f"\n🎯 Profile: `{profile_id}`"
        header += f"\n{'-'*40}"
        requests.post(DISCORD_WEBHOOK_URL, json={"content": header})

        # Send embeds in batches of 10
        embeds_batch = []
        for job in jobs[:DISCORD_TOP_N_JOBS]:
            ranking = job.get("ranking", {})
            tier = ranking.get("match_tier", "")
            matched = ", ".join(
                p.get("profile_title", p["profile_id"])
                for p in job.get("matched_profiles", [])
            )

            embed = {
                "title": f"{job.get('title', 'Unknown')} — {job.get('company', '')}",
                "description": job.get("description", "")[:300] or "No description",
                "url": job.get("url", ""),
                "color": color_map.get(tier, 8421504),
                "fields": [
                    {"name": "🎯 Match Tier", "value": f"**{tier}**", "inline": True},
                    {"name": "🌐 Language", "value": job.get("language", "—"), "inline": True},
                    {"name": "💰 Salary", "value": job.get("salary", "—") or "—", "inline": True},
                    {"name": "💼 Exp. Req", "value": job.get("experience_required", "—") or "—", "inline": True},
                    {"name": "👤 Matched Profile(s)", "value": matched or "—", "inline": False},
                    {"name": "📝 Summary", "value": ranking.get("jd_summary", "—") or "—", "inline": False},
                ],
                "footer": {"text": f"Auto-ranked by AI | {datetime.now().strftime('%Y-%m-%d %H:%M')}"},
            }
            embeds_batch.append(embed)

            if len(embeds_batch) == 10:
                requests.post(DISCORD_WEBHOOK_URL, json={"embeds": embeds_batch})
                embeds_batch = []

        if embeds_batch:
            requests.post(DISCORD_WEBHOOK_URL, json={"embeds": embeds_batch})

        # Mark alerts as sent
        job_ids = [job.get("id") for job in jobs[:DISCORD_TOP_N_JOBS] if job.get("id")]
        if job_ids:
            try:
                requests.post(
                    f"{DJANGO_API_URL}/api/jobs/mark_alerts_sent/",
                    json={"job_ids": job_ids},
                    timeout=10,
                )
            except requests.RequestException as e:
                print(f"⚠️ Failed to mark alerts as sent: {e}")

        print(f"✅ Sent {min(len(jobs), DISCORD_TOP_N_JOBS)} S/A ranked jobs to Discord.")