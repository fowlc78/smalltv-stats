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
deux modules, répartis sur trois écrans (n'importe quel bouton passe au suivant) :

1. la page du jour : un passage de Confucius, puis le relevé des réseaux sociaux en tableau (écran par défaut) ;
2. le relevé des réseaux sociaux en grand, lisible de loin ;
3. le passage du jour seul, en grand.

Le design suit l'idée d'une page imprimée : fond blanc, encre noire, filets fins, EB Garamond pour le texte,
Inter pour les chiffres, et le rouge comme seule couleur d'accent.

- `fetch_stats.py` écrit aussi `e1002.json` : les mêmes chiffres que `stats.json`, plus le passage du jour et la date.
- `e1002/confucius.json` : le texte intégral des Entretiens, de la Grande Étude et de l'Invariable Milieu
  (traduction de Séraphin Couvreur, 1895, domaine public, lue sur Wikisource). Un passage par jour, dans l'ordre,
  en boucle ; les passages longs sont répartis sur plusieurs jours. Le fichier est reconstruit par
  `e1002/build_confucius.py` (workflow « Reconstruire les citations de Confucius »).
- `e1002/reterminal-e1002.yaml` : le firmware. Réveil toutes les 30 min (`sleep_minutes`), l'écran n'est
  redessiné que si quelque chose a changé, pour ménager la batterie.

Installation (une seule fois, câble USB-C branché sur l'ordinateur) :

```sh
brew install esphome            # ou : pip install esphome
cd e1002
cp secrets.yaml.example secrets.yaml   # puis y mettre le nom et le mot de passe du Wi-Fi
esphome run reterminal-e1002.yaml
```

Cette installation remplace le firmware d'origine (SenseCraft HMI) de l'appareil.
