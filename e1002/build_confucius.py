"""Construit confucius.json : le texte intégral des Entretiens de Confucius.

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
PAGE = "Les Quatre livres/Entretiens de Confucius/{:02d}"
UA = "confucius-quotes-builder/1.0 (script GitHub Actions ; lecture ponctuelle)"
OUT = Path(__file__).with_name("confucius.json")
MAX_CHARS = 560  # au-delà, le passage est découpé en plusieurs jours
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII",
         "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX"]
# Caractères que les polices de l'écran savent dessiner (même liste que « glyphs » du YAML)
ALLOWED = set(" !\"%'()+,-./0123456789:;?[]"
              "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
              "«»ÀÂÇÈÉÊËÎÏÔÙÛŒàâçèéêëîïôùûüœ’…–—· ")
REPLACE = {" ": " ", " ": " ", "‘": "’", "“": "« ", "”": " »",
           "æ": "ae", "Æ": "AE", "ʼ": "’", "′": "’", "`": "’", "*": "", "=": "", "_": " "}


def fetch_html(chapter):
    """Wikisource limite le débit : on patiente et on réessaie plusieurs fois."""
    for attempt in range(7):
        r = requests.get(API, headers={"User-Agent": UA}, timeout=30, params={
            "action": "parse", "page": PAGE.format(chapter), "prop": "text",
            "format": "json", "formatversion": 2})
        if r.status_code == 200 and "parse" in r.json():
            return r.json()["parse"]["text"]
        wait = r.headers.get("Retry-After", "")
        wait = min(int(wait), 300) if wait.isdigit() else 20 * (attempt + 1)
        print(f"chapitre {chapter} : HTTP {r.status_code}, nouvel essai dans {wait} s", file=sys.stderr)
        time.sleep(wait)
    raise RuntimeError(f"chapitre {chapter} : HTTP {r.status_code} {r.text[:200]}")


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


def passages(page_html, unknown):
    """Liste [(numéro, texte)] des passages numérotés d'un chapitre."""
    page_html = re.sub(r"<style.*?</style>", "", page_html, flags=re.S)
    page_html = re.sub(r'<div id="headertemplate".*?</div>\s*</div>', "", page_html, flags=re.S)
    page_html = re.sub(r"<sup.*?</sup>", "", page_html, flags=re.S)       # appels de note
    page_html = re.sub(r"<ol class=\"references\".*?</ol>", "", page_html, flags=re.S)
    result = []
    for para in re.findall(r"<p>(.*?)</p>", page_html, flags=re.S):
        text = clean(re.sub(r"<[^>]+>", "", para), unknown)
        if not text:
            continue
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
    sentences = re.findall(r".+?(?:[.!?»](?=\s)|$)\s*", text)
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
    for chapter in range(1, 21):
        items = passages(fetch_html(chapter), unknown)
        if not items:
            raise RuntimeError(f"chapitre {chapter} : aucun passage trouvé")
        print(f"chapitre {chapter:2d} : {len(items)} passages", file=sys.stderr)
        for num, text in items:
            parts = split_parts(text)
            for i, part in enumerate(parts, 1):
                ref = f"Entretiens, {ROMAN[chapter - 1]}.{num}"
                if len(parts) > 1:
                    ref += f" ({i}/{len(parts)})"
                quotes.append({"q": part, "r": ref})
        time.sleep(4)
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
