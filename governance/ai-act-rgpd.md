# Cadre de gouvernance : AI Act, RGPD et sécurité

Ce document explique les choix du kit. Ce n'est pas un avis juridique.

## AI Act : calendrier utilisé

Règlement (UE) 2024/1689, modifié par l'omnibus numérique sur l'IA adopté en 2026 :

| Obligation | Applicable |
|---|---|
| Pratiques interdites (art. 5) | depuis le 2 février 2025 |
| Transparence (art. 50) : informer qu'on échange avec une IA, signaler les contenus générés | depuis le 2 août 2026 |
| Systèmes à haut risque de l'annexe III (RH, crédit, éducation, infrastructures critiques) | 2 décembre 2027 |
| Systèmes à haut risque de l'annexe I (composants de sécurité de produits réglementés, ex. machines) | 2 août 2028 |

`kit/ai_act.py` classe un cas d'usage en interdit, haut risque, transparence ou minimal et liste
les articles à lire et les actions. Les ateliers contribuent aussi à la maîtrise de l'IA
(AI literacy, art. 4) des équipes.

## RGPD

- **Minimisation** : les données personnelles sont masquées avant tout envoi au modèle
  (`kit/guardrails.py`) ; la table de correspondance reste en local.
- **Journalisation** : le journal d'audit ne contient que des valeurs masquées.
- **AIPD** : à prévoir si un cas d'usage traite des données personnelles à grande échelle ou
  porte sur des salariés.

## Sécurité et confidentialité

| Niveau | Fournisseur externe | Modèle local ou mode hors ligne |
|---|---|---|
| C1 Public | oui | oui |
| C2 Interne | oui | oui |
| C3 Confidentiel | non | oui |
| C4 Secret | jamais indexé | jamais indexé |

Autres garde-fous : réponse refusée si elle ne cite pas une source réellement fournie, agent limité
à 4 étapes et à une liste d'outils, ticket créé seulement en brouillon, aucun e-mail envoyé sans
validation humaine, alerte sur les changements de coordonnées bancaires.
