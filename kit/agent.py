"""Small tool-using agent. The model answers with JSON: either a tool call or a final answer.

Tools are read-only except create_ticket, which only creates a draft that a person must
validate. The loop stops after MAX_STEPS, and any unknown tool or bad JSON ends the run safely.
"""
from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from . import guardrails
from .assistant import Assistant
from .audit import AuditLog
from .providers import Provider

MAX_STEPS = 4

AGENT_PROMPT = """Tu es un agent Supply Chain. Outils disponibles :
- search_procedures {"query": texte} : cherche dans les procédures internes
- stock_level {"reference": "REF-xxxx"} : stock disponible d'une référence
- create_ticket {"title": texte, "team": texte} : crée un BROUILLON de ticket, validé ensuite par une personne
Réponds UNIQUEMENT en JSON, soit {"tool": nom, "args": {...}}, soit {"answer": texte}.
Dans la réponse finale, cite les sources des procédures au format [source: fichier.md]."""


class Tools:
    def __init__(self, assistant: Assistant, stock_csv: Path, tickets: Path):
        self.assistant = assistant
        with stock_csv.open(encoding="utf-8") as f:
            self.stock = {r["reference"]: r for r in csv.DictReader(f)}
        self.tickets = tickets

    def search_procedures(self, query: str) -> tuple[str, list[dict]]:
        hits = self.assistant.index.search(query, k=3, allowed_levels=self.assistant.allowed_levels())
        passages = [{"source": p.source, "title": p.title, "text": p.text} for s, p in hits if s >= 1.0]
        summary = "; ".join(f"{p['source']} ({p['title']})" for p in passages) or "aucun résultat"
        return summary, passages

    def stock_level(self, reference: str) -> str:
        if not re.fullmatch(r"REF-\d{3,}", reference):
            return f"Référence invalide : {reference}"
        row = self.stock.get(reference)
        if not row:
            return f"{reference} : référence inconnue."
        return (f"{reference} ({row['designation']}) : {row['quantite']} en stock à {row['site']}, "
                f"seuil de réappro {row['seuil']}.")

    def create_ticket(self, title: str, team: str) -> str:
        self.tickets.parent.mkdir(parents=True, exist_ok=True)
        n = sum(1 for _ in self.tickets.open(encoding="utf-8")) + 1 if self.tickets.exists() else 1
        tid = f"TCK-{n:04d}"
        with self.tickets.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"id": tid, "title": title, "team": team, "status": "brouillon à valider",
                                "created": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                               ensure_ascii=False) + "\n")
        return f"Brouillon de ticket {tid} créé pour l'équipe {team}, à valider par une personne."


class Agent:
    def __init__(self, provider: Provider, tools: Tools, audit: AuditLog):
        self.provider, self.tools, self.audit = provider, tools, audit

    def run(self, question: str, user: str = "demo") -> dict:
        red = guardrails.redact(question)
        history: list[dict] = []
        for step in range(1, MAX_STEPS + 1):
            transcript = "\n".join(f"Outil {h['tool']} -> {h['result']}" for h in history)
            raw = self.provider.complete(AGENT_PROMPT, f"Question : {red.text}\n{transcript}",
                                         task="agent_step", data={"question": red.text, "history": history})
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                return self._end(user, red, history, "Réponse du modèle illisible, arrêt.", ok=False)
            if "answer" in msg:
                return self._end(user, red, history, str(msg["answer"]), ok=True)
            tool, args = msg.get("tool"), msg.get("args", {})
            if tool == "search_procedures":
                result, passages = self.tools.search_procedures(str(args.get("query", red.text)))
                history.append({"tool": tool, "args": args, "result": result, "passages": passages})
            elif tool == "stock_level":
                history.append({"tool": tool, "args": args, "result": self.tools.stock_level(str(args.get("reference", "")))})
            elif tool == "create_ticket":
                history.append({"tool": tool, "args": args,
                                "result": self.tools.create_ticket(str(args.get("title", ""))[:120], str(args.get("team", "support")))})
            else:
                return self._end(user, red, history, f"Outil non autorisé : {tool}. Arrêt.", ok=False)
        return self._end(user, red, history, "Nombre maximum d'étapes atteint, arrêt.", ok=False)

    def _end(self, user: str, red: guardrails.Redaction, history: list[dict], answer: str, ok: bool) -> dict:
        answer = guardrails.restore(answer, red.mapping)
        self.audit.write("agent", user=user, provider=self.provider.name, question=red.text,
                         tools=[h["tool"] for h in history], ok=ok, redactions=red.kinds())
        return {"answer": f"{answer}\n\n{guardrails.TRANSPARENCY_NOTICE}", "steps": history, "ok": ok}
