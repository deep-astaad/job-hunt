import json
import re
from openai import OpenAI
from config import OPENAI_API_KEY


class JobRankerAI:

    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_API_KEY)

    def _read_file(self, filepath):
        import os
        base_dir = os.path.dirname(os.path.abspath(__file__))
        abs_path = os.path.join(base_dir, filepath)
        with open(abs_path, "r", encoding="utf-8") as f:
            return f.read()

    def _load_json(self, filepath):
        import os
        base_dir = os.path.dirname(os.path.abspath(__file__))
        abs_path = os.path.join(base_dir, filepath)
        with open(abs_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _parse_experience_years(experience_str):
        match = re.search(r'(\d+)', experience_str)
        return int(match.group(1)) if match else None

    @staticmethod
    def _parse_ranking_table(markdown_text):
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

    @staticmethod
    def _apply_hard_rules(rows):
        """Override tier to F for jobs requiring Japanese or >4 years experience."""
        filtered = []
        for row in rows:
            exp_text = row[4].lower() if len(row) > 4 else ""
            lang_text = row[5].lower() if len(row) > 5 else ""

            is_jp_required = any(kw in lang_text for kw in ["jp", "japanese", "jlpt"])
            match = re.search(r'(\d+)', exp_text)
            exp_years = int(match.group(1)) if match else None
            is_experienced = exp_years is not None and exp_years > 4

            if is_jp_required or is_experienced:
                row[1] = "F"

            filtered.append(row)
        return filtered
