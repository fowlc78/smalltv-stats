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

1. stats des réseaux sociaux + citation du jour (écran par défaut) ;
2. stats des réseaux sociaux en grand ;
3. citation de Confucius du jour en grand.

- `fetch_stats.py` écrit aussi `e1002.json` : les mêmes chiffres que `stats.json`, plus la citation du jour.
- `e1002/confucius.json` : les citations (traductions maison des *Entretiens*, la numérotation des passages
  varie selon les éditions). Une par jour, dans l'ordre, en boucle. On peut en ajouter ou en retirer librement.
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
