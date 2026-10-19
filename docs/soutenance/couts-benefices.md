# Analyse coûts-bénéfices

Deux points de vue : la régie de collecte (le client du scénario) et nous (l'équipe projet).
Les chiffres marqués _hyp._ sont des hypothèses à annoncer comme telles devant le jury.

## Pour la régie de collecte

### Coûts

| Poste                       | Estimation                                                  | Commentaire                                                    |
| --------------------------- | ----------------------------------------------------------- | -------------------------------------------------------------- |
| Matériel                    | 0 € si PC existant ≥ 16 Go ; ~900 € un mini-PC 32 Go _hyp._ | Pas de GPU nécessaire avec un modèle 4B                        |
| Électricité                 | ~15 €/an _hyp._                                             | ~65 W pendant ~1 h de génération cumulée par jour, ~0,25 €/kWh |
| Licences                    | 0 €                                                         | Ollama (MIT), Qwen (Apache 2.0), Sensai interne                |
| Installation et maintenance | ~2 jours/an d'un technicien _hyp._                          | Mises à jour du modèle, des documents, sauvegardes             |
| Mise à jour du corpus RAG   | ~1 h/mois _hyp._                                            | Nouveau calendrier, nouvelles consignes                        |
| Formation des agents        | ~1 h par chef d'équipe                                      | Interface web, rien à installer côté agent                     |
| Conformité RGPD             | Mise à jour du registre, AIPD éventuelle                    | Voir [securite-rgpd.md](securite-rgpd.md)                      |

### Bénéfices

| Bénéfice                                      | Estimation                                                                  |
| --------------------------------------------- | --------------------------------------------------------------------------- |
| Rédaction des rapports d'incident             | 15 min → 5 min _hyp._ × 25 rapports/semaine = **~4 h/semaine** gagnées      |
| Recherche dans le règlement / fiches sécurité | 5 min → 30 s × 20 recherches/semaine = ~1,5 h/semaine                       |
| Réponses du service usagers                   | Brouillon de courrier prêt en 30 s, ton homogène                            |
| Qualité des rapports                          | Structure toujours complète (champs demandés par la procédure)              |
| Sécurité des agents                           | Règle de sécurité retrouvée et sourcée, au lieu d'une mémoire approximative |
| Intégration des nouveaux ripeurs              | Questions posées à l'assistant plutôt qu'au chef d'équipe                   |

Ordre de grandeur : ~5 h/semaine × 45 semaines ≈ 225 h/an. Au coût chargé d'un agent de maîtrise
(~30 €/h _hyp._), **~6 700 €/an** pour moins de 1 000 € d'investissement la première année.

### Comparaison avec une API cloud

| Critère                | Sensai local (Ollama)               | API cloud (type Groq, OpenAI)                  |
| ---------------------- | ----------------------------------- | ---------------------------------------------- |
| Coût variable          | ~0 €                                | Par token ; faible à ce volume, mais récurrent |
| Données usagers        | Ne quittent pas le dépôt            | Transfert hors UE probable, sous-traitant RGPD |
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
