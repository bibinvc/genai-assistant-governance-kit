"""Command line: python -m kit.cli <command>

  ask "question"          assistant answer with sources
  agent "question"        tool-using agent
  triage                  process data/emails into the approval queue
  approve EMAIL_ID NAME   approve one draft (goes to out/outbox, never sent)
  screen                  AI Act screening of data/use_cases.json
  eval                    run eval/questions.jsonl and write out/eval.md
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

from .agent import Agent, Tools
from .ai_act import UseCase, screen
from .assistant import Assistant
from .audit import AuditLog
from .evaluate import run as run_eval
from .providers import from_env
from .workflow import EmailWorkflow

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]
    provider = from_env()
    audit = AuditLog(OUT / "audit.jsonl")
    assistant = Assistant(ROOT / "data" / "procedures", provider, audit)

    if cmd == "ask":
        a = assistant.ask(" ".join(args))
        print(a.text)
    elif cmd == "agent":
        tools = Tools(assistant, ROOT / "data" / "stock.csv", OUT / "tickets.jsonl")
        res = Agent(provider, tools, audit).run(" ".join(args))
        for s in res["steps"]:
            print(f"- {s['tool']} {json.dumps(s['args'], ensure_ascii=False)} -> {s['result']}")
        print(res["answer"])
    elif cmd == "triage":
        wf = EmailWorkflow(provider, OUT, audit)
        for p in sorted((ROOT / "data" / "emails").glob("*.txt")):
            item = wf.triage(p)
            print(f"{item['id']}: {item['category']}, masked {item['masked_values']}, status {item['status']}")
            for alert in item["security_alerts"]:
                print(f"  ALERTE: {alert}")
    elif cmd == "approve":
        print(EmailWorkflow(provider, OUT, audit).approve(args[0], args[1]))
    elif cmd == "screen":
        cases = json.loads((ROOT / "data" / "use_cases.json").read_text(encoding="utf-8"))
        results = [asdict(screen(UseCase(**c))) for c in cases]
        (OUT / "ai_act_screening.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        for r in results:
            print(f"{r['level']:<13} {r['use_case']}")
    elif cmd == "eval":
        md, _ = run_eval(assistant, ROOT / "eval" / "questions.jsonl")
        (OUT / "eval.md").write_text(md, encoding="utf-8")
        print(md)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
