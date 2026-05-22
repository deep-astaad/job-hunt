import csv
import re
import requests
from datetime import datetime
from config import DISCORD_WEBHOOK_URL, DISCORD_TOP_N_JOBS

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