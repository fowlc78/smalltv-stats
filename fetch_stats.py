"""Récupère les vues de la dernière vidéo YouTube / TikTok / Instagram
et écrit stats.json (petit fichier lu directement par la SmallTV).

Secrets (variables d'environnement, fournis par GitHub Actions) :
  YT_CHANNEL_ID        identifiant de chaîne YouTube (UC...)
  TOKENS_KEY           clé Fernet qui chiffre tokens.enc (jetons qui se renouvellent)
  TIKTOK_CLIENT_KEY    / TIKTOK_CLIENT_SECRET   (app développeur TikTok)
Les jetons TikTok/Instagram vivent chiffrés dans tokens.enc, car ils changent
à chaque renouvellement (un secret GitHub ne peut pas être réécrit par le workflow).
"""
import json
import os
import re
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "stats.json")
TOKENS = os.path.join(HERE, "tokens.enc")


def log(*a):
    print(*a, file=sys.stderr)


# ---------------------------------------------------------------- YouTube
def youtube_latest_views(channel_id):
    """Lit la page « Vidéos » de la chaîne (pas de clé API nécessaire)."""
    url = f"https://www.youtube.com/channel/{channel_id}/videos?hl=en&gl=US"
    r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "en-US"},
                     cookies={"SOCS": "CAI", "CONSENT": "YES+"}, timeout=20)
    r.raise_for_status()
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", r.text, re.S)
    if not m:
        raise RuntimeError("ytInitialData introuvable")
    data = json.loads(m.group(1))
    return parse_youtube_views(data), parse_youtube_subs(data)


def parse_youtube_subs(data):
    for node in _walk(data):
        c = node.get("content") if isinstance(node, dict) else None
        if isinstance(c, str) and re.search(r"subscribers?|abonn", c, re.I):
            return _digits(c)
    return None


# -------------------------------------------------- TikTok (page publique)
def tiktok_followers(username):
    """Le nombre d'abonnés est dans la page publique du profil (pas besoin d'API)."""
    r = requests.get(f"https://www.tiktok.com/@{username}", headers={"User-Agent": UA}, timeout=20)
    m = re.search(r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>', r.text, re.S)
    if not m:
        raise RuntimeError("TikTok: données de profil introuvables")
    stats = (json.loads(m.group(1))["__DEFAULT_SCOPE__"]["webapp.user-detail"]
             ["userInfo"].get("stats", {}))
    return stats.get("followerCount")


def _walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)


def _digits(text):
    """'1,234 views' / '15 views' / '1.2K views' -> int"""
    t = text.replace(" ", " ").replace("\xa0", " ").strip()
    m = re.match(r"([\d.,]+)\s*([KkMm]?)", t)
    if not m:
        if t.lower().startswith("no view"):
            return 0
        return None
    num, suf = m.groups()
    if suf:
        val = float(num.replace(",", "."))
        return int(val * (1000 if suf.lower() == "k" else 1_000_000))
    return int(re.sub(r"[.,]", "", num))


def parse_youtube_views(data):
    # Nouveau format (lockupViewModel) : la 1re métadonnée contenant « view »
    for node in _walk(data):
        if "lockupViewModel" in node:
            parts = [n.get("content") for n in _walk(node["lockupViewModel"])
                     if isinstance(n.get("content"), str)]
            # parts[0] = titre ; ensuite « 15 views », « 15 » ou « No views », puis la date
            for p in parts[1:]:
                if re.fullmatch(r"\s*[\d.,\s \xa0]+[KkMm]?\s*(views?|vues?)?\s*", p, re.I) \
                        or re.match(r"no views", p, re.I):
                    return _digits(p)
        if "videoRenderer" in node or "gridVideoRenderer" in node:
            v = node.get("videoRenderer") or node.get("gridVideoRenderer")
            vc = v.get("viewCountText", {})
            txt = vc.get("simpleText") or "".join(x.get("text", "") for x in vc.get("runs", []))
            if txt:
                return _digits(txt)
    raise RuntimeError("aucune vidéo trouvée")


# ---------------------------------------------------------- jetons chiffrés
def _fernet():
    """TOKENS_KEY = phrase secrète libre choisie par l'utilisateur."""
    import base64
    import hashlib
    from cryptography.fernet import Fernet
    raw = hashlib.sha256(os.environ["TOKENS_KEY"].encode()).digest()
    return Fernet(base64.urlsafe_b64encode(raw))


def load_tokens():
    if not os.environ.get("TOKENS_KEY") or not os.path.exists(TOKENS):
        return {}
    return json.loads(_fernet().decrypt(open(TOKENS, "rb").read()))


def save_tokens(tokens):
    open(TOKENS, "wb").write(_fernet().encrypt(json.dumps(tokens).encode()))


# ----------------------------------------------------------------- TikTok
def tiktok_latest_views(tokens):
    tk = tokens.get("tiktok")
    if not tk:
        return None
    # Le jeton d'accès dure 24 h : on le renouvelle avec le refresh token.
    if time.time() > tk.get("expires_at", 0) - 600:
        r = requests.post("https://open.tiktokapis.com/v2/oauth/token/", data={
            "client_key": os.environ["TIKTOK_CLIENT_KEY"],
            "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
            "grant_type": "refresh_token",
            "refresh_token": tk["refresh_token"],
        }, timeout=20)
        j = r.json()
        if "access_token" not in j:
            raise RuntimeError(f"refresh TikTok: {j}")
        tk.update(access_token=j["access_token"],
                  refresh_token=j.get("refresh_token", tk["refresh_token"]),
                  expires_at=time.time() + int(j.get("expires_in", 86400)))
    r = requests.post(
        "https://open.tiktokapis.com/v2/video/list/?fields=id,create_time,view_count",
        headers={"Authorization": f"Bearer {tk['access_token']}"},
        json={"max_count": 20}, timeout=20)
    vids = r.json().get("data", {}).get("videos", [])
    if not vids:
        raise RuntimeError(f"TikTok: {r.text[:200]}")
    # Les vidéos épinglées peuvent remonter en tête : on prend la plus récente.
    return max(vids, key=lambda v: v["create_time"])["view_count"]


# -------------------------------------------------------------- Instagram
def instagram_latest_views(tokens):
    ig = tokens.get("instagram")
    if not ig:
        return None
    base = "https://graph.instagram.com"
    # Jeton longue durée (60 j) : on le prolonge une fois par semaine.
    if time.time() - ig.get("refreshed_at", 0) > 7 * 86400:
        j = requests.get(f"{base}/refresh_access_token", params={
            "grant_type": "ig_refresh_token", "access_token": ig["token"]}, timeout=20).json()
        if "access_token" in j:
            ig.update(token=j["access_token"], refreshed_at=time.time())
        else:
            log("refresh Instagram:", j)
    media = requests.get(f"{base}/me/media", params={
        "fields": "id,timestamp,media_type,media_product_type",
        "limit": 25, "access_token": ig["token"]}, timeout=20).json().get("data", [])
    videos = [m for m in media if m.get("media_type") == "VIDEO"
              or m.get("media_product_type") == "REELS"]
    if not videos:
        raise RuntimeError("Instagram: aucune vidéo")
    latest = max(videos, key=lambda m: m["timestamp"])
    views = None
    for metric in ("views", "plays"):  # « plays » = ancien nom pour les Reels
        j = requests.get(f"{base}/{latest['id']}/insights", params={
            "metric": metric, "access_token": ig["token"]}, timeout=20).json()
        for d in j.get("data", []):
            if d.get("name") == metric:
                views = d["values"][0]["value"]
        if views is not None:
            break
    if views is None:
        log(f"Instagram insights: {j}")
    me = requests.get(f"{base}/me", params={"fields": "followers_count",
                                             "access_token": ig["token"]}, timeout=20).json()
    return views, me.get("followers_count")


# ------------------------------------------------------------------- main
def fmt(n):
    """Texte court pour l'écran (police ASCII de la box)."""
    if n is None:
        return "--"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M".replace(".0M", "M")
    if n >= 100_000:
        return f"{n//1000}k"
    if n >= 10_000:
        return f"{n/1000:.1f}k".replace(".0k", "k")
    return f"{n:,}".replace(",", " ")


def main():
    old = {}
    if os.path.exists(OUT):
        try:
            old = json.load(open(OUT))
        except ValueError:
            pass
    tokens = load_tokens()
    out = dict(old)

    def put(key, fn, *args):
        """Exécute fn ; en cas d'échec on garde la valeur précédente."""
        try:
            val = fn(*args)
            if val is not None:
                out[key] = fmt(val)
        except Exception as e:
            log(f"[{key}] échec : {e}")
        out.setdefault(key, "--")

    # YouTube : vues + abonnés en une seule requête
    yt = {}
    if os.environ.get("YT_CHANNEL_ID"):
        try:
            yt["v"], yt["f"] = youtube_latest_views(os.environ["YT_CHANNEL_ID"])
        except Exception as e:
            log(f"[yt] échec : {e}")
    put("yt", lambda: yt.get("v"))
    put("ytf", lambda: yt.get("f"))

    # TikTok : abonnés via la page publique, vues via l'API officielle
    put("ttf", tiktok_followers, os.environ.get("TIKTOK_USER", "avinathan"))
    put("tt", tiktok_latest_views, tokens)

    # Instagram : tout passe par l'API officielle
    ig = {}
    try:
        res = instagram_latest_views(tokens)
        if res:
            ig["v"], ig["f"] = res
    except Exception as e:
        log(f"[ig] échec : {e}")
    put("ig", lambda: ig.get("v"))
    put("igf", lambda: ig.get("f"))
    out["t"] = datetime.now(ZoneInfo("Europe/Paris")).strftime("%d/%m %H:%M")
    json.dump(out, open(OUT, "w"), separators=(",", ":"))
    if tokens and os.environ.get("TOKENS_KEY"):
        save_tokens(tokens)
    log(json.dumps(out))


if __name__ == "__main__":
    main()
