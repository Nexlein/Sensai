# Sécurité et RGPD

Deux questions du jury : « que se passe-t-il en cas de fuite, quelles contraintes techniques ? » et
« montrez où, dans le code, vous bloquez les injections de prompt et les fuites ».

## Données traitées (scénario Sensai Collecte)

| Donnée                         | Où elle est stockée               | Contient des données perso ?                                                                                                  | Chiffrée ? |
| ------------------------------ | --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- | ---------- |
| Historique des conversations   | `sensai.db` (SQLite, `--session`) | Oui, mais PII structurées **masquées avant stockage**                                                                         | Non        |
| Mémoire structurée (M3)        | `sensai.db`                       | Possible (faits sur l'agent : secteur, équipage)                                                                              | Non        |
| Index RAG                      | `rag.db`                          | Selon les documents indexés (**non filtrés**)                                                                                 | Non        |
| Log des réponses (EV1, opt-in) | `logs/replies.jsonl`              | Texte déjà filtré, mais contexte RAG brut                                                                                     | Non        |
| Config                         | `sensai.toml`                     | Clés d'API en clair (Groq, MCP)                                                                                               | Non        |
| Prompt envoyé au modèle        | Mémoire d’Ollama, local           | Entrée, réponses et résultats d’outils filtrés si les guardrails sont actifs ; contexte RAG et arguments d’outils non filtrés | n/a        |

Tous ces fichiers sont ignorés par Git (`*.db`, `logs/`, `sensai.toml`, `.env`).

## Analyse RGPD

| Principe RGPD                              | Application dans le scénario                                                                                   |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------- |
| Base légale (art. 6)                       | Mission de service public de la régie (art. 6.1.e) pour le traitement des réclamations                         |
| Minimisation (art. 5.1.c)                  | Emails, téléphones, IBAN, cartes, n° de sécu masqués **avant** le modèle et avant l'écriture sur disque        |
| Limitation de la conservation (art. 5.1.e) | ⚠️ Aucune purge automatique. À ajouter : suppression des sessions de plus de N jours                           |
| Sécurité (art. 32)                         | Traitement 100 % local, rien ne sort du poste ; UI web liée à `127.0.0.1` ; confirmation humaine des écritures |
| Sous-traitance et transferts (art. 28, 44) | Ollama local = aucun sous-traitant. **Groq = transfert hors UE** : à désactiver dans ce scénario               |
| Droits des personnes (art. 15-17)          | Effacement : `/clear`, `/memory delete`, `/memory clear`, suppression de `sensai.db`. Pas d'export dédié       |
| Information                                | Les agents doivent savoir que l'assistant conserve l'historique (mention à afficher au démarrage)              |
| Analyse d'impact (AIPD)                    | À envisager : nouvelle technologie + données d'usagers. Le registre de la régie doit mentionner le traitement  |

### Ce que les guardrails ne couvrent pas (à dire honnêtement)

- **Noms et adresses postales** ne sont pas détectés (pas de NER, seulement des regex). Dans le
  scénario, « M. Martin, 4 rue des Lilas » reste en clair dans l'historique.
- **Documents RAG** : leur contenu est injecté sans filtrage PII. Ne pas indexer de fichiers usagers.
- **Arguments d'appels d'outils** écrits par le modèle ne sont pas filtrés.
- Injection : heuristiques regex, contournables par paraphrase (`known_gap` dans le corpus EV4).

## En cas de fuite

Scénario : le PC du dépôt est volé, ou `sensai.db` est copié.

**Ce qui fuit** : historiques (avec noms et adresses en clair, PII structurées masquées), mémoire,
index RAG, clés d'API de `sensai.toml`. **Ce qui ne fuit pas** : les emails, téléphones, IBAN, cartes
et n° de sécu tapés dans le chat (jamais stockés en clair), et rien n'est parti vers un cloud.

**Obligations** :

1. Documenter la violation dans le registre interne (art. 33.5), dans tous les cas.
2. Notifier la CNIL **dans les 72 heures** si risque pour les personnes (art. 33).
3. Informer les usagers concernés si risque élevé (art. 34). Le chiffrement du disque peut en
   dispenser (art. 34.3.a : données incompréhensibles pour un tiers).
4. Révoquer les clés d'API présentes dans `sensai.toml`.

**Contraintes techniques qui en découlent** :

| Mesure                                   | État    | Pourquoi                                                  |
| ---------------------------------------- | ------- | --------------------------------------------------------- |
| Chiffrement du disque (LUKS / BitLocker) | Poste   | SQLite n'est pas chiffré ; c'est la protection principale |
| Pas de clés dans `sensai.toml`           | Conseil | Utiliser les variables d'environnement (`GROQ_API_KEY`)   |
| Purge automatique des sessions           | ❌      | Limiter ce qui fuit                                       |
| Détection des noms / adresses            | ❌      | Les PII les plus fréquentes du scénario                   |
| Authentification de l'UI web             | ❌      | Aujourd'hui protégée seulement par la liaison à localhost |
| Permissions fichier `600` sur les `.db`  | ❌      | Poste partagé entre plusieurs agents                      |

## Où le code se protège

À montrer en direct dans l'éditeur.

### Injections de prompt

| Défense                                                | Emplacement                                                   |
| ------------------------------------------------------ | ------------------------------------------------------------- |
| Règles d'injection (anglais et français)               | `src/sensai/eval/guardrails/injection.py:72` `find_injection` |
| Message bloqué avant le modèle, le RAG et l'historique | `src/sensai/core/engine.py:110`                               |
| Priorité block > redact > flag > allow                 | `src/sensai/eval/guardrails/guardrail.py:22`                  |
| Documents RAG traités comme des données                | `src/sensai/core/prompt.py:62`                                |
| Résultats d'outils traités comme des données           | `src/sensai/core/prompt.py:22`                                |
| Le juge ne se laisse pas dicter sa note                | `src/sensai/eval/judge/judge.py:27`                           |
| Boucle d'outils bornée (pas de boucle infinie)         | `src/sensai/core/engine.py:31` `MAX_TOOL_ROUNDS`              |
| Corpus d'attaques rejoué à chaque CI                   | `src/sensai/eval/adversarial/corpus.py`                       |

### Fuites de données

| Défense                                                                  | Emplacement                                                 |
| ------------------------------------------------------------------------ | ----------------------------------------------------------- |
| PII masquées dans l'entrée (regex + checksums Luhn, IBAN, NIR)           | `src/sensai/eval/guardrails/pii_rules.py`, `checksums.py`   |
| PII masquées dans la réponse en streaming, même coupée entre deux chunks | `src/sensai/eval/guardrails/stream.py:37` `PiiOutputStream` |
| PII masquées dans les résultats d'outils                                 | `src/sensai/core/tool_runner.py:69` `store`                 |
| Clé d'API masquée dans `/config`                                         | `src/sensai/core/commands.py:222`                           |
| UI web liée à localhost                                                  | `src/sensai/interfaces/web/app.py:12`                       |

### Actions dangereuses

| Défense                                                                          | Emplacement                                    |
| -------------------------------------------------------------------------------- | ---------------------------------------------- |
| Chemins confinés à la racine autorisée (`..`, absolus, liens symboliques)        | `src/sensai/tools/base.py:29` `_validate_path` |
| Confirmation humaine des outils sensibles, refus par défaut                      | `src/sensai/core/tool_runner.py:51`            |
| Sandbox Docker : pas de réseau, lecture seule, non-root, mémoire/CPU/PIDs bornés | `src/sensai/tools/sandbox.py:74`               |

## Gestion des erreurs

Remarque du jury : « try/catch c'est mal, il faut des sécurités dans le code ». Notre position :

1. **Valider avant d'agir, plutôt que rattraper après** :
   - config validée par pydantic au chargement (`AppConfig`, `ConfigError` lisible) ;
   - entrée vide refusée avant tout appel (`src/sensai/core/engine.py:105`, `EmptyInputError`) ;
   - chemins validés avant toute lecture (`_validate_path`) ;
   - arguments du sandbox (code vide, timeout invalide) refusés avant de lancer un conteneur.
2. **Erreurs typées, rattrapées à la frontière seulement** : le fournisseur lève `ProviderError`
   (cause chaînée), l'interface l'affiche en une ligne (`src/sensai/interfaces/cli/app.py:103`).
   Pas de `except` qui avale silencieusement au milieu du code.
3. **Les `except Exception` restants sont volontaires et commentés** (`# noqa: BLE001`), aux
   frontières où du code non maîtrisé s'exécute :
   - `core/tool_runner.py` : un outil (ou un serveur MCP tiers) qui plante devient un message
     d'erreur rendu au modèle, qui peut corriger son appel ; la session survit ;
   - `eval/evaluator.py` : une attaque du corpus qui fait planter le guardrail est comptée comme un
     échec du test, pas comme un crash de la suite.
4. **Rien n'est perdu sur erreur** : un tour annulé ou en échec retire le message utilisateur sans
   réponse (`test_cancelling_a_turn_drops_the_unanswered_user_message`).
