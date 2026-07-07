"""Red-team the safety gate: run all safety tests, measure recall + false alarms."""
import sys
sys.path.insert(0, ".")

from app.safety.guardrails import check_input
from app.evaluation.safety_tests import SAFETY_TESTS


def main():
    print("\n===== SAFETY GATE — RED TEAM REPORT =====\n")

    missed = []        # real emergencies that slipped through (DANGEROUS)
    false_alarms = []  # safe questions wrongly flagged (annoying)
    emergencies = [t for t in SAFETY_TESTS if t["is_emergency"]]
    safe = [t for t in SAFETY_TESTS if not t["is_emergency"]]

    for t in SAFETY_TESTS:
        flagged = check_input(t["message"]) is not None
        if t["is_emergency"]:
            mark = "CAUGHT" if flagged else "*** MISSED ***"
            if not flagged:
                missed.append(t["message"])
        else:
            mark = "false alarm" if flagged else "ok (safe)"
            if flagged:
                false_alarms.append(t["message"])
        print(f"[{mark}] {t['message']}")

    # Recall = of the real emergencies, how many did we catch?
    caught = len(emergencies) - len(missed)
    recall = round(100 * caught / len(emergencies))

    print(f"\n--- SUMMARY ---")
    print(f"Emergency recall: {caught}/{len(emergencies)} caught ({recall}%)")
    print(f"False alarms: {len(false_alarms)}/{len(safe)} safe questions flagged")
    if missed:
        print(f"\n⚠ MISSED EMERGENCIES (fix these):")
        for m in missed:
            print(f"   - {m}")
    print()


if __name__ == "__main__":
    main()