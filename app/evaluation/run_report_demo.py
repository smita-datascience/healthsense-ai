"""Try the lab report reader on a file, without WhatsApp.

Usage:
  python -m app.evaluation.run_report_demo sample_reports/sample_blood_report.png
  python -m app.evaluation.run_report_demo sample_reports/sample_blood_report.pdf --caption "yeh meri report hai, samjhao"

Shows every step: the table Claude read (with the status Python computed),
whether the guardrail blocked the explanation, and the final reply. The final
reply is also saved to report_reply.txt (easier to read Hindi there).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, ".")

from app.agents.report import explain_report

MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".pdf": "application/pdf"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--caption", default="")
    args = parser.parse_args()

    path = Path(args.path)
    mime = MIME.get(path.suffix.lower(), "application/octet-stream")
    trace = {}
    reply = explain_report(path.read_bytes(), mime, caption=args.caption,
                           user_id="report_demo", trace=trace)

    print("\n===== 1. WHAT CLAUDE READ  +  2. STATUS PYTHON COMPUTED =====\n")
    for r in trace.get("rows", []):
        print(f"  {r['name'][:26]:<26} {r['value']:>10} {r['unit']:<11} "
              f"range {r['reference_range'] or '-':<20} -> {r['status'].upper()}")
    if "guardrail_blocked" in trace:
        print(f"\n===== 3. OUTPUT GUARDRAIL: {'BLOCKED' if trace['guardrail_blocked'] else 'passed'} =====")
    print("\n===== 4. FINAL REPLY (also saved to report_reply.txt) =====\n")
    print(reply)
    Path("report_reply.txt").write_text(reply, encoding="utf-8")


if __name__ == "__main__":
    main()
