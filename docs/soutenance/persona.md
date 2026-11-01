# Fiche personnage : Camille Roux

> La personne que tu incarnes pendant la pièce. Tout est fictif : la régie, les communes, les usagers.
> Camille, joué au masculin par Nielsen. Si tu changes de nom, change-le aussi dans
> [demo-script.md](demo-script.md).

## En une phrase

Camille répond toute la journée aux usagers de la régie de collecte, n'a pas le droit d'utiliser
ChatGPT à cause des données personnelles, et perd des heures à chercher des réponses dans six
documents différents.

## Identité

| Champ            | Valeur                                                                |
| ---------------- | --------------------------------------------------------------------- |
| Nom              | Camille Roux, 29 ans                                                  |
| Poste            | Service usagers de la Régie de collecte du Val-Brûlé, depuis 3 ans    |
| Avant            | Accueil de la mairie de Saint-Ormes                                   |
| Employeur        | Régie publique : 38 communes, 95 000 habitants, 120 agents, 22 bennes |
| Poste de travail | PC de la collectivité sous Linux, réseau parfois coupé                |
| Horaires         | 8 h 30 – 17 h, environ 40 appels et mails par jour                    |
| Signature        | « Camille Roux, service usagers, poste 210 »                          |

## Ce que Camille sait faire (et ne sait pas)

- À l'aise avec un navigateur, les mails, le logiciel de la régie.
- **Pas développeur.** Sait suivre un tutoriel et copier-coller des commandes dans un terminal, comme
  le jour où la DSI lui a fait installer l'imprimante. Ne lit pas de code.
- Se méfie des outils qui « inventent » : une mauvaise date de collecte, c'est un usager qui rappelle
  énervé le lendemain.

## Une journée type

1. **Appels « mon bac n'a pas été vidé »** : la moitié des demandes. Il faut retrouver le secteur, le
   jour de passage, et la raison possible du refus (sac fermé dans le bac jaune, couvercle qui ne ferme
   pas…).
2. **Courriers aux usagers** : refus de collecte, excuses après un oubli, dépôt sauvage. Il faut suivre
   les modèles officiels. Aujourd'hui : 10 à 15 minutes par courrier.
3. **Réclamations du formulaire en ligne** : texte libre écrit par les usagers, parfois n'importe quoi.
4. **Jours de neige** : le plan hivernal change les tournées, et le téléphone sonne sans arrêt.

## Ce qui l'agace (les besoins)

| Problème                                                                                  | Ce que Sensai apporte                                                            | Feature |
| ----------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- | ------- |
| Les infos sont dans 6 documents : calendrier, consignes de tri, plan hivernal, modèles…   | Réponse en une question, **avec le document cité**                               | R1      |
| Un assistant générique invente et parle comme un robot                                    | Un assistant « de la régie » : vocabulaire métier, sources, « je ne trouve pas » | A5      |
| La DSI a interdit ChatGPT : les mails des usagers contiennent téléphones et adresses mail | Tout reste sur le PC, **et** les données sont masquées avant le modèle           | EV2     |
| Le formulaire en ligne reçoit parfois des textes malveillants                             | Les tentatives de manipulation sont bloquées                                     | EV2     |
| Rédiger et ranger les courriers prend du temps                                            | Courrier rédigé selon le modèle, enregistré dans `courriers/`                    | T4      |
| Peur qu'un outil écrive n'importe où sans prévenir                                        | Rien n'est écrit sans son « Oui »                                                | A3      |
| Retaper sa signature et son contexte à chaque fois                                        | Sensai retient les faits qu'on lui donne                                         | M3      |
| Reprendre un dossier commencé la veille                                                   | La conversation revient au redémarrage                                           | M1      |
| Pas développeur, pas envie d'un terminal toute la journée                                 | Une page web                                                                     | X1      |

## Pourquoi un assistant local, dit avec ses mots

- « On n'a pas le droit d'envoyer les données des usagers sur un service américain. »
- « On est une régie publique : pas de budget pour un abonnement par utilisateur. »
- « Le réseau du dépôt coupe souvent ; il faut que ça marche quand même. »
- « Même en une minute sur un vieux PC, c'est rien à côté de 5 minutes à fouiller dans les PDF. »

## Vocabulaire à placer naturellement

Bac jaune (emballages), bac gris (ordures), bac marron (biodéchets), secteur, tournée, refus de
collecte, autocollant orange, encombrants (sur rendez-vous), dépôt sauvage, plan hivernal, poste 210.

## Les faits à connaître par cœur (tirés de `demo/collecte/docs/`)

- La Combe est en **secteur B** : bac jaune le **mercredi**, collecte à partir de 6 h.
- Un sac fermé dans le bac jaune = **refus de collecte**, autocollant orange.
- Encombrants : **sur rendez-vous**, 4 passages par an et par foyer.
- Neige : **Opération Hérisson**, la côte de La Combe n'est pas desservie, les bacs se déposent en bas
  de la rue.

## Questions du jury possibles, réponses dans le personnage

| Question                          | Réponse de Camille                                                                                                                         |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| « Pourquoi pas ChatGPT ? »        | « Interdit par la DSI : les mails des usagers contiennent leurs coordonnées. Ici rien ne sort du PC. »                                     |
| « Et si Sensai se trompe ? »      | « Il cite le document, je vérifie en un clic. S'il ne trouve pas, il le dit. »                                                             |
| « C'est lent, non ? »             | « Ici, quelques secondes. Même sur un vieux PC, c'est 30 secondes à une minute : avant, je cherchais 5 minutes dans le classeur. »         |
| « Il faut une carte graphique ? » | « Non. Sans carte graphique ça marche aussi, en 30 secondes à une minute par réponse : l'équipe l'a mesuré. La régie n'a rien à acheter. » |
| « Qui l'a installé ? »            | « Moi, avec le guide du README. Je n'ai rien compris au code, et je n'en ai pas eu besoin. »                                               |
