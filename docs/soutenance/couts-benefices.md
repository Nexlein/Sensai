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
