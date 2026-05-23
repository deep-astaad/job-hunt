import json
import re
from openai import OpenAI
from config import OPENAI_API_KEY


class JobRankerAI:
    BATCH_SIZE = 10

    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_API_KEY)

    def _read_file(self, filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()

    def _load_json(self, filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _parse_experience_years(experience_str):
        match = re.search(r'(\d+)', experience_str)
        return int(match.group(1)) if match else None

    def _parse_ranking_table(self, markdown_text):
        """Extract structured rows from a ranking markdown table."""
        lines = [l.strip() for l in markdown_text.strip().split('\n') if l.strip().startswith('|')]
        if len(lines) < 3:
            return []
        rows = []
        for line in lines[2:]:
            cells = [c.strip() for c in line.split('|')[1:-1]]
            if len(cells) >= 8:
                rows.append(cells)
        return rows

    def _rank_batch(self, batch, profile, system_prompt):
        """Send one batch of jobs to gpt-4.1-nano and return the markdown table."""
        user_content = f"CANDIDATE PROFILE:\n{json.dumps(profile, indent=2)}\n\nJOB DATA:\n{json.dumps(batch, indent=2)}"

        response = self.client.chat.completions.create(
            model="gpt-4.1-nano-2025-04-14",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content

    def _merge_tables(self, all_rows, profile, system_prompt):
        """Send all batch results to gpt-4o-mini for a single unified ranking."""
        header = "| Rank | Match Tier (S/A/B/C/F) | Job Title & Company | Salary Range | Exp. Req | Language (EN/JP) | JD Summary | URL |"
        separator = "|------|------------------------|---------------------|--------------|----------|-------------------|------------|-----|"
        table_rows = [f"| {'|'.join(r)} |" for r in all_rows]
        combined_table = "\n".join([header, separator] + table_rows)

        merge_prompt = (
            "You are given multiple partial ranking tables of the same job data, "
            "each ranked independently. Re-rank ALL jobs into a single unified table.\n\n"
            "Rules:\n"
            "1. Use the Match Tier (S/A/B/C/F) and summary info already provided.\n"
            "2. Re-assign Rank from 1 to N based on tier (S first, then A, B, C, F) "
            "and within each tier keep the existing relative order.\n"
            "3. If jobs have different tiers across batches, respect the tier -- S > A > B > C > F.\n"
            "4. Preserve all original row data (title, salary, exp, lang, summary, URL).\n\n"
            "Output format: a single Markdown table with the same columns. No text before or after."
        )

        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": merge_prompt},
                {"role": "user", "content": combined_table},
            ],
            temperature=0.1,
        )
        return response.choices[0].message.content

    def generate_rankings(self, minimized_jobs, profile_id="backend_dev"):
        """Matches data vectors against a target profile via gpt-4.1-nano in batches."""
        system_prompt = self._read_file("system-prompt.txt")
        profiles = self._load_json("user-profiles.json")

        selected_profile = next((p for p in profiles if p["id"] == profile_id), profiles[0])
        selected_profile["experience_years"] = self._parse_experience_years(selected_profile["experience"])

        batches = [
            minimized_jobs[i : i + self.BATCH_SIZE]
            for i in range(0, len(minimized_jobs), self.BATCH_SIZE)
        ]

        print(f"🧠 Phase 3: Ranking {len(minimized_jobs)} jobs via gpt-4.1-nano ({len(batches)} batches)...")

        all_rows = []
        for i, batch in enumerate(batches):
            print(f"   -> Ranking batch {i + 1}/{len(batches)} ({len(batch)} jobs)...")
            try:
                table = self._rank_batch(batch, selected_profile, system_prompt)
                rows = self._parse_ranking_table(table)
                all_rows.extend(rows)
                print(f"   ✅ Batch {i + 1}: {len(rows)} jobs ranked")
            except Exception as e:
                print(f"   ❌ Batch {i + 1} failed: {e}")

        if not all_rows:
            print("   ⚠️ No jobs ranked. Returning empty table.")
            empty_table = (
                "| Rank | Match Tier (S/A/B/C/F) | Job Title & Company | Salary Range | Exp. Req | Language (EN/JP) | JD Summary | URL |\n"
                "|------|------------------------|---------------------|--------------|----------|-------------------|------------|-----|"
            )
            return empty_table, selected_profile["title"]

        if len(batches) > 1:
            print(f"   -> Merging {len(all_rows)} ranked jobs into unified table via gpt-4o-mini...")
            try:
                merged = self._merge_tables(all_rows, selected_profile, system_prompt)
                if "```" in merged:
                    merged = merged.split("```")[1] if merged.count("```") >= 2 else merged
                    if merged.strip().startswith("markdown"):
                        merged = merged.strip().split("\n", 1)[1] if "\n" in merged else merged
                print("   ✅ Merge complete.")
                return merged.strip(), selected_profile["title"]
            except Exception as e:
                print(f"   ⚠️ Merge failed: {e}. Falling back to raw concatenated tables.")

        # Single batch or merge failed -- just concatenate
        header = "| Rank | Match Tier (S/A/B/C/F) | Job Title & Company | Salary Range | Exp. Req | Language (EN/JP) | JD Summary | URL |"
        separator = "|------|------------------------|---------------------|--------------|----------|-------------------|------------|-----|"
        rows_str = "\n".join([f"| {'|'.join(r)} |" for r in all_rows])
        return "\n".join([header, separator, rows_str]), selected_profile["title"]
