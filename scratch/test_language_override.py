import sys
import os

# Add job-hunt root to python path to import persistence
sys.path.append("/app")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from persistence import detect_job_language

test_cases = [
    # 1. Business Level Japanese Required in English text
    {
        "input": {
            "language": "ENGLISH",
            "description": "We are seeking a Backend Engineer. Business Level Japanese Required for regular client communication.",
            "title": "Software Engineer"
        },
        "expected": "JP",
        "description": "Business Level Japanese Required override"
    },
    # 2. all text in japanese instruction
    {
        "input": {
            "language": "English",
            "description": "All text in Japanese. The documentation is entirely in Japanese.",
            "title": "React Developer"
        },
        "expected": "JP",
        "description": "all text in japanese override"
    },
    # 3. Japanese: Business Level Required
    {
        "input": {
            "language": "EN",
            "description": "Japanese: Business Level Required",
            "title": "DevOps Engineer"
        },
        "expected": "JP",
        "description": "Japanese: Business Level Required override"
    },
    # 4. Language: Japanese and English
    {
        "input": {
            "language": "english",
            "description": "Language: Japanese and English. Candidate must speak both.",
            "title": "System Architect"
        },
        "expected": "JP",
        "description": "Language: Japanese and English override"
    },
    # 5. Japanese is a plus (should NOT override)
    {
        "input": {
            "language": "ENGLISH",
            "description": "English only environment. Japanese is a plus but not required.",
            "title": "Full Stack Engineer"
        },
        "expected": "EN",
        "description": "Japanese is a plus (stays EN)"
    },
    # 6. Basic English/Japanese synonyms mapping
    {
        "input": {
            "language": "JAPANESE",
            "description": "開発チームに参加してください。",
            "title": "バックエンド開発"
        },
        "expected": "JP",
        "description": "JAPANESE -> JP mapping"
    },
    {
        "input": {
            "language": "ENGLISH",
            "description": "Regular developer role.",
            "title": "Developer"
        },
        "expected": "EN",
        "description": "ENGLISH -> EN mapping"
    },
    # 7. Japanese characters in fallback
    {
        "input": {
            "language": "",
            "description": "開発チームに参加してください。",
            "title": "Webエンジニア"
        },
        "expected": "JP",
        "description": "Japanese characters detection fallback"
    },
    # 8. Non-english
    {
        "input": {
            "language": "non-english",
            "description": "Candidat doit parler français.",
            "title": "Ingénieur"
        },
        "expected": "non-english",
        "description": "non-english stays non-english"
    }
]

failed = 0
print("Running detect_job_language test suite:")
print("-" * 50)

for i, case in enumerate(test_cases, 1):
    result = detect_job_language(case["input"])
    status = "🟢 PASS" if result == case["expected"] else "🔴 FAIL"
    print(f"Test {i}: {case['description']}")
    print(f"  Input Language: {case['input'].get('language')}")
    print(f"  Result:         {result} (Expected: {case['expected']})")
    print(f"  Status:         {status}")
    print()
    if result != case["expected"]:
        failed += 1

print("-" * 50)
if failed == 0:
    print("🎉 All tests passed successfully!")
    sys.exit(0)
else:
    print(f"❌ {failed} tests failed.")
    sys.exit(1)
