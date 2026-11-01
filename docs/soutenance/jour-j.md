# Jour J : défense du 2 novembre, 11 h

Tout ce qu'on fait avant d'entrer en salle, dans l'ordre, avec les commandes à copier-coller. Sur le
PC d'Alban (Arch Linux, RTX 4060). La démo elle-même est dans [demo-script.md](demo-script.md) :
le texte, l'[antisèche](demo-script.md#antisèche--tout-ce-que-tu-tapes-dans-lordre) et le
[plan de repli](demo-script.md#plan-de-repli). Pour les questions : [index-jury.md](index-jury.md).

| Heure   | Quoi                                                |
| ------- | --------------------------------------------------- |
| Veille  | [Installer et préparer](#la-veille)                 |
| 9 h 00  | [Répétition générale](#9-h-00--répétition-générale) |
| 9 h 30  | [Questions croisées](#9-h-30--questions-croisées)   |
| 9 h 40  | [Ajustements](#9-h-40--ajustements)                 |
| 10 h 10 | [Mise en place](#10-h-10--mise-en-place)            |
| 10 h 40 | [Gel](#10-h-40--gel)                                |
| 10 h 50 | [Préchargement](#10-h-50--préchargement)            |
| 11 h 00 | [Défense](#11-h-00--défense)                        |

## La veille

À faire une seule fois sur le PC d'Alban :

```bash
# ollama-cuda doit avoir la même version que ollama, sinon les modèles plantent au chargement.
sudo pacman -S ollama ollama-cuda uv git
sudo systemctl enable --now ollama
ollama pull qwen3.5:4b
ollama pull bge-m3

# La colonne PROCESSOR doit afficher du GPU, pas « 100% CPU ».
ollama run qwen3.5:4b "Bonjour" --think=false
ollama ps

# Python et les dépendances en cache : un clone jetable suffit
git clone https://github.com/Nexlein/Sensai.git /tmp/sensai-warmup
cd /tmp/sensai-warmup && uv sync && cd -
```

- [ ] **Chargeur branché pour toutes les répétitions.**
- [ ] Démo répétée au moins deux fois, chronomètre en main.
- [ ] `gcc` installé (`gcc --version`) pour le moment optionnel du 5C.
- [ ] Vidéo de secours de chaque moment (OBS), en local et sur une clé.
- [ ] Captures d'écran des réponses attendues dans les slides.

## 9 h 00 : répétition générale

Alban joue tout le script, sans s'arrêter, depuis un dossier vierge. Nielsen joue le jury et note.

```bash
# Dossier vierge : un ancien clone garde la mémoire, la session, l'index et CPool_Day04.
rm -rf ~/demo && mkdir ~/demo && cd ~/demo

# Modèles chargés à l'avance (voir 10 h 10 pour le détail)
curl -s localhost:11434/api/generate -d '{"model":"qwen3.5:4b","prompt":"ok","think":false,"keep_alive":"2h"}' > /dev/null
curl -s localhost:11434/api/embed -d '{"model":"bge-m3","input":"ok","keep_alive":"2h"}' > /dev/null
ollama ps
```

Grille de Nielsen, une ligne par moment :

| Moment               | Cible    | Réel | Hésitation, phrase oubliée | Le modèle s'écarte du script (chemin, pas de `Yes` / `No`, pas de source) | Commande cherchée |
| -------------------- | -------- | ---- | -------------------------- | ------------------------------------------------------------------------- | ----------------- |
| 1. Problématique     | 1 min    |      |                            |                                                                           |                   |
| 2. Découverte        | 30 s     |      |                            |                                                                           |                   |
| 3. Lecture de la doc | 30 s     |      |                            |                                                                           |                   |
| 4. Installation      | 2 min    |      |                            |                                                                           |                   |
| 5. Les features      | 5 min 30 |      |                            |                                                                           |                   |
| 6. En coulisses      | 1 min 30 |      |                            |                                                                           |                   |

Comparer aux [temps mesurés](demo-script.md#temps-mesurés) : environ 1 min 30 d'attente du modèle
sur toute la démo.

## 9 h 30 : questions croisées

5 minutes. Chacun pose 5 questions à l'autre, tirées de [index-jury.md](index-jury.md), et celui
qui répond ouvre le bon fichier. Objectif : moins de 10 secondes pour l'ouvrir.

Pour commencer :

1. Pourquoi cet ordre dans le prompt ?
2. Où bloquez-vous les injections ?
3. Amélioration mesurée ?
4. Pourquoi Qwen ? C'est quoi un MoE ?
5. Pourquoi pas Copilot ?
6. Il peut écrire n'importe où ?
7. Vos limites ?
8. Quelle story pour cette feature ?
9. Pourquoi température 0 ?
10. Qu'avez-vous corrigé depuis la mi-parcours ?

## 9 h 40 : ajustements

- **Texte seulement** : phrases, transitions, placement. Pas de code, pas de config.
- **Rejouer** uniquement les moments qui ont accroché à 9 h 00.
- **Trop long** (au-delà de 11 min) : raccourcir le moment 6.
- **Signaux de repli** à fixer ensemble. Par défaut : « thinking… » au-delà de 60 s, alors `Stop`
  et la vidéo du moment ; le reste dans le [plan de repli](demo-script.md#plan-de-repli).
- **Qui répond à quoi**, à confirmer :

| Alban                                                 | Nielsen                                                                               |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Scénario, user stories, interface, déroulé de la démo | Modèles, paramètres, benchmarks, limites, décisions, RGPD, coûts, code des garde-fous |

Les corrections de texte se notent dans les notes d'Alban : pas de PR ce matin.

## 10 h 10 : mise en place

```bash
# Repartir d'un dossier vierge : la répétition de 9 h y a laissé la mémoire, la session,
# l'index des documents et CPool_Day04.
rm -rf ~/demo && mkdir ~/demo && cd ~/demo

# Modèles chargés pour 2 h (évite 10 à 20 s de chargement devant le jury)
systemctl is-active ollama
curl -s localhost:11434/api/generate -d '{"model":"qwen3.5:4b","prompt":"ok","think":false,"keep_alive":"2h"}' > /dev/null
curl -s localhost:11434/api/embed -d '{"model":"bge-m3","input":"ok","keep_alive":"2h"}' > /dev/null
ollama ps
```

- [ ] **Chargeur branché**, sur une prise testée.
- [ ] `ollama ps` montre `qwen3.5:4b` et `bge-m3`.
- [ ] Rien d'autre de lourd ouvert (IDE, Docker) : les deux modèles prennent 4,6 Go.
- [ ] Terminal ouvert dans `~/demo`, police agrandie ; navigateur avec un seul onglet vide.
- [ ] Antisèche ouverte dans une autre fenêtre.
- [ ] Wi-Fi testé pour `git clone` (sinon voir le [plan de repli](demo-script.md#plan-de-repli)).
- [ ] Vidéo de secours sur la clé.
- [ ] Pour les questions, dans une autre fenêtre : [index-jury.md](index-jury.md) ouvert sur GitHub
      (les liens surlignent la ligne de code), et un clone ouvert dans l'éditeur en secours sans
      réseau : `git clone https://github.com/Nexlein/Sensai.git ~/sensai-code`. Pas `/tmp` : il se
      vide au redémarrage.

## 10 h 40 : gel

Plus aucun push sur `main` : chaque push relance la CI et le miroir Epitech. Plus de changement dans
`sensai.toml` ni dans le script.

## 10 h 50 : préchargement

Relancer les deux mêmes commandes : le compteur de `keep_alive` repart pour 2 h, même si la défense
commence en retard.

```bash
curl -s localhost:11434/api/generate -d '{"model":"qwen3.5:4b","prompt":"ok","think":false,"keep_alive":"2h"}' > /dev/null
curl -s localhost:11434/api/embed -d '{"model":"bge-m3","input":"ok","keep_alive":"2h"}' > /dev/null
ollama ps
```

La colonne `UNTIL` d'`ollama ps` doit indiquer environ 2 heures.

## 11 h 00 : défense

- Alban joue [demo-script.md](demo-script.md), l'antisèche dans l'autre fenêtre.
- Nielsen répond aux questions de son côté, avec [index-jury.md](index-jury.md).
- Si quelque chose casse : le [plan de repli](demo-script.md#plan-de-repli).
