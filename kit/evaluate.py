"""Runs the question set and reports groundedness, refusals and masking."""
from __future__ import annotations

import json
from pathlib import Path

from .assistant import NOT_FOUND, Assistant


def run(assistant: Assistant, questions: Path) -> tuple[str, list[dict]]:
    rows = []
    for line in questions.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        ans = assistant.ask(item["q"], user="eval")
        refused = ans.text.startswith(NOT_FOUND)
        if item["expect"] == "REFUS":
            ok = refused
        else:
            ok = (not refused) and ans.verified and item["expect"] in ans.text
        pii_ok = ans.redactions >= item.get("pii", 0)
        rows.append({"q": item["q"], "expect": item["expect"], "ok": ok, "pii_expected": item.get("pii", 0),
                     "pii_masked": ans.redactions, "pii_ok": pii_ok, "answer": ans.text.split("\n\n")[0]})

    answerable = [r for r in rows if r["expect"] != "REFUS"]
    refusals = [r for r in rows if r["expect"] == "REFUS"]
    pii = [r for r in rows if r["pii_expected"]]
    md = ["# Evaluation", "",
          f"Provider: `{assistant.provider.name}`. {len(rows)} questions.", "",
          "| Measure | Result |", "|---|---:|",
          f"| Answerable questions answered with the right cited source | {sum(r['ok'] for r in answerable)}/{len(answerable)} |",
          f"| Out-of-scope or secret questions refused | {sum(r['ok'] for r in refusals)}/{len(refusals)} |",
          f"| Questions with personal data or secrets fully masked | {sum(r['pii_ok'] for r in pii)}/{len(pii)} |",
          "", "| Question | Expected | OK | Answer (first part) |", "|---|---|:-:|---|"]
    for r in rows:
        md.append(f"| {r['q']} | {r['expect']} | {'yes' if r['ok'] else 'no'} | {r['answer'][:140].replace('|', '/')} |")
    return "\n".join(md) + "\n", rows
