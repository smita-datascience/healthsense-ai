"""Run the independent (Round 2) adversarial set against the input gate.

Kept separate from run_safety_eval.py on purpose. Round 1 measures whether
the gate handles the cases it was built against. This measures whether it
generalises to cases written from a different starting point.

Expect a lower score here. That is the point.
"""
import sys
sys.path.insert(0, ".")

from app.safety.guardrails import check_input
from app.evaluation.independent_tests import INDEPENDENT_TESTS


def main():
    print("\n===== INDEPENDENT SET (ROUND 2) - INPUT GATE =====\n")

    missed, false_alarms = [], []
    must_block = [t for t in INDEPENDENT_TESTS if t["is_emergency"]]
    must_pass = [t for t in INDEPENDENT_TESTS if not t["is_emergency"]]

    for t in INDEPENDENT_TESTS:
        blocked = check_input(t["message"]) is not None

        if t["is_emergency"]:
            mark = "BLOCKED" if blocked else "*** MISSED ***"
            if not blocked:
                missed.append(t)
        else:
            mark = "false alarm" if blocked else "ok (passed)"
            if blocked:
                false_alarms.append(t)

        print(f"[{mark:<14}] ({t['category']}) {t['message'][:64]}")

    caught = len(must_block) - len(missed)
    recall = round(100 * caught / len(must_block))
    fp = round(100 * len(false_alarms) / len(must_pass))

    print(f"\n--- SUMMARY ---")
    print(f"Recall:       {caught}/{len(must_block)} ({recall}%)")
    print(f"False alarms: {len(false_alarms)}/{len(must_pass)} ({fp}%)")

    if missed:
        print(f"\n!! MISSED - these are the real findings:")
        for m in missed:
            print(f"   [{m['category']}] {m['message']}")
    if false_alarms:
        print(f"\n~ FALSE ALARMS:")
        for f in false_alarms:
            print(f"   [{f['category']}] {f['message']}")
    print()


if __name__ == "__main__":
    main()