# smalltv-stats

Vues de la dernière vidéo et nombre d'abonnés (YouTube, TikTok, Instagram) d'Avinathan,
affichés sur une GeekMagic SmallTV-Ultra sous [smalltv-mod](https://github.com/giovi321/smalltv-mod).

- `fetch_stats.py` : récupère les chiffres et écrit `stats.json`
- `.github/workflows/stats.yml` : exécution automatique toutes les 20 min
- `theme/` : écran de la box (`theme.json`, empaqueté en `.stheme` par `pack.py`)

La box lit `http://raw.githack.com/fowlc78/smalltv-stats/main/stats.json` (HTTP simple : l'ESP8266 n'a pas assez de mémoire pour HTTPS).
Relais de secours testé : `http://api.allorigins.win/raw?url=https://raw.githubusercontent.com/fowlc78/smalltv-stats/main/stats.json`.
Les jetons TikTok/Instagram sont stockés chiffrés dans `tokens.enc` (clé dans le secret `TOKENS_KEY`).

## reTerminal E1002 (e-paper couleur 7,3")

Le dossier `e1002/` contient la configuration [ESPHome](https://esphome.io) du reTerminal E1002. Elle affiche
deux pages, et n'importe quel bouton passe de l'une à l'autre :

1. le passage de Confucius du jour, toujours en entier : grand sceau rouge 孔子 à gauche, et un texte qui
   rétrécit (puis une mise en page plus large) quand le passage est long ;
2. les réseaux sociaux.

- `fetch_stats.py` écrit aussi `e1002.json` : les mêmes chiffres que `stats.json`, plus le passage du jour, la date
  et des infos en plus par réseau (j'aime, commentaires, date et nombre de vidéos, évolution des abonnés sur
  7 jours, total). L'historique des abonnés est tenu dans `e1002/history.json`.
- Les chiffres de `e1002.json` ne sont réécrits qu'une fois par jour (au premier relevé du jour), comme la
  citation, pour éviter que l'écran se redessine à chaque variation. Un lancement manuel du workflow
  « Mise à jour des stats » force la mise à jour. `stats.json` (SmallTV) reste mis à jour à chaque relevé.
- `e1002/confucius.json` : le texte intégral des Entretiens, de la Grande Étude et de l'Invariable Milieu
  (traduction de Séraphin Couvreur, 1895, domaine public, lue sur Wikisource), soit 618 passages. Un passage
  entier par jour, dans l'ordre, en boucle. Le fichier est reconstruit par `e1002/build_confucius.py`
  (workflow « Reconstruire les citations de Confucius »).
- `e1002/reterminal-e1002.yaml` : le firmware. Réveil toutes les 12 h (`sleep_minutes`), l'écran n'est
  redessiné que si quelque chose a changé, pour ménager la batterie.

Installation (une seule fois, câble USB-C branché sur l'ordinateur) :

```sh
brew install esphome            # ou : pip install esphome
cd e1002
cp secrets.yaml.example secrets.yaml   # puis y mettre le nom et le mot de passe du Wi-Fi
esphome run reterminal-e1002.yaml
```

Cette installation remplace le firmware d'origine (SenseCraft HMI) de l'appareil.
