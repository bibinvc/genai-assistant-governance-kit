"""First-level AI Act screening of a use case, before any project starts.

This is a teaching and triage aid, not legal advice. It points to the articles to read and
the team to involve (DPO, legal, security). Application dates reflect Regulation (EU)
2024/1689 as amended by the 2026 Digital Omnibus on AI.
"""
from __future__ import annotations

from dataclasses import dataclass, field

DATES = {
    "interdit": "Interdictions applicables depuis le 2 février 2025.",
    "haut_risque_annexe_III": "Obligations haut risque (annexe III) applicables au 2 décembre 2027.",
    "haut_risque_annexe_I": "Obligations haut risque (annexe I, produits réglementés) applicables au 2 août 2028.",
    "transparence": "Obligations de transparence (art. 50) applicables depuis le 2 août 2026.",
}

ANNEX_III_DOMAINS = {
    "rh_recrutement": "Annexe III, point 4 a) : recrutement et sélection",
    "rh_decision": "Annexe III, point 4 b) : promotion, licenciement, attribution des tâches, suivi des performances",
    "infrastructure_critique": "Annexe III, point 2 : composant de sécurité d'une infrastructure critique",
    "credit": "Annexe III, point 5 b) : évaluation de la solvabilité",
    "education": "Annexe III, point 3 : éducation et formation professionnelle",
}


@dataclass
class UseCase:
    name: str
    domain: str = "productivite_interne"
    interacts_with_people: bool = False
    generates_content: bool = False
    emotion_recognition_workplace: bool = False
    social_scoring: bool = False
    safety_component_of_product: bool = False
    personal_data: bool = False


@dataclass
class Screening:
    use_case: str
    level: str
    references: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    date: str = ""


def screen(uc: UseCase) -> Screening:
    if uc.emotion_recognition_workplace:
        return Screening(uc.name, "interdit",
                         ["Art. 5, paragraphe 1, point f) : reconnaissance des émotions sur le lieu de travail"],
                         ["Ne pas lancer le projet. Seules les raisons médicales ou de sécurité font exception."],
                         DATES["interdit"])
    if uc.social_scoring:
        return Screening(uc.name, "interdit", ["Art. 5, paragraphe 1, point c) : notation sociale"],
                         ["Ne pas lancer le projet."], DATES["interdit"])

    refs, actions = [], []
    if uc.safety_component_of_product:
        refs.append("Art. 6, paragraphe 1 et annexe I : composant de sécurité d'un produit réglementé (ex. machines)")
        level, date = "haut_risque", DATES["haut_risque_annexe_I"]
    elif uc.domain in ANNEX_III_DOMAINS:
        refs.append(f"Art. 6, paragraphe 2 et {ANNEX_III_DOMAINS[uc.domain]}")
        level, date = "haut_risque", DATES["haut_risque_annexe_III"]
    elif uc.interacts_with_people or uc.generates_content:
        level, date = "transparence", DATES["transparence"]
    else:
        level, date = "minimal", "Pas d'obligation spécifique ; bonnes pratiques et charte interne."

    if level == "haut_risque":
        actions += ["Système de gestion des risques et documentation technique",
                    "Gouvernance des données et journalisation",
                    "Contrôle humain défini et formé",
                    "Impliquer juridique, DPO et sécurité avant tout pilote"]
    if uc.interacts_with_people:
        refs.append("Art. 50, paragraphe 1 : informer les personnes qu'elles échangent avec une IA")
        actions.append("Afficher clairement que l'assistant est une IA")
    if uc.generates_content:
        refs.append("Art. 50 : transparence sur les contenus générés par IA")
        actions.append("Signaler les contenus générés et garder une validation humaine avant diffusion")
    if uc.personal_data:
        refs.append("RGPD : base légale, minimisation, analyse d'impact (AIPD) si risque élevé")
        actions.append("Masquer les données personnelles avant envoi au modèle et vérifier le contrat du fournisseur")
    return Screening(uc.name, level, refs, actions, date)
