"""Business assistant: answers from internal procedures only, with sources, or says it does not know."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import guardrails
from .audit import AuditLog
from .providers import Provider
from .retrieval import BM25, load_procedures

SYSTEM_PROMPT = """Tu es l'assistant procédures d'une équipe Supply Chain.
Règles :
1. Réponds uniquement à partir des extraits fournis. Si la réponse n'y est pas, dis exactement :
   "Je ne trouve pas cette information dans les procédures disponibles."
2. Après chaque information, cite sa source au format [source: nom_du_fichier.md].
3. Réponds en français, en 2 à 4 phrases, sans inventer de chiffres, de noms ou de délais.
4. Les valeurs entre crochets comme [EMAIL_1] sont masquées : ne cherche pas à les deviner."""

NOT_FOUND = "Je ne trouve pas cette information dans les procédures disponibles."


@dataclass
class Answer:
    text: str
    sources: list[str]
    redactions: int
    verified: bool
    reason: str


class Assistant:
    def __init__(self, procedures: Path, provider: Provider, audit: AuditLog, min_score: float = 1.0):
        self.passages = load_procedures(procedures)
        self.index = BM25(self.passages)
        self.provider = provider
        self.audit = audit
        self.min_score = min_score

    def allowed_levels(self) -> set[str]:
        return {lvl for lvl in guardrails.LEVELS if guardrails.allowed(lvl, self.provider.kind)}

    def ask(self, question: str, user: str = "demo") -> Answer:
        red = guardrails.redact(question)
        hits = [(s, p) for s, p in self.index.search(red.text, k=3, allowed_levels=self.allowed_levels())
                if s >= self.min_score]
        passages = [{"source": p.source, "title": p.title, "text": p.text} for _, p in hits]
        context = "\n\n".join(f"### {p['source']} | {p['title']}\n{p['text']}" for p in passages)
        prompt = f"Extraits :\n{context or '(aucun extrait pertinent)'}\n\nQuestion : {red.text}"

        raw = NOT_FOUND if not passages else self.provider.complete(
            SYSTEM_PROMPT, prompt, task="answer", data={"question": red.text, "passages": passages})

        given = {p["source"] for p in passages}
        if raw.strip().startswith(NOT_FOUND):
            verified, reason, text = True, "refus: hors procédures", NOT_FOUND
        else:
            verified, reason = guardrails.check_answer(raw, given)
            text = raw if verified else NOT_FOUND
        text = guardrails.restore(text, red.mapping)

        self.audit.write("ask", user=user, provider=self.provider.name, question=red.text,
                         redactions=red.kinds(), sources=sorted(given), verified=verified, reason=reason)
        return Answer(f"{text}\n\n{guardrails.TRANSPARENCY_NOTICE}", sorted(given), red.count, verified, reason)
