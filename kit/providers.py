"""LLM providers behind one small interface.

Every call gets a system prompt and a user prompt (used by real models) plus a task name
and structured data (used by the offline provider, so tests and demos run without a key).

Real providers read their key and model from environment variables; no model name is
hard-coded because model names change often:
  LLM_PROVIDER = offline | gemini | openai | anthropic
  LLM_MODEL    = the model name to use
  GEMINI_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY
  OPENAI_BASE_URL (optional) for OpenAI-compatible APIs such as DeepSeek
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass


class Provider:
    name = "base"
    kind = "external"  # decides which confidentiality levels it may receive

    def complete(self, system: str, user: str, task: str = "", data: dict | None = None) -> str:
        raise NotImplementedError


# ---------------------------------------------------------------- offline

_CATEGORIES = {
    "retard": ["retard", "livraison", "decal", "report", "expedition", "transporteur"],
    "facture": ["facture", "paiement", "iban", "reglement", "avoir", "echeance"],
    "qualite": ["defaut", "non-conform", "non conform", "casse", "qualite", "reclamation", "rebut"],
}


def _norm(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


class OfflineProvider(Provider):
    """Deterministic baseline: extractive answers, keyword routing, template drafts."""
    name = "offline"
    kind = "offline"

    def complete(self, system: str, user: str, task: str = "", data: dict | None = None) -> str:
        data = data or {}
        if task == "answer":
            return self._answer(data["question"], data["passages"])
        if task == "classify_email":
            return self._classify(data["email"])
        if task == "draft_reply":
            return self._draft(data["category"], data["email"])
        if task == "agent_step":
            return self._agent_step(data["question"], data["history"])
        return "Je ne sais pas traiter cette demande."

    def _answer(self, question: str, passages: list[dict]) -> str:
        from .retrieval import tokens
        if not passages:
            return "Je ne trouve pas cette information dans les procédures disponibles."
        q = set(tokens(question))
        # a line must share at least 2 terms with the question (counting its section heading)
        need = 2 if len(q) >= 2 else 1
        best: list[tuple[int, int, str, str]] = []
        for p in passages:
            heading: set[str] = set()
            for line in p["text"].splitlines():
                line = line.strip(" -*").strip()
                if not line:
                    continue
                if line.startswith("#"):
                    heading = set(tokens(line))
                    continue
                own = q & set(tokens(line))
                overlap = len(q & (set(tokens(line)) | heading))
                if overlap >= need:
                    best.append((overlap, len(own), line, p["source"]))
        if not best:
            return "Je ne trouve pas cette information dans les procédures disponibles."
        best.sort(key=lambda x: (-x[0], -x[1]))
        best = [(o, line, src) for o, _, line, src in best]
        picked, seen = [], set()
        for _, line, src in best:
            if line not in seen:
                picked.append((line, src))
                seen.add(line)
            if len(picked) == 2:
                break
        return " ".join(f"{line} [source: {src}]" for line, src in picked)

    def _classify(self, email: str) -> str:
        e = _norm(email)
        scores = {c: sum(e.count(w) for w in words) for c, words in _CATEGORIES.items()}
        cat = max(scores, key=scores.get)
        return cat if scores[cat] > 0 else "autre"

    def _draft(self, category: str, email: str) -> str:
        sender = re.search(r"^De\s*:\s*(.+)$", email, re.M)
        who = sender.group(1).strip() if sender else "Madame, Monsieur"
        body = {
            "retard": "Merci de nous avoir prévenus. Pouvez-vous nous confirmer la nouvelle date de livraison "
                      "et le numéro de suivi ? Nous mettons à jour le planning de réception de notre côté.",
            "facture": "Nous avons bien reçu votre facture. Elle est transmise au service comptabilité "
                       "fournisseurs, qui la rapproche de la commande et du bon de réception avant paiement.",
            "qualite": "Merci pour votre retour. Nous ouvrons une fiche de non-conformité et revenons vers vous "
                       "sous 48 heures avec l'analyse et la suite proposée.",
            "autre": "Merci pour votre message. Nous l'avons transmis à la bonne équipe, qui reviendra vers vous.",
        }[category]
        return f"Bonjour {who},\n\n{body}\n\nCordialement,\nService Achats et Approvisionnement"

    def _agent_step(self, question: str, history: list[dict]) -> str:
        q = _norm(question)
        done = {h["tool"] for h in history}
        ref = re.search(r"\bref-\d{3,}\b", q)
        if ref and "stock_level" not in done and any(w in q for w in ("stock", "dispo", "quantite", "reste")):
            return json.dumps({"tool": "stock_level", "args": {"reference": ref.group(0).upper()}})
        if any(w in q for w in ("ticket", "signaler", "incident", "ouvrir une demande")) and "create_ticket" not in done:
            return json.dumps({"tool": "create_ticket", "args": {"title": question[:80], "team": "supply-chain"}})
        if "search_procedures" not in done and not history:
            return json.dumps({"tool": "search_procedures", "args": {"query": question}})
        parts = []
        for h in history:
            if h["tool"] == "stock_level":
                parts.append(h["result"])
            elif h["tool"] == "create_ticket":
                parts.append(h["result"])
            elif h["tool"] == "search_procedures":
                parts.append(self._answer(question, h.get("passages", [])))
        return json.dumps({"answer": " ".join(parts) or "Je n'ai pas trouvé de réponse."}, ensure_ascii=False)


# ---------------------------------------------------------------- real providers

def _post(url: str, headers: dict, body: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


@dataclass
class GeminiProvider(Provider):
    model: str
    api_key: str
    name = "gemini"

    def complete(self, system: str, user: str, task: str = "", data: dict | None = None) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        out = _post(url, {"x-goog-api-key": self.api_key}, {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0.2},
        })
        return "".join(p.get("text", "") for p in out["candidates"][0]["content"]["parts"])


@dataclass
class OpenAIProvider(Provider):
    model: str
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    name = "openai"

    def complete(self, system: str, user: str, task: str = "", data: dict | None = None) -> str:
        out = _post(f"{self.base_url.rstrip('/')}/chat/completions", {"Authorization": f"Bearer {self.api_key}"}, {
            "model": self.model, "temperature": 0.2,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        })
        return out["choices"][0]["message"]["content"]


@dataclass
class AnthropicProvider(Provider):
    model: str
    api_key: str
    name = "anthropic"

    def complete(self, system: str, user: str, task: str = "", data: dict | None = None) -> str:
        out = _post("https://api.anthropic.com/v1/messages",
                    {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}, {
                        "model": self.model, "max_tokens": 800, "temperature": 0.2,
                        "system": system, "messages": [{"role": "user", "content": user}],
                    })
        return "".join(b.get("text", "") for b in out["content"] if b.get("type") == "text")


class ScriptedProvider(Provider):
    """Returns prepared replies in order. Used in tests to check the agent loop and guardrails."""
    name = "scripted"
    kind = "external"

    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.prompts: list[str] = []

    def complete(self, system: str, user: str, task: str = "", data: dict | None = None) -> str:
        self.prompts.append(user)
        return self.replies.pop(0)


def from_env() -> Provider:
    name = os.environ.get("LLM_PROVIDER", "offline").lower()
    if name == "offline":
        return OfflineProvider()
    model = os.environ.get("LLM_MODEL")
    if not model:
        raise SystemExit("LLM_MODEL must be set for a real provider")
    if name == "gemini":
        return GeminiProvider(model, os.environ["GEMINI_API_KEY"])
    if name == "openai":
        return OpenAIProvider(model, os.environ["OPENAI_API_KEY"],
                              os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    if name == "anthropic":
        return AnthropicProvider(model, os.environ["ANTHROPIC_API_KEY"])
    raise SystemExit(f"unknown LLM_PROVIDER {name}")
