# Analyse coûts-bénéfices

Trois points de vue : l'étudiant de la démo, la régie de collecte (le scénario des benchmarks) et
nous (l'équipe projet).
Les chiffres marqués _hyp._ sont des hypothèses à annoncer comme telles devant le jury.

## Pour l'étudiant en Tek 1 (scénario de la démo)

### Coûts

| Poste          | Estimation                                        | Commentaire                                                      |
| -------------- | ------------------------------------------------- | ---------------------------------------------------------------- |
| Matériel       | 0 €                                               | Le PC portable de l'école ; 16 Go de RAM conseillés, GPU inutile |
| Téléchargement | ~4,6 Go, une fois                                 | `qwen3.5:4b` (3,4 Go) et `bge-m3` (1,2 Go)                       |
| Électricité    | ~0,03 € par heure de génération _hyp._            | ~100 W sous charge × 0,25 €/kWh                                  |
| Licences       | 0 €                                               | Ollama (MIT), Qwen 3.5 (Apache 2.0), Sensai                      |
| Mise en place  | 2 min prévues à la démo, modèles déjà téléchargés | Copier la config, changer 4 lignes                               |

### Bénéfices

| Bénéfice                   | Ce qui le montre                                                                  |
| -------------------------- | --------------------------------------------------------------------------------- |
| Réponse tirée de son sujet | Fonctions autorisées et date limite en ~6 s sur GPU (mesuré), fichier source cité |
| Code qu'il sait expliquer  | Une fonction à la fois, à la norme, chaque ligne expliquée : pas de -42           |
| Rien n'est écrit sans lui  | Aperçu complet et `Yes` / `No` avant chaque fichier                               |
| Rien ne sort du PC         | Le message du binôme et son code restent en local, numéro et mail masqués         |
| Marche sans réseau         | Une fois les modèles téléchargés                                                  |

### Comparaison avec les assistants en ligne

| Critère                         | Sensai local                        | GitHub Copilot Student                              | ChatGPT Plus, Claude Pro           |
| ------------------------------- | ----------------------------------- | --------------------------------------------------- | ---------------------------------- |
| Prix                            | 0 €                                 | 0 € pour un étudiant vérifié, avec un quota mensuel | 20 $ par mois chacun               |
| Où vont le code et les messages | Restent sur le PC                   | Envoyés au service                                  | Envoyés au service                 |
| Connaît le sujet du jour        | Oui : RAG, source citée             | Non, sauf à le coller                               | Non, sauf à le coller              |
| Fait à sa place                 | Non : la fiche impose d'expliquer   | Complète le code dans l'éditeur                     | Écrit ce qu'on lui demande         |
| Qualité                         | Modèle 4B : erreurs plus fréquentes | Gros modèles : nettement meilleure                  | Gros modèles : nettement meilleure |
| Hors réseau                     | Oui                                 | Non                                                 | Non                                |

**À dire honnêtement** : Copilot est gratuit pour un étudiant vérifié (plan Copilot Student, avec
200 crédits IA par mois depuis le 1er juin 2026). L'argument n'est donc pas seulement le prix :
c'est le contrôle. Rien ne sort du PC, les réponses viennent du sujet de la piscine, et la fiche
explique au lieu de faire. En échange, un 4B se trompe plus souvent qu'un gros modèle en ligne.

Sources : [plans Copilot](https://docs.github.com/en/copilot/get-started/plans),
[Copilot Student](https://github.com/orgs/community/discussions/189268),
[Claude Pro](https://claude.com/pricing), [ChatGPT Plus](https://help.openai.com/en/articles/6950777-what-is-chatgpt-plus).

## Pour la régie de collecte

### Coûts

| Poste                       | Estimation                                                  | Commentaire                                                    |
| --------------------------- | ----------------------------------------------------------- | -------------------------------------------------------------- |
| Matériel                    | 0 € si PC existant ≥ 16 Go ; ~900 € un mini-PC 32 Go _hyp._ | Pas de GPU nécessaire avec un modèle 4B                        |
| Électricité                 | ~15 €/an _hyp._                                             | ~65 W pendant ~1 h de génération cumulée par jour, ~0,25 €/kWh |
| Licences                    | 0 €                                                         | Ollama (MIT), Qwen (Apache 2.0), Sensai interne                |
| Installation et maintenance | ~2 jours/an d'un technicien _hyp._                          | Mises à jour du modèle, des documents, sauvegardes             |
| Mise à jour du corpus RAG   | ~1 h/mois _hyp._                                            | Nouveau calendrier, nouvelles consignes                        |
| Formation des agents        | ~1 h par agent du service usagers                           | Interface web, rien à installer côté agent                     |
| Conformité RGPD             | Mise à jour du registre, AIPD éventuelle                    | Voir [securite-rgpd.md](securite-rgpd.md)                      |

### Bénéfices

| Bénéfice                              | Estimation                                                              |
| ------------------------------------- | ----------------------------------------------------------------------- |
| Courriers aux usagers                 | 15 min → 3 min _hyp._ × 15 courriers/semaine = **~3 h/semaine** gagnées |
| Recherche pendant les appels          | 3 min → 1 min _hyp._ × 20 recherches/jour = **~3,3 h/semaine**          |
| Moins de rappels d'usagers mécontents | Réponse sourcée ; « je ne trouve pas » plutôt qu'une date inventée      |
| Conformité RGPD                       | Téléphones et emails masqués avant le modèle, rien ne sort du poste     |
| Courriers homogènes                   | Toujours le modèle officiel, la bonne signature                         |
| Intégration d'un nouvel agent         | Questions posées à l'assistant plutôt qu'aux collègues                  |

Ordre de grandeur : ~6 h/semaine × 45 semaines ≈ 270 h/an pour un poste du service usagers. Au coût
chargé d'un agent (~30 €/h _hyp._), **~8 000 €/an** pour moins de 1 000 € d'investissement la première
année.

### Comparaison avec une API cloud

| Critère                | Sensai local (Ollama)               | API cloud (type Groq, OpenAI)                  |
| ---------------------- | ----------------------------------- | ---------------------------------------------- |
| Coût variable          | ~0 €                                | Par token ; faible à ce volume, mais récurrent |
| Données usagers        | Ne quittent pas le poste            | Transfert hors UE probable, sous-traitant RGPD |
| Qualité                | Modèle 4B : erreurs plus fréquentes | Modèles 70B+ : nettement meilleure             |
| Latence                | 10 à 30 s par réponse sur CPU       | 1 à 3 s                                        |
| Fonctionne hors réseau | Oui                                 | Non                                            |

Conclusion à présenter : à ce volume, le cloud ne coûte pas cher en argent, mais coûte en
conformité et en dépendance. Le local gagne pour des données d'usagers ; on perd en qualité et en
latence, ce qui est acceptable au bureau (pas en cabine).

### Risques

| Risque                                                    | Mitigation                                                         |
| --------------------------------------------------------- | ------------------------------------------------------------------ |
| Réponse fausse sur une règle de sécurité                  | Source citée obligatoire, « demande à ton responsable » si absente |
| Confiance excessive des agents                            | Formation : l'assistant aide, ne décide pas                        |
| Rejet par les équipes (« un robot pour nous surveiller ») | Aucune donnée de performance des agents collectée                  |
| Corpus obsolète                                           | Responsable désigné de la mise à jour mensuelle                    |

## Pour nous (l'équipe)

| Coût                                                                | Bénéfice                                                                               |
| ------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| 4 personnes sur la durée du projet (_à chiffrer_ en jours-personne) | Maîtrise d'un pipeline LLM complet sans framework : streaming, outils, RAG, guardrails |
| 0 € d'infrastructure (tout local)                                   | Compétences transférables : Ollama, embeddings, évaluation de LLM, RGPD                |
| Machines lentes : itérations longues sur les tests live             | Compréhension concrète des contraintes mémoire et débit                                |
| Temps passé sur des features hors scénario (MCP, sandbox, Groq)     | Architecture extensible prouvée (protocoles, injection dans `bootstrap`)               |
| Scénario défini tard : features choisies avant le besoin            | Leçon retenue, voir [decisions.md](decisions.md#alternatives--si-cétait-à-refaire)     |
