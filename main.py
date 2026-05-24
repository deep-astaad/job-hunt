import json
from tasks.pipeline import run_pipeline

PROFILE_IDS = ["backend_dev", "cloud_infra"]


def main():
    print("Booting Celery-based Job Aggregator Engine...")

    with open("actor-config.json") as f:
        actor_configs = json.load(f)

    result = run_pipeline.delay(actor_configs, PROFILE_IDS)
    print(f"Pipeline dispatched. Task ID: {result.id}")
    print("Monitor: celery -A celery_app inspect active")


if __name__ == "__main__":
    main()
