# Erreurs courantes de la piscine

> Fiche fictive, écrite pour la démonstration de Sensai.

## Segmentation fault (segfault)

Le programme lit ou écrit dans une zone de mémoire qui ne lui appartient pas, et le système l'arrête.
Cause la plus fréquente en piscine : la fonction reçoit un pointeur `NULL` et le lit quand même.
Correction : au début de la fonction, si `str` vaut `NULL`, retourner tout de suite.

## implicit declaration of function

`gcc` ne connaît pas la fonction appelée : il manque l'`#include` de son en-tête, par exemple
`#include <unistd.h>` pour `write`.

## undefined reference to `main`

Le fichier a été compilé sans `-c` : `gcc` cherche un programme complet. Pour la moulinette, il faut
compiler avec `gcc -Wall -Wextra -c`.

## La sortie n'affiche rien

Le troisième argument de `write` est la longueur à écrire : avec 0, rien ne s'affiche.
