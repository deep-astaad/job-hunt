import requests
from datetime import datetime
from config import DISCORD_WEBHOOK_URL_DEFAULT, DISCORD_WEBHOOK_URL_JAPAN, DISCORD_WEBHOOK_URL_REMOTE, DISCORD_WEBHOOK_URL_INDIA, DISCORD_TOP_N_JOBS, DJANGO_API_URL
from locations import region_for_text

class ExportHandler:
    @classmethod
    def post_single_job_to_discord(cls, job_data, s_a_rankings):
        """Send a single job to Discord based on location and tier."""
        color_map = {"S": 3066993, "A": 3447003}
        best_tier = "A"
        if any(r["match_tier"] == "S" for r in s_a_rankings):
            best_tier = "S"

        region = str(job_data.get("region", "")).lower()
        loc = str(job_data.get("location", "")).lower()
        if not region:
            region, _, _ = region_for_text(loc)

        target_webhook = None
        if region == "japan":
            target_webhook = DISCORD_WEBHOOK_URL_JAPAN
        elif region == "india":
            target_webhook = DISCORD_WEBHOOK_URL_INDIA
        elif job_data.get("is_remote") or "remote" in loc:
            if best_tier == "S":
                target_webhook = DISCORD_WEBHOOK_URL_REMOTE
        else:
            if best_tier == "S":
                target_webhook = DISCORD_WEBHOOK_URL_DEFAULT

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
            resp = requests.post(target_webhook, json={"embeds": [embed]}, timeout=10)
            resp.raise_for_status()
        except requests.RequestException as e:
            # Discord 429/4xx/5xx don't raise on their own — raise_for_status()
            # turns them into a RequestException so we DON'T mark the job sent.
            # The end-of-run summary (alert_sent=False) is then the backstop.
            print(f"⚠️ Failed to send job {job_data.get('id')} to Discord: {e}")
            return

        # Mark sent (only after a confirmed-OK post) so the summary doesn't re-post.
        job_id = job_data.get("id")
        if job_id:
            try:
                requests.post(
                    f"{DJANGO_API_URL}/api/jobs/mark_alerts_sent/",
                    json={"job_ids": [job_id]},
                    timeout=10,
                )
            except requests.RequestException:
                pass

    @classmethod
    def post_tiered_jobs_from_api(cls, profile_id=None):
        """Fetch S/A ranked jobs from the today-ranked API and send to Discord."""
        if not any([DISCORD_WEBHOOK_URL_DEFAULT, DISCORD_WEBHOOK_URL_JAPAN, DISCORD_WEBHOOK_URL_REMOTE, DISCORD_WEBHOOK_URL_INDIA]):
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
        india_embeds = []
        remote_embeds = []
        default_embeds = []

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

            region = str(job.get("region", "")).lower()
            loc = str(job.get("location", "")).lower()
            if not region:
                region, _, _ = region_for_text(loc)

            if region == "japan":
                japan_embeds.append(embed)
            elif region == "india":
                india_embeds.append(embed)
            elif job.get("is_remote") or "remote" in loc:
                if tier == "S":
                    remote_embeds.append(embed)
            else:
                if tier == "S":
                    default_embeds.append(embed)

        def _send_batches(webhook_url, embeds):
            # Raises requests.RequestException on any failed post so the caller
            # can avoid marking those jobs alert_sent.
            if not webhook_url:
                return
            batch = []
            for e in embeds:
                batch.append(e)
                if len(batch) == 10:
                    requests.post(webhook_url, json={"embeds": batch}, timeout=10).raise_for_status()
                    batch = []
            if batch:
                requests.post(webhook_url, json={"embeds": batch}, timeout=10).raise_for_status()

        # Only mark jobs alert_sent if their webhook batch actually posted OK,
        # otherwise the backstop would skip jobs whose summary post failed.
        send_failed = False
        try:
            if DISCORD_WEBHOOK_URL_JAPAN and japan_embeds:
                requests.post(DISCORD_WEBHOOK_URL_JAPAN, json={"content": header.replace("Top-Ranked Jobs", "Top-Ranked Japan Jobs")}, timeout=10)
                _send_batches(DISCORD_WEBHOOK_URL_JAPAN, japan_embeds)

            if DISCORD_WEBHOOK_URL_INDIA and india_embeds:
                requests.post(DISCORD_WEBHOOK_URL_INDIA, json={"content": header.replace("Top-Ranked Jobs", "Top-Ranked India Jobs")}, timeout=10)
                _send_batches(DISCORD_WEBHOOK_URL_INDIA, india_embeds)

            if DISCORD_WEBHOOK_URL_REMOTE and remote_embeds:
                remote_header = header.replace("Top-Ranked Jobs", "Top-Ranked Remote Jobs (S Tier Only)")
                requests.post(DISCORD_WEBHOOK_URL_REMOTE, json={"content": remote_header}, timeout=10)
                _send_batches(DISCORD_WEBHOOK_URL_REMOTE, remote_embeds)

            if DISCORD_WEBHOOK_URL_DEFAULT and default_embeds:
                default_header = header.replace("Top-Ranked Jobs", "Top-Ranked Other Jobs (S Tier Only)")
                requests.post(DISCORD_WEBHOOK_URL_DEFAULT, json={"content": default_header}, timeout=10)
                _send_batches(DISCORD_WEBHOOK_URL_DEFAULT, default_embeds)
        except requests.RequestException as e:
            send_failed = True
            print(f"⚠️ Discord summary send failed; not marking alerts sent: {e}")

        # Mark alerts as sent (only when the summary posts succeeded).
        job_ids = [job.get("id") for job in jobs[:DISCORD_TOP_N_JOBS] if job.get("id")]
        if job_ids and not send_failed:
            try:
                requests.post(
                    f"{DJANGO_API_URL}/api/jobs/mark_alerts_sent/",
                    json={"job_ids": job_ids},
                    timeout=10,
                )
            except requests.RequestException as e:
                print(f"⚠️ Failed to mark alerts as sent: {e}")

        print(f"✅ Sent {min(len(jobs), DISCORD_TOP_N_JOBS)} S/A ranked jobs to Discord.")