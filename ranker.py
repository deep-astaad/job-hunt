import json


class JobRankerAI:

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

