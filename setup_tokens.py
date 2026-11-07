"""Enregistre (chiffrés dans tokens.enc) les jetons TikTok / Instagram.

Lancé une seule fois par plateforme via le workflow « Ajouter un jeton ».
Les valeurs arrivent par des secrets GitHub (jamais en clair dans le dépôt) :
  IG_TOKEN_INIT      jeton Instagram généré dans le tableau de bord Meta
  TIKTOK_AUTH_CODE   code renvoyé par TikTok après l'autorisation
"""
import os
import sys
import time
from urllib.parse import unquote

import requests

import fetch_stats as fs

REDIRECT = "https://github.com/fowlc78/smalltv-stats"

tokens = fs.load_tokens()

ig = os.environ.get("IG_TOKEN_INIT", "").strip()
if ig:
    r = requests.get("https://graph.instagram.com/me",
                     params={"fields": "username,followers_count", "access_token": ig}, timeout=20).json()
    if "username" not in r:
        sys.exit(f"Jeton Instagram refusé : {r}")
    tokens["instagram"] = {"token": ig, "refreshed_at": 0}
    print(f"Instagram OK : @{r['username']}, {r.get('followers_count')} abonnés")

code = unquote(os.environ.get("TIKTOK_AUTH_CODE", "").strip())
if code:
    j = requests.post("https://open.tiktokapis.com/v2/oauth/token/", data={
        "client_key": os.environ["TIKTOK_CLIENT_KEY"],
        "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT,
    }, timeout=20).json()
    if "access_token" not in j:
        sys.exit(f"Échange TikTok refusé : { {k: v for k, v in j.items() if 'token' not in k} }")
    tokens["tiktok"] = {"access_token": j["access_token"], "refresh_token": j["refresh_token"],
                        "expires_at": time.time() + int(j.get("expires_in", 86400))}
    print("TikTok OK, scopes :", j.get("scope"))

if not (ig or code):
    sys.exit("Aucun jeton fourni.")
fs.save_tokens(tokens)
