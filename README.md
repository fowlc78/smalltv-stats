# smalltv-stats

Vues de la dernière vidéo et nombre d'abonnés (YouTube, TikTok, Instagram) d'Avinathan,
affichés sur une GeekMagic SmallTV-Ultra sous [smalltv-mod](https://github.com/giovi321/smalltv-mod).

- `fetch_stats.py` : récupère les chiffres et écrit `stats.json`
- `.github/workflows/stats.yml` : exécution automatique toutes les 20 min
- `theme/` : écran de la box (`theme.json`, empaqueté en `.stheme` par `pack.py`)

La box lit `http://raw.githack.com/fowlc78/smalltv-stats/main/stats.json` (HTTP simple : l'ESP8266 n'a pas assez de mémoire pour HTTPS).
Relais de secours testé : `http://api.allorigins.win/raw?url=https://raw.githubusercontent.com/fowlc78/smalltv-stats/main/stats.json`.
Les jetons TikTok/Instagram sont stockés chiffrés dans `tokens.enc` (clé dans le secret `TOKENS_KEY`).
