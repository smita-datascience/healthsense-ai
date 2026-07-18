


"""Red-team both safety gates: measure recall + false alarms for each.

Gate 1: emergency gate (input side)  -> check_input()
Gate 2: output guardrail (post-gen)  -> check_output()
"""
import sys
sys.path.insert(0, ".")

from app.safety.guardrails import check_input
# >>> EDIT THIS LINE if your output guardrail has a different name <<<
from app.safety.guardrails import check_output

from app.evaluation.safety_tests import EMERGENCY_TESTS, OUTPUT_TESTS


def run_gate(name, tests, fn, input_key, label_key, blocked_desc, passed_desc):
    """Generic red-team runner. A gate 'blocks' when fn() returns non-None."""
    print(f"\n===== {name} =====\n")

    missed, false_alarms = [], []
    must_block = [t for t in tests if t[label_key]]
    must_pass = [t for t in tests if not t[label_key]]

    for t in tests:
        text = t[input_key]
        blocked = fn(text) is not None

        if t[label_key]:
            mark = "BLOCKED" if blocked else "*** MISSED ***"
            if not blocked:
                missed.append(t)
        else:
            mark = "false alarm" if blocked else "ok (passed)"
            if blocked:
                false_alarms.append(t)

        print(f"[{mark:<14}] ({t['category']}) {text[:70]}")

    caught = len(must_block) - len(missed)
    recall = round(100 * caught / len(must_block)) if must_block else 0
    fp_rate = round(100 * len(false_alarms) / len(must_pass)) if must_pass else 0

    print(f"\n--- {name} SUMMARY ---")
    print(f"Recall:       {caught}/{len(must_block)} {blocked_desc} ({recall}%)")
    print(f"False alarms: {len(false_alarms)}/{len(must_pass)} {passed_desc} ({fp_rate}%)")

    if missed:
        print(f"\n!! MISSED (fix these):")
        for m in missed:
            print(f"   [{m['category']}] {m[input_key]}")
    if false_alarms:
        print(f"\n~ FALSE ALARMS (over-cautious, lower priority):")
        for f in false_alarms:
            print(f"   [{f['category']}] {f[input_key]}")

    return {"recall": recall, "caught": caught, "total": len(must_block),
            "false_alarms": len(false_alarms), "safe_total": len(must_pass)}


def main():
    g1 = run_gate(
        "GATE 1 — EMERGENCY GATE (input)",
        EMERGENCY_TESTS, check_input,
        input_key="message", label_key="is_emergency",
        blocked_desc="emergencies caught", passed_desc="safe questions flagged",
    )

    g2 = run_gate(
        "GATE 2 — OUTPUT GUARDRAIL (post-generation)",
        OUTPUT_TESTS, check_output,
        input_key="output", label_key="should_block",
        blocked_desc="unsafe outputs blocked", passed_desc="safe outputs blocked",
    )

    print("\n" + "=" * 55)
    print("HEADLINE NUMBERS")
    print("=" * 55)
    print(f"Emergency gate:   {g1['caught']}/{g1['total']} recall ({g1['recall']}%), "
          f"{g1['false_alarms']}/{g1['safe_total']} false alarms")
    print(f"Output guardrail: {g2['caught']}/{g2['total']} recall ({g2['recall']}%), "
          f"{g2['false_alarms']}/{g2['safe_total']} false alarms")
    print(f"Total red-team cases: {len(EMERGENCY_TESTS) + len(OUTPUT_TESTS)}")
    print()


if __name__ == "__main__":
    main()