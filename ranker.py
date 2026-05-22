import json
import re
from openai import OpenAI
from config import OPENAI_API_KEY

class JobRankerAI:
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

    def generate_rankings(self, minimized_jobs, profile_id="backend_dev"):
        """Matches data vectors against a target profile via gpt-4.1-nano."""
        system_prompt = self._read_file("system-prompt.txt")
        profiles = self._load_json("user-profiles.json")
        
        # Pull matching profile dictionary block
        selected_profile = next((p for p in profiles if p["id"] == profile_id), profiles[0])
        selected_profile["experience_years"] = self._parse_experience_years(selected_profile["experience"])
        print(f"🧠 Phase 3: Commencing AI analysis against target profile layout: {selected_profile['title']}")

        user_content = f"CANDIDATE PROFILE:\n{json.dumps(selected_profile, indent=2)}\n\nJOB DATA:\n{json.dumps(minimized_jobs, indent=2)}"

        response = self.client.chat.completions.create(
            model="gpt-4.1-nano-2025-04-14",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.2
        )
        return response.choices[0].message.content, selected_profile["title"]