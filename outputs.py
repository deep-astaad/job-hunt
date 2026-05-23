import csv
import re
import requests
from datetime import datetime
from config import DISCORD_WEBHOOK_URL, DISCORD_TOP_N_JOBS, DJANGO_API_URL

class ExportHandler:
    @staticmethod
    def parse_markdown_table_to_csv(markdown_text, csv_filepath):
        """Converts Markdown pipelines cleanly back into raw CSV data rows."""
        lines = [line.strip() for line in markdown_text.strip().split('\n') if line.strip().startswith('|')]
        if len(lines) < 3:
            print("⚠️ Skipping CSV creation: Markdown matrix was malformed.")
            return

        headers = [cell.strip() for cell in lines[0].split('|')[1:-1]]
        with open(csv_filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for line in lines[2:]:
                row = [cell.strip() for cell in line.split('|')[1:-1]]
                writer.writerow(row)
        print(f"💾 CSV dataset recorded cleanly to local storage: {csv_filepath}")

    @staticmethod
    def _extract_url_from_markdown(text):
        match = re.search(r'\((https?://[^\)]+)\)', text)
        return match.group(1) if match else None

    @classmethod
    def post_embeds_to_discord(cls, markdown_text, profile_title):
        """Dispatches structural card objects to a remote Discord channel target."""
        if not DISCORD_WEBHOOK_URL:
            print("⚠️ Skipping Discord pipeline distribution: Target webhook token missing.")
            return

        lines = [line.strip() for line in markdown_text.strip().split('\n') if line.strip().startswith('|')]
        if len(lines) < 3:
            return

        # Broadcast initial metadata panel 
        requests.post(DISCORD_WEBHOOK_URL, json={
            "content": f"🔔 **New Daily AI-Ranked Job Postings Match Run**\n🎯 *Target Profile:* {profile_title}\n{'-'*40}"
        })

        color_map = {"S": 3066993, "A": 3447003, "B": 15844367, "C": 15105570, "F": 15158332}
        embeds_batch = []

        for line in lines[2:2 + DISCORD_TOP_N_JOBS]:
            cells = [cell.strip() for cell in line.split('|')[1:-1]]
            if len(cells) < 8:
                continue

            rank, tier, title_company, salary, exp, lang, summary, url_cell = cells
            raw_url = cls._extract_url_from_markdown(url_cell)

            embed = {
                "title": f"#{rank} | {title_company}",
                "description": f"**Summary:** {summary}",
                "url": raw_url,
                "color": color_map.get(tier.upper(), 8421504),
                "fields": [
                    {"name": "🎯 Match Tier", "value": f"**{tier}**", "inline": True},
                    {"name": "🌐 Language", "value": lang, "inline": True},
                    {"name": "💰 Salary", "value": salary, "inline": True},
                    {"name": "💼 Exp. Req", "value": exp, "inline": True}
                ],
                "footer": {"text": f"Pipeline Automated Run | {datetime.now().strftime('%Y-%m-%d')}"}
            }
            embeds_batch.append(embed)

            if len(embeds_batch) == 10:
                requests.post(DISCORD_WEBHOOK_URL, json={"embeds": embeds_batch})
                embeds_batch = []

        if embeds_batch:
            requests.post(DISCORD_WEBHOOK_URL, json={"embeds": embeds_batch})
        print("✅ Structured embed elements pushed to Discord channels perfectly.")

    @classmethod
    def post_tiered_jobs_from_api(cls, profile_id=None):
        """Fetch S/A ranked jobs from the today-ranked API and send to Discord."""
        if not DISCORD_WEBHOOK_URL:
            print("⚠️ Skipping Discord: DISCORD_WEBHOOK_URL not set.")
            return

        params = {"tiers": "S,A"}
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

        print(f"✅ Sent {min(len(jobs), DISCORD_TOP_N_JOBS)} S/A ranked jobs to Discord.")