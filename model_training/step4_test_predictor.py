import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
"""
STEP 4 — Test the Predictor
Loads all saved models and runs sample predictions.
Shows what the bug report will look like from the backend.
"""

import json
import sys
import os

# Make sure predictor.py is importable
sys.path.insert(0, os.path.dirname(__file__))
from predictor import BugPredictor

print("=" * 60)
print("  STEP 4 — TESTING PREDICTOR")
print("=" * 60)

predictor = BugPredictor()

# ─── Test cases (simulating real code metrics) ────────────────────────────────
test_files = [
    {
        "file_name": "UserService.java",
        "bug_id"   : 1,
        "metrics"  : {
            # High CBO + RFC → likely Crash bug
            "wmc": 14, "dit": 3,  "noc": 2,  "cbo": 22,
            "rfc": 52, "lcom": 70,"ca": 5,   "ce": 10,
            "npm": 9,  "lcom3": 0.8, "loc": 310,
            "dam": 0.7,"moa": 2,  "mfa": 0.3,"cam": 0.2,
            "ic": 1,   "cbm": 2,  "amc": 30,
            "max_cc": 9, "avg_cc": 3.5,
        }
    },
    {
        "file_name": "PaymentCalculator.java",
        "bug_id"   : 2,
        "metrics"  : {
            # High WMC + LCOM + CC → likely Logical bug
            "wmc": 28, "dit": 2,   "noc": 1,  "cbo": 9,
            "rfc": 30, "lcom": 145,"ca": 3,   "ce": 6,
            "npm": 15, "lcom3": 0.9,"loc": 450,
            "dam": 0.5,"moa": 1,   "mfa": 0.2,"cam": 0.15,
            "ic": 0,   "cbm": 1,   "amc": 40,
            "max_cc": 18, "avg_cc": 7.2,
        }
    },
    {
        "file_name": "ReportEngine.java",
        "bug_id"   : 3,
        "metrics"  : {
            # High LOC + DIT + NOC → likely Performance bug
            "wmc": 32, "dit": 6,   "noc": 10, "cbo": 14,
            "rfc": 42, "lcom": 90, "ca": 8,   "ce": 12,
            "npm": 22, "lcom3": 0.7,"loc": 780,
            "dam": 0.8,"moa": 4,   "mfa": 0.5,"cam": 0.3,
            "ic": 2,   "cbm": 3,   "amc": 55,
            "max_cc": 12, "avg_cc": 4.5,
        }
    },
    {
        "file_name": "LoginButton.java",
        "bug_id"   : 4,
        "metrics"  : {
            # Low everything → likely UI or clean
            "wmc": 4,  "dit": 1,   "noc": 0,  "cbo": 3,
            "rfc": 12, "lcom": 15, "ca": 1,   "ce": 2,
            "npm": 3,  "lcom3": 0.2,"loc": 85,
            "dam": 0.5,"moa": 0,   "mfa": 0.1,"cam": 0.6,
            "ic": 0,   "cbm": 0,   "amc": 18,
            "max_cc": 2, "avg_cc": 1.2,
        }
    },
    {
        "file_name": "CleanClass.java",
        "bug_id"   : 5,
        "metrics"  : {
            # Well-structured class — should return None (no bug)
            "wmc": 6,  "dit": 1,   "noc": 0,  "cbo": 4,
            "rfc": 14, "lcom": 10, "ca": 2,   "ce": 3,
            "npm": 5,  "lcom3": 0.1,"loc": 95,
            "dam": 0.9,"moa": 1,   "mfa": 0.8,"cam": 0.7,
            "ic": 0,   "cbm": 0,   "amc": 15,
            "max_cc": 2, "avg_cc": 1.0,
        }
    },
]

# ─── Run predictions ──────────────────────────────────────────────────────────
print("\n  Running predictions on 5 test files...\n")
bugs_found = []

for rec in test_files:
    result = predictor.predict(
        metrics   = rec["metrics"],
        file_name = rec["file_name"],
        bug_id    = rec["bug_id"]
    )

    if result:
        bugs_found.append(result)
        print(f"  BUG {rec['file_name']}")
        print(f"     Bug ID       : {result['bug_id']}")
        print(f"     Type         : {result['type']}")
        print(f"     Severity     : {result['severity']}")
        print(f"     Line Number  : {result['line_number']}")
        print(f"     Confidence   : {result['defect_probability']*100:.1f}%")
        print(f"     Assigned To  : {result['assigned_to']}")
        print(f"     AI Reason    : {result['ai_reason']}")
        print(f"     Fix          : {result['suggested_fix']}")
        print()
    else:
        print(f"  OK  {rec['file_name']} — No bug detected (clean)")
        print()

# ─── Summary ──────────────────────────────────────────────────────────────────
print("─" * 60)
print(f"  Files analyzed : {len(test_files)}")
print(f"  Bugs detected  : {len(bugs_found)}")
print(f"  Clean files    : {len(test_files) - len(bugs_found)}")

if bugs_found:
    from collections import Counter
    type_counts = Counter(b['type'] for b in bugs_found)
    sev_counts  = Counter(b['severity'] for b in bugs_found)
    print(f"\n  Bug Types      : {dict(type_counts)}")
    print(f"  Severities     : {dict(sev_counts)}")

# ─── Save sample output ───────────────────────────────────────────────────────
out_path = os.path.join(os.path.dirname(__file__),
                        "saved_models", "sample_output.json")
with open(out_path, 'w') as f:
    json.dump(bugs_found, f, indent=2)
print(f"\n  Sample output saved → saved_models/sample_output.json")

print("\n" + "=" * 60)
print("  STEP 4 COMPLETE — Predictor is working!")
print("=" * 60)
