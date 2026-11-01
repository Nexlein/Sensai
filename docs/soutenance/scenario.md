# Scénario : Sensai Collecte

> Fixé depuis le bootstrap du keynote : chaque feature montrée doit servir ce scénario.
> Les noms de personnes et de la régie sont fictifs.

## Contexte

La **Régie de collecte du Val-Brûlé** (régie publique fictive, 38 communes, ~95 000 habitants)
collecte les ordures ménagères, les emballages, les biodéchets et les encombrants. 120 agents,
22 bennes, un dépôt central. La régie traite des données d'usagers (adresses, téléphones,
signalements) et dépend d'un budget public serré.

## Utilisateur cible : Camille Roux, service usagers

Fiche personnage complète, à connaître avant de jouer : [persona.md](persona.md).

- 29 ans, au service usagers de la régie depuis 3 ans. Répond à environ 40 appels et mails par jour
  (« mon bac n'a pas été vidé », « quel jour passe le jaune ? », encombrants, réclamations).
- Poste de travail : PC de la collectivité sous Linux. Fonctionne avec ou sans carte graphique
  (30 s à 1 min par réponse sans, mesuré).
- Pas développeur, à l'aise avec un navigateur → interface **web**. Sait suivre un guide et
  copier-coller des commandes : c'est Camille qui installe Sensai pendant la pièce, avec le README pour
  seule aide (acte 0 de [demo-script.md](demo-script.md)).
- Manipule des données personnelles en permanence (téléphones, adresses mail) : la DSI a interdit
  ChatGPT. C'est ce qui justifie un modèle local **et** les guardrails PII.

**Besoins métier** :

1. **Répondre vite et juste** : jour de collecte par commune, motifs de refus, plan hivernal. Les
   réponses sont dans six documents différents.
2. **Rédiger les courriers aux usagers** selon les modèles officiels, avec sa signature, et les ranger.
   Aujourd'hui 10 à 15 minutes par courrier.
3. **Ne jamais exposer les données des usagers**, y compris quand le texte vient d'un formulaire en
   ligne qui peut contenir n'importe quoi.
4. **Ne pas recevoir d'information inventée** : une fausse date de collecte, c'est un usager qui
   rappelle en colère.

## Pourquoi un assistant local

| Contrainte               | Conséquence                                                            |
| ------------------------ | ---------------------------------------------------------------------- |
| Données d'usagers (RGPD) | Rien ne sort du dépôt : Ollama local, pas d'API cloud (Groq désactivé) |
| Budget public            | Pas d'abonnement par token, matériel déjà présent ou un mini-PC        |
| Réseau parfois coupé     | Fonctionne hors ligne (sauf recherche web, optionnelle)                |
| Documents internes       | Règlement, fiches sécurité, plan hivernal → RAG sur `data/collecte/`   |

## Cohérence avec la latence locale

Sur le PC d’Alban, `qwen3.5:4b` atteint 11 tokens/s sur CPU et 37 sur GPU, réflexion
désactivée ([mesures](../benchmarks.md#models-speed-and-memory)). À ce débit, générer
150 tokens demande environ 14 s sur CPU ou 4 s sur GPU, auxquels s’ajoutent le traitement
du prompt et, si nécessaire, le chargement du modèle.

- **Acceptable** : au bureau, pour un courrier ou une question pendant un appel. 30 s à 1 min contre
  5 minutes de recherche ou 15 minutes de rédaction. Mesures réelles dans [demo-script.md](demo-script.md#temps-mesurés-1er-novembre-pc-de-nielsen-sur-secteur).
- **Non acceptable** : un assistant vocal temps réel au téléphone. **Exclu du scope**.
- Le streaming rend l'attente supportable : le premier mot arrive après le temps de traitement du
  prompt, pas après la réponse complète. L'indicateur « thinking… N s » montre que rien n'est figé.

## Features au service du scénario

Présentées (12 étoiles), activées par [`sensai.example.toml`](../../sensai.example.toml) :

| Feature                 | ⭐  | Usage dans le scénario                                                         |
| ----------------------- | --- | ------------------------------------------------------------------------------ |
| X1 Web UI               | 1   | Interface pour un utilisateur non technique                                    |
| A5 Persona              | 1   | « Sensai Collecte » : vocabulaire métier, sources citées, « je ne sais pas »   |
| R1 RAG                  | 2   | Calendrier des secteurs, consignes de tri, plan hivernal, modèles de courriers |
| T4 Fichiers             | 1   | Enregistrer les courriers aux usagers dans `courriers/`                        |
| A3 Confirmation humaine | 1   | Camille valide chaque courrier, aperçu à l'appui, avant qu'il soit écrit       |
| M3 Mémoire structurée   | 2   | Retient la signature de Camille et la réutilise dans les courriers             |
| EV2 Guardrails          | 3   | Mail d'usager : téléphone et email masqués ; injection bloquée                 |
| M1 Sessions             | 1   | Reprendre la journée de la veille (`--session usagers`)                        |

Présentes dans le code mais coupées pour la soutenance (à présenter comme « capacités techniques »
si le jury demande, pas comme besoin de Camille) : M2 compression (`[budget] compress = false`), A1
raisonnement, EV1 juge, EV4 suite adversariale, T2 sandbox, T3 recherche web, T1 MCP, Groq. Voir
[decisions.md](decisions.md).

## Jeu de données

Dossier [`data/collecte/`](../../data/collecte/), au format Markdown (ingéré tel quel par le RAG) :

| Fichier                     | Contenu                                                       | Sert à tester                    |
| --------------------------- | ------------------------------------------------------------- | -------------------------------- |
| `consignes-tri.md`          | Quel déchet dans quel bac, refus de collecte                  | Motifs de refus, encombrants     |
| `calendrier-secteurs.md`    | Secteurs A à D, jours et horaires                             | Faits locaux inconnus du modèle  |
| `securite-collecte.md`      | Règles internes de sécurité (marche arrière, marchepied, EPI) | Réponses sourcées, non inventées |
| `procedure-incidents.md`    | Types d'incidents, délais, contenu d'un rapport               | Rédaction de rapport             |
| `plan-hivernal-herisson.md` | Nom de code « Opération Hérisson »                            | Test du codename (hallucination) |
| `modeles-courriers.md`      | Modèles de courriers aux usagers                              | Génération avec PII masquées     |

Ces documents contiennent volontairement des faits **inventés** (horaires, noms de code, seuils
internes) : un modèle sans RAG ne peut pas les connaître, ce qui rend la mesure A/B nette.

## Pré-prompt proposé

Livré dans `personas/collecte.md`. Pour l'activer :

```toml
[persona]
enabled = true
name = "Sensai Collecte"
file = "personas/collecte.md"   # ou instruction = "..." en ligne
```

Le texte est envoyé comme premier message système de chaque appel, avant le guide d'usage des
outils, la note de confidentialité, la mémoire et le contexte RAG. `/persona off` revient au prompt
générique sans redémarrer (le prompt est alors identique à celui sans persona), `/persona on` le
remet, `/config save` garde l'état.

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

Comparaison mesurée : taux de mention d’un fichier `.md` et taux de refus correct, avec et sans ce
pré-prompt (voir [benchmarks.md](benchmarks.md#ab-2--pré-prompt-générique-vs-spécialisé)).

La persona fait passer les réponses mentionnant un fichier `.md` de 3/18 à 15/18, sans
changer l’exactitude. Ce compteur ne vérifie pas que la source citée existe ni qu’elle appuie
la réponse ; il ne faut pas le présenter comme un taux de « citations correctes ».
