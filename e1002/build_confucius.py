"""Construit confucius.json : le texte intégral des écrits attribués à Confucius.

Trois livres : les Entretiens, la Grande Étude et l'Invariable Milieu (ceux que Wikisource
classe sous Confucius ; le quatrième des Quatre livres est de Mencius).
Source : traduction française de Séraphin Couvreur (Les Quatre livres, 1895, domaine public),
lue sur Wikisource. Chaque passage devient une entrée ; les passages trop longs pour l'écran
sont découpés en plusieurs parties (une par jour), de sorte que tout le texte est utilisé.

Usage : python build_confucius.py   (écrit confucius.json à côté de ce fichier)
"""
import html
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests

API = "https://fr.wikisource.org/w/api.php"
BOOK = "Les Quatre livres/"
UA = "confucius-quotes-builder/1.0 (script GitHub Actions ; lecture ponctuelle)"
OUT = Path(__file__).with_name("confucius.json")
MAX_CHARS = 420  # au-delà, le passage est découpé en plusieurs jours
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII",
         "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX"]
# Caractères que les polices de l'écran savent dessiner (même liste que « glyphs » du YAML)
ALLOWED = set(" !\"%'()+,-./0123456789:;?[]§"
              "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
              "«»ÀÂÇÈÉÊËÎÏÔÙÛŒàâçèéêëîïôùûüœ’…–—· ")
REPLACE = {" ": " ", " ": " ", "‘": "’", "“": "« ", "”": " »",
           "æ": "ae", "Æ": "AE", "ʼ": "’", "′": "’", "`": "’", "*": "", "=": "", "_": " "}


def fetch_html(title):
    """Wikisource limite parfois le débit : on patiente et on réessaie."""
    for attempt in range(6):
        r = requests.get(API, headers={"User-Agent": UA}, timeout=30, params={
            "action": "parse", "page": BOOK + title, "prop": "text",
            "format": "json", "formatversion": 2})
        if r.status_code == 200:
            data = r.json()
            if "parse" in data:
                return data["parse"]["text"]
            raise RuntimeError(f"{title} : {data.get('error', data)}")
        wait = r.headers.get("Retry-After", "")
        wait = min(int(wait), 300) if wait.isdigit() else 20 * (attempt + 1)
        print(f"{title} : HTTP {r.status_code}, nouvel essai dans {wait} s", file=sys.stderr)
        time.sleep(wait)
    raise RuntimeError(f"{title} : HTTP {r.status_code} {r.text[:200]}")


def clean(text, unknown):
    text = html.unescape(text)
    out = []
    for ch in text:
        ch = REPLACE.get(ch, ch)
        for c in ch:
            if c in ALLOWED:
                out.append(c)
            elif c in "\n\t\r":
                out.append(" ")
            else:
                base = "".join(x for x in unicodedata.normalize("NFD", c)
                               if not unicodedata.combining(x))
                if base and all(x in ALLOWED for x in base):
                    out.append(base)
                else:
                    unknown[c] = unknown.get(c, 0) + 1
    text = "".join(out)
    text = re.sub(r"[  ]* [  ]*", " ", text)   # une seule insécable
    text = re.sub(r" +", " ", text).strip()
    text = re.sub(r" ([;:?!»])", " \\1", text)
    return text.replace("« ", "« ")


FRENCH = set("le la les des du une dans pour pas il au aux ce sur par elle ses son leur leurs "
             "nous vous je".split())


def paragraphs(page_html, unknown):
    """Paragraphes français d'une page (l'édition mêle aussi chinois transcrit et latin)."""
    page_html = re.sub(r"<style.*?</style>", "", page_html, flags=re.S)
    page_html = re.sub(r'<div id="headertemplate".*?</div>\s*</div>', "", page_html, flags=re.S)
    page_html = re.sub(r"<sup.*?</sup>", "", page_html, flags=re.S)       # appels de note
    page_html = re.sub(r"<ol class=\"references\".*?</ol>", "", page_html, flags=re.S)
    for para in re.findall(r"<p>(.*?)</p>", page_html, flags=re.S):
        raw = html.unescape(re.sub(r"<[^>]+>", "", para))
        if re.search(r"[\u2e80-\u9fff]", raw):        # notice du traducteur citant le chinois
            continue
        words = re.findall(r"[a-zàâçéèêëîïôùûüœ]+", raw.lower())
        if not words or sum(w in FRENCH for w in words) / len(words) < 0.07:
            continue
        text = clean(raw, unknown)
        if text and not text.startswith("Mon maître Tch"):   # avertissement de Tchou Hi
            yield text


def passages(page_html, unknown):
    """Liste [(numéro, texte)] des passages numérotés d'un chapitre."""
    result = []
    for text in paragraphs(page_html, unknown):
        m = re.match(r"(\d+)\.\s*(.+)", text)
        if m and (not result or int(m.group(1)) in (result[-1][0] + 1, result[-1][0] + 2)
                  or int(m.group(1)) == 1):
            result.append([int(m.group(1)), m.group(2)])
        elif result:
            result[-1][1] += " " + text      # suite du même passage (dialogue, commentaire)
    return result


def split_parts(text):
    """Découpe un long passage aux fins de phrase, en parties de taille voisine."""
    if len(text) <= MAX_CHARS:
        return [text]
    # Une phrase finit par . ! ? (avec son guillemet fermant éventuel), jamais avant le « » »
    sentences = re.findall(r".+?(?:[.!?…](?:\u00a0»)?[)]?(?=\s)|$)\s*", text)
    n = -(-len(text) // MAX_CHARS)
    target = len(text) / n
    parts, cur = [], ""
    for s in sentences:
        if cur and len(cur) + len(s) > MAX_CHARS or (len(cur) >= target and len(parts) < n - 1):
            parts.append(cur.strip())
            cur = ""
        cur += s
    if cur.strip():
        parts.append(cur.strip())
    final = []
    for p in parts:                       # phrase unique trop longue : coupe aux virgules/espaces
        while len(p) > MAX_CHARS + 120:
            cut = max(p.rfind(sep, 0, MAX_CHARS) for sep in (", ", " ; ", " "))
            final.append(p[:cut + 1].strip() + " …")
            p = "… " + p[cut + 1:].strip()
        final.append(p)
    return final


def main():
    unknown, quotes = {}, []

    def add(text, ref):
        parts = split_parts(text)
        for i, part in enumerate(parts, 1):
            quotes.append({"q": part, "r": ref + (f" ({i}/{len(parts)})" if len(parts) > 1 else "")})

    for chapter in range(1, 21):
        # Sur Wikisource, la page du chapitre 10 n'a pas de barre oblique dans son titre
        title = "Entretiens de Confucius10" if chapter == 10 else f"Entretiens de Confucius/{chapter:02d}"
        items = passages(fetch_html(title), unknown)
        if not items:
            raise RuntimeError(f"chapitre {chapter} : aucun passage trouvé")
        print(f"Entretiens {chapter:2d} : {len(items)} passages", file=sys.stderr)
        for num, text in items:
            add(text, f"Confucius, Entretiens, {ROMAN[chapter - 1]}.{num}")
        time.sleep(2)

    items = list(paragraphs(fetch_html("La Grande étude"), unknown))
    print(f"Grande Étude : {len(items)} paragraphes", file=sys.stderr)
    for num, text in enumerate(items, 1):
        add(text, f"La Grande Étude, § {num}")
    time.sleep(2)

    items = passages(fetch_html("L’Invariable milieu"), unknown)
    print(f"Invariable Milieu : {len(items)} articles", file=sys.stderr)
    for num, text in items:
        add(text, f"L’Invariable Milieu, {num}")

    if len(quotes) < 400:
        raise RuntimeError(f"seulement {len(quotes)} entrées : source incomplète ?")
    OUT.write_text("[\n" + ",\n".join(" " + json.dumps(q, ensure_ascii=False) for q in quotes)
                   + "\n]\n", encoding="utf-8")
    print(f"{len(quotes)} entrées, la plus longue : {max(len(q['q']) for q in quotes)} caractères",
          file=sys.stderr)
    if unknown:
        print("caractères ignorés :", unknown, file=sys.stderr)


if __name__ == "__main__":
    main()
