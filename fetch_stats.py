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
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "stats.json")
TOKENS = os.path.join(HERE, "tokens.enc")
E1002_OUT = os.path.join(HERE, "e1002.json")
QUOTES = os.path.join(HERE, "e1002", "confucius.json")
HISTORY = os.path.join(HERE, "e1002", "history.json")
# Infos supplémentaires pour le reTerminal E1002 (j'aime, commentaires, date, nombre de vidéos).
# Remplies au passage par les fonctions ci-dessous ; la SmallTV ne les lit pas.
EXTRA = {}


def log(*a):
    print(*a, file=sys.stderr)


# ---------------------------------------------------------------- YouTube
def _yt_page(url):
    r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "en-US"},
                     cookies={"SOCS": "CAI", "CONSENT": "YES+"}, timeout=20)
    r.raise_for_status()
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", r.text, re.S)
    if not m:
        raise RuntimeError(f"ytInitialData introuvable (HTTP {r.status_code})")
    return r.text, json.loads(m.group(1))


def youtube_latest_views(channel_id):
    """Vues du dernier envoi (vidéo OU Short) + abonnés, sans clé API.

    La playlist « UU… » liste tous les envois de la chaîne, le plus récent en premier.
    """
    raw, data = _yt_page(f"https://www.youtube.com/playlist?list=UU{channel_id[2:]}&hl=en&gl=US")
    try:
        views = parse_youtube_views(data)
    except RuntimeError:
        mv = re.search(r'"(?:simpleText|content|text)":"((?:[\d.,\u202f\xa0 ]+[KkMm]?|No) views?)"', raw)
        if not mv:
            raise
        views = _digits(mv.group(1))
    try:
        mn = re.search(r'"([\d,.\u202f\xa0 ]+) videos?"', raw)
        if mn:
            EXTRA["ytn"] = _digits(mn.group(1))
        youtube_feed(channel_id)
    except Exception as e:
        log(f"[yt+] échec : {e}")
    subs = None
    try:
        _, chan = _yt_page(f"https://www.youtube.com/channel/{channel_id}?hl=en&gl=US")
        subs = parse_youtube_subs(chan)
    except Exception as e:
        log(f"[ytf] échec : {e}")
    return views, subs


def youtube_feed(channel_id):
    """Flux public de la chaîne : date et nombre de « j'aime » du dernier envoi."""
    r = requests.get(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}",
                     headers={"User-Agent": UA}, timeout=20)
    r.raise_for_status()
    parse_youtube_feed(r.text)


def parse_youtube_feed(xml):
    entries = re.findall(r"<entry>(.*?)</entry>", xml, re.S)
    best = None
    for e in entries:
        pub = re.search(r"<published>([^<]+)</published>", e)
        if not pub:
            continue
        ts = datetime.fromisoformat(pub.group(1).replace("Z", "+00:00")).timestamp()
        if best is None or ts > best[0]:
            best = (ts, e)
    if not best:
        return
    EXTRA["yta"] = best[0]
    likes = re.search(r'<media:starRating[^>]*\bcount="(\d+)"', best[1])
    if likes:
        EXTRA["ytl"] = int(likes.group(1))


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
    if stats.get("videoCount") is not None:
        EXTRA["ttn"] = stats["videoCount"]
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
        if "playlistVideoRenderer" in node:
            runs = node["playlistVideoRenderer"].get("videoInfo", {}).get("runs", [])
            if runs:
                return _digits(runs[0].get("text", ""))
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
        "https://open.tiktokapis.com/v2/video/list/"
        "?fields=id,create_time,view_count,like_count,comment_count",
        headers={"Authorization": f"Bearer {tk['access_token']}"},
        json={"max_count": 20}, timeout=20)
    vids = r.json().get("data", {}).get("videos", [])
    if not vids:
        raise RuntimeError(f"TikTok: {r.text[:200]}")
    # Les vidéos épinglées peuvent remonter en tête : on prend la plus récente.
    latest = max(vids, key=lambda v: v["create_time"])
    EXTRA["tta"] = latest["create_time"]
    if latest.get("like_count") is not None:
        EXTRA["ttl"] = latest["like_count"]
    if latest.get("comment_count") is not None:
        EXTRA["ttc"] = latest["comment_count"]
    return latest["view_count"]


# -------------------------------------------------------------- Instagram
def instagram_latest_views(tokens):
    ig = tokens.get("instagram")
    if not ig:
        return None
    # Deux types de jetons :
    #  - connexion Instagram (ancienne) : graph.instagram.com/me, jeton de 60 j à prolonger ;
    #  - connexion unifiée (apps Meta récentes) : graph.facebook.com/<id du compte Instagram>,
    #    jeton d'utilisateur système sans expiration (ig["ig_id"] est alors renseigné).
    unified = bool(ig.get("ig_id"))
    base = "https://graph.facebook.com" if unified else "https://graph.instagram.com"
    who = ig["ig_id"] if unified else "me"
    # Jeton longue durée (60 j) : on le prolonge une fois par semaine.
    if not unified and time.time() - ig.get("refreshed_at", 0) > 7 * 86400:
        j = requests.get(f"{base}/refresh_access_token", params={
            "grant_type": "ig_refresh_token", "access_token": ig["token"]}, timeout=20).json()
        if "access_token" in j:
            ig.update(token=j["access_token"], refreshed_at=time.time())
        else:
            log("refresh Instagram:", j)
    media = requests.get(f"{base}/{who}/media", params={
        "fields": "id,timestamp,media_type,media_product_type,like_count,comments_count",
        "limit": 25, "access_token": ig["token"]}, timeout=20).json()
    if "error" in media:
        raise RuntimeError(f"Instagram: {media['error'].get('message')}")
    media = media.get("data", [])
    videos = [m for m in media if m.get("media_type") == "VIDEO"
              or m.get("media_product_type") == "REELS"]
    if not videos:
        raise RuntimeError("Instagram: aucune vidéo")
    latest = max(videos, key=lambda m: m["timestamp"])
    try:
        EXTRA["iga"] = datetime.strptime(latest["timestamp"], "%Y-%m-%dT%H:%M:%S%z").timestamp()
    except (KeyError, ValueError):
        pass
    if latest.get("like_count") is not None:
        EXTRA["igl"] = latest["like_count"]
    if latest.get("comments_count") is not None:
        EXTRA["igc"] = latest["comments_count"]
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
    me = requests.get(f"{base}/{who}", params={"fields": "followers_count,media_count",
                                             "access_token": ig["token"]}, timeout=20).json()
    if me.get("media_count") is not None:
        EXTRA["ign"] = me["media_count"]
    return views, me.get("followers_count")


# ------------------------------------------------- reTerminal E1002
def quote_of_the_day(day):
    """Une citation par jour : la liste tourne en boucle, dans l'ordre du fichier."""
    quotes = json.load(open(QUOTES, encoding="utf-8"))
    return quotes[day.toordinal() % len(quotes)]


def french_spaces(text):
    """Espace insécable avant ; : ? ! » et après « (évite une ponctuation seule en début de ligne)."""
    text = re.sub(r" ([;:?!»])", "\u00a0\\1", text)
    return text.replace("« ", "«\u00a0")


def age_text(ts, now):
    """« aujourd'hui », « hier », « il y a 3 j »… à partir d'une date de publication."""
    days = (now.date() - datetime.fromtimestamp(ts, now.tzinfo).date()).days
    if days <= 0:
        return "aujourd’hui"
    if days == 1:
        return "hier"
    if days < 60:
        return f"il y a {days} j"
    return f"il y a {days // 30} mois"


def signed(n):
    return ("+" if n >= 0 else "-") + fmt(abs(n))


def follower_history(followers, now):
    """Mémorise les abonnés du jour et renvoie ceux d'il y a 7 jours (ou du plus ancien relevé)."""
    try:
        hist = json.load(open(HISTORY))
    except (OSError, ValueError):
        hist = {}
    today = now.date().isoformat()
    day = hist.setdefault(today, {})
    day.update({k: v for k, v in followers.items() if v is not None})
    keep = sorted(hist)[-40:]
    hist = {k: hist[k] for k in keep}
    json.dump(hist, open(HISTORY, "w"), separators=(",", ":"), sort_keys=True)
    week = [k for k in keep if k >= (now.date() - timedelta(days=7)).isoformat() and k < today]
    return hist[week[0]] if week else {}


def write_e1002(stats, now, followers):
    """Fichier lu par le reTerminal E1002 : mêmes chiffres, infos en plus, citation du jour.

    followers : abonnés bruts du relevé courant, par réseau (None si inconnu).
    """
    try:
        old = json.load(open(E1002_OUT, encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    quote = quote_of_the_day(now.date())
    days = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    months = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
              "septembre", "octobre", "novembre", "décembre"]
    date = f"{days[now.weekday()]} {'1er' if now.day == 1 else now.day} {months[now.month - 1]}"
    data = dict(stats, q=french_spaces(quote["q"]), r=quote["r"],
                d=date, h=now.strftime("%H:%M"))
    before = follower_history(followers, now)
    for net in ("yt", "tt", "ig"):
        # j'aime, commentaires, nombre de vidéos : valeur fraîche, sinon la précédente
        for suffix in ("l", "c", "n"):
            key = net + suffix
            data[key] = fmt(EXTRA[key]) if EXTRA.get(key) is not None else old.get(key, "--")
        data[net + "a"] = age_text(EXTRA[net + "a"], now) if EXTRA.get(net + "a") else old.get(net + "a", "")
        cur, prev = followers.get(net), before.get(net)
        data[net + "d"] = signed(cur - prev) if cur is not None and prev is not None else old.get(net + "d", "")
    known = [v for v in followers.values() if v is not None]
    if known:
        data["tot"] = fmt(sum(known))
        both = [k for k, v in followers.items() if v is not None and before.get(k) is not None]
        data["totd"] = signed(sum(followers[k] - before[k] for k in both)) if both else ""
    else:
        data["tot"], data["totd"] = old.get("tot", "--"), old.get("totd", "")
    json.dump(data, open(E1002_OUT, "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))


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

    raw = {}

    def put(key, fn, *args):
        """Exécute fn ; en cas d'échec on garde la valeur précédente."""
        try:
            val = fn(*args)
            if val is not None:
                raw[key] = val
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
    now = datetime.now(ZoneInfo("Europe/Paris"))
    out["t"] = now.strftime("%d/%m %H:%M")
    json.dump(out, open(OUT, "w"), separators=(",", ":"))
    try:
        write_e1002(out, now, {"yt": raw.get("ytf"), "tt": raw.get("ttf"), "ig": raw.get("igf")})
    except Exception as e:
        log(f"[e1002] échec : {e}")
    if tokens and os.environ.get("TOKENS_KEY"):
        save_tokens(tokens)
    log(json.dumps(out))


if __name__ == "__main__":
    main()
