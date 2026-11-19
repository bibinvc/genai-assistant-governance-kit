"""Data protection guardrails applied before and after every LLM call.

- Pseudonymisation: personal data and secrets are replaced by placeholders such as
  [EMAIL_1] before text leaves the machine. The mapping stays local, so a human-approved
  draft can be restored with the real values.
- Confidentiality levels: a document label decides which provider may see it.
- Output checks: an answer must cite a source that was really given to the model,
  and every answer carries an AI transparency notice.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

TRANSPARENCY_NOTICE = "Réponse générée par IA à partir des procédures internes. À vérifier avant usage."

# Order matters: the most specific patterns run first.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("SECRET", re.compile(r"\b(?:sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}|ghp_[A-Za-z0-9]{36})\b")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){3,7}(?:[ ]?[A-Z0-9]{1,3})?\b")),
    ("NIR", re.compile(r"\b[12][ ]?\d{2}[ ]?(?:0[1-9]|1[0-2])[ ]?\d{2}[ ]?\d{3}[ ]?\d{3}[ ]?\d{2}\b")),
    ("CARTE", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("TEL", re.compile(r"(?<!\d)(?:\+33[ .]?|0)[1-9](?:[ .-]?\d{2}){4}(?!\d)")),
]


def _luhn_ok(digits: str) -> bool:
    nums = [int(c) for c in digits if c.isdigit()]
    if not 13 <= len(nums) <= 19:
        return False
    total = 0
    for i, n in enumerate(reversed(nums)):
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


@dataclass
class Redaction:
    text: str
    mapping: dict[str, str] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.mapping)

    def kinds(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for key in self.mapping:
            kind = key.strip("[]").rsplit("_", 1)[0]
            out[kind] = out.get(kind, 0) + 1
        return out


def redact(text: str) -> Redaction:
    """Replaces personal data and secrets with numbered placeholders."""
    mapping: dict[str, str] = {}
    reverse: dict[str, str] = {}
    counters: dict[str, int] = {}

    for kind, pattern in _PATTERNS:
        def repl(m: re.Match[str], kind: str = kind) -> str:
            value = m.group(0)
            if kind == "CARTE" and not _luhn_ok(value):
                return value
            if value in reverse:
                return reverse[value]
            counters[kind] = counters.get(kind, 0) + 1
            key = f"[{kind}_{counters[kind]}]"
            mapping[key] = value
            reverse[value] = key
            return key

        text = pattern.sub(repl, text)
    return Redaction(text, mapping)


def restore(text: str, mapping: dict[str, str]) -> str:
    for key, value in mapping.items():
        text = text.replace(key, value)
    return text


# Confidentiality levels used in the front matter of each procedure.
LEVELS = {"C1": "Public", "C2": "Interne", "C3": "Confidentiel", "C4": "Secret"}

# Highest level each provider kind may receive. C4 is never indexed at all.
PROVIDER_MAX_LEVEL = {"offline": "C3", "local": "C3", "external": "C2"}


def allowed(level: str, provider_kind: str) -> bool:
    max_level = PROVIDER_MAX_LEVEL.get(provider_kind, "C1")
    return level != "C4" and int(level[1]) <= int(max_level[1])


_CITATION = re.compile(r"\[source:\s*([\w./-]+)\]")


def cited_sources(answer: str) -> list[str]:
    return _CITATION.findall(answer)


def check_answer(answer: str, given_sources: set[str]) -> tuple[bool, str]:
    """An answer passes if it cites at least one source and only sources it was given."""
    cited = cited_sources(answer)
    if not cited:
        return False, "aucune source citée"
    unknown = [c for c in cited if c not in given_sources]
    if unknown:
        return False, f"source inconnue citée: {', '.join(unknown)}"
    return True, "ok"
