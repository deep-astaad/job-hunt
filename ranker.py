import json
from openai import OpenAI
from config import get_openai_api_keys, get_openai_base_url


class JobRankerAI:

    @property
    def client(self):
        import random
        keys = get_openai_api_keys()
        return OpenAI(api_key=random.choice(keys) if keys else None, base_url=get_openai_base_url())

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

