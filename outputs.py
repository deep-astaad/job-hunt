import requests
from datetime import datetime
from config import DISCORD_WEBHOOK_URL, DISCORD_WEBHOOK_URL_REMOTE, DISCORD_TOP_N_JOBS, DJANGO_API_URL
from locations import region_for_text

class ExportHandler:
    @classmethod
    def post_single_job_to_discord(cls, job_data, s_a_rankings):
        """Send a single job to Discord based on location and tier."""
        color_map = {"S": 3066993, "A": 3447003}
        best_tier = "A"
        if any(r["match_tier"] == "S" for r in s_a_rankings):
            best_tier = "S"

        region, _, _ = region_for_text(job_data.get("location", ""))
        is_japan = region == "japan"

        target_webhook = None
        if is_japan:
            if DISCORD_WEBHOOK_URL:
                target_webhook = DISCORD_WEBHOOK_URL
        else:
            if best_tier == "S" and DISCORD_WEBHOOK_URL_REMOTE:
                target_webhook = DISCORD_WEBHOOK_URL_REMOTE

        if not target_webhook:
            return

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
            requests.post(target_webhook, json={"embeds": [embed]}, timeout=10)
        except requests.RequestException as e:
            print(f"⚠️ Failed to send job {job_data.get('id')} to Discord: {e}")

    @classmethod
    def post_tiered_jobs_from_api(cls, profile_id=None):
        """Fetch S/A ranked jobs from the today-ranked API and send to Discord."""
        if not DISCORD_WEBHOOK_URL and not DISCORD_WEBHOOK_URL_REMOTE:
            print("⚠️ Skipping Discord: No DISCORD_WEBHOOK_URL set.")
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
        
        # Fetch today's tier stats to provide a summary
        tier_counts = {"S": 0, "A": 0, "B": 0, "C": 0, "F": 0}
        try:
            stats_resp = requests.get(f"{DJANGO_API_URL}/api/jobs/today-all-rankings/", timeout=30)
            if stats_resp.status_code == 200:
                stats_data = stats_resp.json().get("results", [])
                tier_order = {"S": 0, "A": 1, "B": 2, "C": 3, "F": 4}
                for job_stat in stats_data:
                    rankings = job_stat.get("rankings", [])
                    if profile_id:
                        rankings = [r for r in rankings if r.get("profile_id") == profile_id]
                    if rankings:
                        best_ranking = min(rankings, key=lambda r: tier_order.get(r.get("match_tier", "F"), 99))
                        best_tier = best_ranking.get("match_tier", "F")
                        if best_tier in tier_counts:
                            tier_counts[best_tier] += 1
        except Exception as e:
            print(f"⚠️ Failed to fetch today's stats for Discord summary: {e}")

        # Header message
        header = f"🔔 **Today's Top-Ranked Jobs** ({data['date']})"
        if profile_id:
            header += f"\n🎯 Profile: `{profile_id}`"
            
        summary_str = " | ".join([f"**{t}:** {tier_counts[t]}" for t in ["S", "A", "B", "C", "F"]])
        header += f"\n📊 **Summary:** {summary_str}"
        header += f"\n{'-'*40}"
        # Send embeds in batches of 10
        japan_embeds = []
        remote_embeds = []

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

            region, _, _ = region_for_text(job.get("location", ""))
            if region == "japan":
                japan_embeds.append(embed)
            else:
                if tier == "S":
                    remote_embeds.append(embed)

        def _send_batches(webhook_url, embeds):
            if not webhook_url:
                return
            batch = []
            for e in embeds:
                batch.append(e)
                if len(batch) == 10:
                    requests.post(webhook_url, json={"embeds": batch})
                    batch = []
            if batch:
                requests.post(webhook_url, json={"embeds": batch})

        if DISCORD_WEBHOOK_URL:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": header})
            _send_batches(DISCORD_WEBHOOK_URL, japan_embeds)
            
        if DISCORD_WEBHOOK_URL_REMOTE:
            # Optionally send the summary header to the remote channel too, or a modified one
            remote_header = f"🔔 **Today's Top-Ranked Remote/Other Jobs (S Tier Only)** ({data['date']})"
            requests.post(DISCORD_WEBHOOK_URL_REMOTE, json={"content": remote_header})
            _send_batches(DISCORD_WEBHOOK_URL_REMOTE, remote_embeds)

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