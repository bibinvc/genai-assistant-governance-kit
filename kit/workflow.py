"""Supplier email workflow: mask, classify, draft a reply, then wait for a person to approve.

Nothing is ever sent automatically. Approved drafts go to out/outbox/ as text files, with the
masked values restored only at that point.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import guardrails
from .audit import AuditLog
from .providers import Provider

CLASSIFY_PROMPT = """Classe l'e-mail fournisseur dans une seule catégorie : retard, facture, qualite ou autre.
Réponds par le seul mot de la catégorie."""

DRAFT_PROMPT = """Rédige une réponse courte et polie en français à cet e-mail fournisseur, au nom du
Service Achats et Approvisionnement. Ne promets ni date, ni montant, ni geste commercial.
Garde tels quels les éléments masqués entre crochets."""

CATEGORIES = {"retard", "facture", "qualite", "autre"}

# Bank detail changes announced by email are a classic payment fraud pattern.
_BANK_CHANGE = re.compile(r"(nouveau|nouvel|changement de|modification de)\s+(compte|rib|iban|coordonn[ée]es bancaires)",
                          re.IGNORECASE)


def security_alerts(text: str) -> list[str]:
    alerts = []
    if _BANK_CHANGE.search(text):
        alerts.append("Changement de coordonnées bancaires annoncé par e-mail : vérifier par téléphone auprès "
                      "d'un contact déjà connu avant toute modification (risque de fraude au virement).")
    return alerts


class EmailWorkflow:
    def __init__(self, provider: Provider, out_dir: Path, audit: AuditLog):
        self.provider, self.out, self.audit = provider, out_dir, audit
        (self.out / "approval_queue").mkdir(parents=True, exist_ok=True)
        (self.out / "outbox").mkdir(parents=True, exist_ok=True)

    def triage(self, email_path: Path) -> dict:
        raw = email_path.read_text(encoding="utf-8")
        red = guardrails.redact(raw)
        category = self.provider.complete(CLASSIFY_PROMPT, red.text, task="classify_email",
                                          data={"email": red.text}).strip().lower()
        if category not in CATEGORIES:
            category = "autre"
        draft = self.provider.complete(DRAFT_PROMPT, red.text, task="draft_reply",
                                       data={"category": category, "email": red.text})
        item = {
            "id": email_path.stem,
            "category": category,
            "status": "en_attente",
            "masked_email": red.text,
            "draft": draft,
            "masked_values": red.kinds(),
            "security_alerts": security_alerts(raw),
            "notice": "Brouillon généré par IA, à relire et valider avant envoi.",
        }
        # The mapping stays in a separate local file and is never sent to the provider.
        (self.out / "approval_queue" / f"{item['id']}.json").write_text(
            json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
        (self.out / "approval_queue" / f"{item['id']}.mapping.json").write_text(
            json.dumps(red.mapping, ensure_ascii=False), encoding="utf-8")
        self.audit.write("triage", provider=self.provider.name, email=item["id"], category=category,
                         redactions=red.kinds(), alerts=len(item["security_alerts"]))
        return item

    def approve(self, item_id: str, reviewer: str) -> Path:
        q = self.out / "approval_queue"
        item = json.loads((q / f"{item_id}.json").read_text(encoding="utf-8"))
        mapping = json.loads((q / f"{item_id}.mapping.json").read_text(encoding="utf-8"))
        item["status"] = "approuve"
        item["reviewer"] = reviewer
        (q / f"{item_id}.json").write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
        out = self.out / "outbox" / f"{item_id}.txt"
        out.write_text(guardrails.restore(item["draft"], mapping) + "\n", encoding="utf-8")
        self.audit.write("approve", email=item_id, reviewer=reviewer)
        return out
