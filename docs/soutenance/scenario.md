# Scénario : Sensai Collecte

> Fixé depuis le bootstrap du keynote : chaque feature montrée doit servir ce scénario.
> Les noms de personnes et de la régie sont fictifs.

## Contexte

La **Régie de collecte du Val-Brûlé** (régie publique fictive, 38 communes, ~95 000 habitants)
collecte les ordures ménagères, les emballages, les biodéchets et les encombrants. 120 agents,
22 bennes, un dépôt central. La régie traite des données d'usagers (adresses, téléphones,
signalements) et dépend d'un budget public serré.

## Utilisateurs cibles

### Persona principale : Karim, chef d'équipe collecte

- 44 ans, 18 ans de métier, encadre 3 équipages (chauffeur + 2 ripeurs).
- Prise de poste à 5 h 15 au dépôt, retour vers 12 h 30.
- Poste de travail : un PC partagé au bureau du dépôt, pas de GPU, réseau de la collectivité.
- Pas développeur, à l'aise avec un navigateur, peu avec un terminal → interface **web** pendant la démo.

**Besoins métier** :

1. **Briefing du matin** : retrouver vite la consigne du jour (secteur, plan hivernal, rue en travaux).
2. **Rapports d'incident au retour** : bac non conforme, dépôt sauvage, presqu'accident. Aujourd'hui
   rédigés à la main en 15 à 20 minutes, souvent incomplets.
3. **Réponses aux ripeurs** : « ce bac, on le prend ou pas ? », « la marche arrière dans l'impasse,
   c'est autorisé ? » → réponse sourcée dans le règlement et les fiches sécurité.

### Persona secondaire : Léa, agente du service usagers

- Répond au téléphone et aux mails des usagers (« pourquoi mon bac n'a pas été vidé ? »).
- Manipule des données personnelles en permanence (nom, adresse, téléphone, email) → justifie
  les guardrails PII.

## Pourquoi un assistant local

| Contrainte                    | Conséquence                                                            |
| ----------------------------- | ---------------------------------------------------------------------- |
| Données d'usagers (RGPD)      | Rien ne sort du dépôt : Ollama local, pas d'API cloud (Groq désactivé) |
| Budget public                 | Pas d'abonnement par token, matériel déjà présent ou un mini-PC        |
| Réseau du dépôt parfois coupé | Fonctionne hors ligne (sauf recherche web, optionnelle)                |
| Documents internes            | Règlement, fiches sécurité, plan hivernal → RAG sur `data/collecte/`   |

## Cohérence avec la latence locale

Un modèle 4B quantifié sur CPU produit de l'ordre de 5 à 20 tokens/s (à mesurer, voir
[observabilite.md](observabilite.md#débit-tokenss)). Une réponse de 150 tokens prend donc 10 à 30 s.

- **Acceptable** : au bureau, briefing ou rédaction d'un rapport. 20 s contre 15 minutes de rédaction.
- **Non acceptable** : en cabine pendant la conduite ou en assistant vocal temps réel. **Exclu du
  scope** (et dangereux : l'agent ne doit pas manipuler d'écran en conduisant).
- Le streaming rend l'attente supportable : le premier mot arrive après le temps de traitement du
  prompt, pas après la réponse complète. L'indicateur « thinking… N s » montre que rien n'est figé.

## Features au service du scénario

| Feature                    | Usage dans le scénario                                                           |
| -------------------------- | -------------------------------------------------------------------------------- |
| R1 RAG                     | Règlement de collecte, consignes de tri, fiches sécurité, plan hivernal          |
| EV2 Guardrails PII         | Léa colle un mail d'usager : email et téléphone masqués avant le modèle          |
| EV2 Injection              | Un usager écrit « ignore tes instructions » dans un formulaire de réclamation    |
| T4 Fichiers                | Lire / écrire les rapports d'incident dans `rapports/`                           |
| A3 Confirmation humaine    | Karim valide chaque écriture de rapport avant qu'elle ait lieu                   |
| M3 Mémoire structurée      | Retient « secteur de Karim = B », « équipage 2 = benne 14 »                      |
| M1 Sessions                | Reprendre le rapport commencé la veille (`--session incident-1018`)              |
| M2 Budget de tokens        | Longues journées de questions sans dépasser le contexte                          |
| X1 Web UI                  | Interface pour un utilisateur non technique                                      |
| EV1 Juge / EV4 Adversarial | Prouver que les réponses sont fidèles aux documents et que les attaques échouent |

Hors scénario mais présent dans le code (à présenter comme « capacités techniques », pas comme besoin
de Karim) : sandbox Python (T2), MCP (T1), Groq. Voir [decisions.md](decisions.md).

## Jeu de données

Dossier [`data/collecte/`](../../data/collecte/), au format Markdown (ingéré tel quel par le RAG) :

| Fichier                     | Contenu                                                       | Sert à tester                    |
| --------------------------- | ------------------------------------------------------------- | -------------------------------- |
| `consignes-tri.md`          | Quel déchet dans quel bac, refus de collecte                  | Questions de tri des ripeurs     |
| `calendrier-secteurs.md`    | Secteurs A à D, jours et horaires                             | Faits locaux inconnus du modèle  |
| `securite-collecte.md`      | Règles internes de sécurité (marche arrière, marchepied, EPI) | Réponses sourcées, non inventées |
| `procedure-incidents.md`    | Types d'incidents, délais, contenu d'un rapport               | Rédaction de rapport             |
| `plan-hivernal-herisson.md` | Nom de code « Opération Hérisson »                            | Test du codename (hallucination) |
| `modeles-courriers.md`      | Modèles de courriers aux usagers                              | Génération avec PII masquées     |

Ces documents contiennent volontairement des faits **inventés** (horaires, noms de code, seuils
internes) : un modèle sans RAG ne peut pas les connaître, ce qui rend la mesure A/B nette.

## Pré-prompt proposé

À brancher via `Persona` (`domain/models.py`), aujourd'hui accepté par `build_prompt` mais jamais passé.

```text
Tu es Sensai Collecte, l'assistant des équipes de la Régie de collecte du Val-Brûlé.
Tu aides les chefs d'équipe et les agents du service usagers.

Règles :
- Réponds en français, en phrases courtes, avec le vocabulaire du métier (bac, benne, ripeur, tournée, secteur).
- Pour toute règle de tri, de sécurité, d'horaire ou de procédure, appuie-toi uniquement sur les
  documents fournis et cite le fichier source entre crochets, par exemple [securite-collecte.md].
- Si les documents ne contiennent pas la réponse, dis « Je ne trouve pas cette information dans les
  documents de la régie » et propose qui contacter. N'invente jamais un horaire, une règle ou un nom.
- Une question de sécurité sans réponse dans les documents se termine par : « Demande à ton responsable
  avant d'agir. »
- Les données personnelles des usagers apparaissent masquées ([EMAIL], [PHONE]) : ne cherche pas à les deviner.
- Pour un rapport d'incident, suis la structure de procedure-incidents.md et demande les champs manquants.
```

À mesurer : taux de citation de la source et taux de « je ne sais pas » correct, avec et sans ce
pré-prompt (voir [benchmarks.md](benchmarks.md#ab-2--pré-prompt-générique-vs-spécialisé)).
