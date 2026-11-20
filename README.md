# GenAI Assistant Governance Kit

Kit pour déployer l'IA générative auprès des équipes métier sans perdre le contrôle des données :
un assistant qui répond sur les procédures internes avec ses sources, un agent avec outils, un
workflow automatisé avec validation humaine, des garde-fous RGPD et sécurité, une grille AI Act,
une version no-code (Gemini Gem, GPT personnalisé, projet Claude, Apps Script) et un kit d'atelier.

**Projet personnel, novembre 2026.** Toutes les données sont fictives : entreprise
« Exemple Industrie », procédures, stocks et e-mails inventés.

## Contenu

| Partie | Fichiers | État |
|---|---|---|
| Assistant procédures (RAG BM25, sources obligatoires, refus hors périmètre) | `kit/assistant.py`, `kit/retrieval.py` | testé en local |
| Agent avec outils : recherche, stock, brouillon de ticket ; 4 étapes max, liste d'outils fermée | `kit/agent.py` | testé en local |
| Workflow e-mails fournisseurs : masquage, classement, brouillon, validation humaine, alerte fraude au RIB | `kit/workflow.py` | testé en local |
| Garde-fous : pseudonymisation (e-mail, téléphone, IBAN, NIR, carte, clés API), niveaux C1 à C4, contrôle des sources | `kit/guardrails.py` | testé en local |
| Grille AI Act par cas d'usage : interdit, haut risque, transparence, minimal | `kit/ai_act.py`, `governance/` | testé en local |
| Journal d'audit sans données personnelles | `kit/audit.py` | testé en local |
| Jeu d'évaluation : sources, refus, masquage | `eval/`, `kit/evaluate.py` | exécuté en mode hors ligne |
| Fournisseurs Gemini, OpenAI (et API compatibles comme DeepSeek), Anthropic | `kit/providers.py` | code prêt, non exécuté sans clé API |
| No-code : instructions pour Gem, GPT, projet Claude, agent Copilot ; Apps Script Sheets + Gemini | `nocode/` | non exécuté ; syntaxe et masquage JS vérifiés |
| Atelier de 2 h : déroulé, fiche prompt, checklist sécurité, guide de maintenance, quiz | `atelier/` | documents |

## Résultats enregistrés (`evidence/`)

Mode hors ligne, Python 3.13, aucune dépendance externe, 19 novembre 2026 :

- **24 tests unitaires réussis** (`evidence/tests.txt`), dont : une source inventée par le modèle est
  bloquée, un fournisseur externe ne reçoit jamais un extrait C3, un outil non autorisé arrête l'agent,
  aucun e-mail ne part sans validation.
- **Évaluation** (`evidence/eval.md`, 17 questions) : 13/13 réponses avec la bonne source citée,
  4/4 questions hors périmètre ou sur un document secret refusées, 2/2 questions contenant des
  données personnelles ou une clé API masquées. Le jeu de questions a été écrit en même temps que le
  mode hors ligne : il vérifie les garde-fous, pas la qualité d'un modèle. Avec un vrai modèle, le
  relancer et ajouter des questions.
- **Workflow** (`evidence/workflow.txt`) : 4 e-mails classés (retard, facture, qualité, autre),
  données masquées, alerte sur l'e-mail qui annonce un nouveau compte bancaire, brouillon restauré
  seulement après validation.
- **AI Act** (`evidence/ai_act_screening.json`) : 6 cas d'usage, dont le tri de CV (haut risque,
  annexe III), l'analyse des émotions au travail (interdit) et la détection d'obstacles sur une
  machine (haut risque, annexe I).

## Lancer

```sh
bash scripts/run_demo.sh                   # tests + toutes les fonctions, sorties dans evidence/
python3 -m kit.cli ask "Qui doit valider une commande urgente ?"
python3 -m kit.cli agent "Quel est le stock de REF-1002 ?"
python3 -m kit.cli triage && python3 -m kit.cli approve email_01 "Nom du relecteur"
python3 -m kit.cli screen
python3 -m kit.cli eval
```

Avec un vrai modèle (non fait par l'auteur, nécessite une clé) :

```sh
export LLM_PROVIDER=gemini LLM_MODEL=<nom du modèle> GEMINI_API_KEY=...
# ou LLM_PROVIDER=openai (+ OPENAI_BASE_URL pour une API compatible), ou LLM_PROVIDER=anthropic
```

Un fournisseur externe ne reçoit que des extraits C1 et C2, déjà masqués.

## Choix de conception

- **Le modèle prépare, la personne décide** : brouillons de tickets et d'e-mails, jamais d'envoi
  automatique.
- **Pas de source, pas de réponse** : une réponse qui ne cite pas un extrait réellement fourni est
  remplacée par un refus.
- **Les données personnelles ne sortent pas** : masquage avant l'appel, restauration en local
  après validation, journal d'audit masqué.
- **Le métier garde la main** : la version no-code et le guide de maintenance permettent à une
  équipe de faire évoluer son assistant sans développeur.

## Limites

- Données fictives, mode hors ligne extractif comme référence ; pas de mesure de qualité d'un vrai
  modèle.
- La détection de données personnelles par expressions régulières ne couvre pas tout (noms propres
  dans le texte libre, adresses postales).
- La grille AI Act est une aide au premier tri, pas un avis juridique.

## English summary

Toolkit for rolling out generative AI to business teams with guardrails: a procedures assistant
that must cite its sources or refuse, a tool-using agent with a closed tool list and step limit, a
supplier email workflow with human approval and a bank-detail fraud alert, GDPR pseudonymisation,
C1-C4 confidentiality levels per provider, an AI Act use-case screening, no-code versions (Gemini
Gem, custom GPT, Claude project, Apps Script) and a 2-hour workshop kit in French. 24 unit tests
pass offline; real LLM providers are wired but were not run without an API key.

MIT, Copyright 2026 Bibin Vellangott Cheruvadi.
