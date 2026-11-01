# Piscine C : sujet du Jour 04, « Pointeurs et chaînes »

> Sujet fictif, écrit pour la démonstration de Sensai.

## Rendu

- Dépôt : `CPool_Day04`, un fichier par exercice, à la racine du dépôt.
- Date limite : **dimanche à 23 h 42**. La moulinette ramasse le dépôt à cette heure-là ; un commit
  poussé après 23 h 42 n'est pas corrigé.
- La moulinette compile chaque fichier seul avec `gcc -Wall -Wextra -c`. Un fichier qui contient une
  fonction `main` vaut 0 à l'exercice.

## Fonctions autorisées

Une seule fonction de la bibliothèque est autorisée aujourd'hui : **`write`**. `printf`, `strlen`,
`puts` et toutes les autres sont interdites : leur utilisation vaut 0 à l'exercice.

## Exercice 00 : my_strlen

Fichier : `my_strlen.c`. Prototype : `int my_strlen(char const *str);`

Retourne le nombre de caractères de la chaîne `str`, sans compter le `'\0'` final.

## Exercice 01 : my_putstr

Fichier : `my_putstr.c`. Prototype : `int my_putstr(char const *str);`

Affiche la chaîne `str` caractère par caractère avec `write`, puis retourne 0.

## Exercice 02 : my_revstr

Fichier : `my_revstr.c`. Prototype : `char *my_revstr(char *str);`

Inverse la chaîne `str` sur place et la retourne.
