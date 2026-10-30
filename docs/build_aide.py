"""Fabrique l'aide de Musicothèque à partir de docs/manuel.md et docs/images/ :

  aide/html/*.html              une page par chapitre (aide de la version tactile, Linux)
  aide/Musicotheque.chm         aide Windows : sommaire, index, recherche (F1 dans le logiciel)
  aide/Musicotheque_Manuel.pdf  manuel à imprimer
  aide/projet_chm/              projet HTML Help Workshop (pour recompiler le .chm sous Windows)

Utilisation :  python docs/build_aide.py
  - .chm : compilé avec chmcmd (Linux : sudo apt install fp-utils) ou hhc.exe (Windows : HTML Help Workshop).
  - .pdf : fabriqué avec Playwright + Chromium s'ils sont installés.
"""
import html
import re
import shutil
import subprocess
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "manuel.md"
IMG = ROOT / "docs" / "images"
OUT = ROOT / "aide"
HTML = OUT / "html"
PROJ = OUT / "projet_chm"
TITLE = "Musicothèque — Aide"

# nom de fichier de chaque chapitre (même nom que dans app/help.py)
FILES = {1: "index.html", 2: "02-installation.html", 3: "03-premiers-pas.html", 4: "04-bibliotheque.html",
         5: "05-ranger.html", 6: "06-identifier.html", 7: "07-son.html", 8: "08-audiogramme.html",
         9: "09-sorties.html", 10: "10-tactile.html", 11: "11-telecommande.html", 12: "12-depannage.html"}

# captures d'écran : chapitre -> [(insérer après ce titre de section, ou None = après l'intro), image, légende]
SHOTS = {
    4: [(None, "fenetre_principale.png", "La fenêtre principale : classement, liste des titres, lecteur et panneau Son.")],
    5: [("Étape par étape", "rangement.png", "L'aperçu du rangement : rien n'est modifié avant « 2. Ranger ».")],
    6: [("Identifier un titre", "identifier.png", "Les propositions trouvées par l'empreinte sonore, avec leur score."),
        ("Modifier les informations", "modifier_infos.png", "Modifier les informations d'un titre."),
        ("Lien YouTube", "youtube_mp3.png", "Convertir un lien YouTube en MP3.")],
    7: [(None, "panneau_son.png", "Le panneau Son : sortie, profil, égaliseur et ambiance.")],
    8: [("Saisir un audiogramme", "audiogramme.png", "Audiogramme : oreille droite en rouge (O), gauche en bleu (X)."),
        ("Faire un test auditif", "test_auditif.png", "Fin du test auditif : Appliquer reporte le résultat.")],
    9: [("Une autre musique", "autres_lecteurs.png", "Le Lecteur 2 joue une autre musique sur le casque Bluetooth.")],
    10: [("Les cinq pages", "tactile_lecture.png", "Page Lecture (écran 800×480)."),
         ("Les cinq pages", "tactile_musique.png", "Page Musique."),
         ("Les cinq pages", "tactile_son.png", "Page Son."),
         ("Les tuiles", "tactile_outils.png", "Page Outils."),
         ("Une autre musique", "tactile_2_lecteurs.png", "Deux lecteurs : chacun sa musique et ses sorties.")],
    11: [("Installer l'application", "telecommande_android.png", "La télécommande sur un téléphone Android."),
         ("Sans application", "tactile_telecommande.png", "Outils ▸ Télécommande : QR code et code d'appairage.")],
}

# mots de l'index : mot -> chapitre(s)
INDEX = {
    "AcoustID (clé)": [3, 6], "Aide (F1)": [12], "Album": [4, 6], "Alsamixer": [12], "Ambiance": [7],
    "Annuler un rangement": [5], "Appairage (télécommande)": [11], "Audiogramme": [8], "Balance": [7],
    "Banana Pi": [2, 10], "Basses (renfort)": [7], "Bibliothèque": [4], "Bluetooth": [9, 10, 12], "CD audio": [6],
    "Clé USB": [5, 10], "Conversion en MP3": [5, 6], "Corbeille": [5], "Doublons": [5], "DRM": [5, 12],
    "Égaliseur": [7], "Écran (taille)": [10, 12], "ffmpeg": [2, 12], "Fichiers (emplacement)": [12],
    "Fichiers protégés (accès refusé)": [5, 6, 12], "Lecture seule": [5, 6, 12], "Fichiers mis de côté": [6, 12], "Dossier tampon (_Fichiers à vérifier)": [6, 12], "Not a Frame instance": [6, 12], "File de lecture": [4], "Identifier un titre": [6],
    "Installation": [2], "Lecteur 2 et 3": [9, 10], "M3U": [4], "Métadonnées": [6], "OGG": [5],
    "Pochette": [6], "Profils audio": [7], "QR code": [11], "Raccourcis clavier": [12], "Ranger et classer": [5],
    "Raspberry Pi": [2, 10], "Recherche": [4, 10], "Retard (alignement)": [9], "Réverbération": [7],
    "Shazam (reconnaissance)": [6], "Sorties audio": [9], "Surround": [7], "Tactile": [10],
    "Télécommande Android": [11], "Test auditif": [8], "Vumètre": [4, 7], "WAV": [5], "WMA": [5, 12], "YouTube": [6],
}

CSS = """
body{font-family:"Segoe UI",Arial,sans-serif;font-size:10.5pt;line-height:1.45;color:#1f2328;margin:18px 26px;max-width:900px}
h1{font-size:20pt;color:#0b5394;border-bottom:3px solid #0b5394;padding-bottom:4px;margin-top:4px}
h2{font-size:13.5pt;color:#0b5394;margin-top:22px;border-bottom:1px solid #d0d7de;padding-bottom:2px}
h3{font-size:11.5pt;color:#24292f;margin-top:16px}
a{color:#0969da}
code{font-family:Consolas,monospace;background:#f3f4f6;padding:0 3px;font-size:9.5pt}
table{border-collapse:collapse;margin:8px 0 12px}
th,td{border:1px solid #d0d7de;padding:5px 8px;vertical-align:top;text-align:left}
th{background:#eef3f8}
blockquote{margin:10px 0;padding:6px 12px;background:#fff8e5;border-left:4px solid #d4a72c}
blockquote p{margin:2px 0}
.fig{margin:10px 0 16px;text-align:center}
.fig img{max-width:100%;border:1px solid #d0d7de}
.fig .cap{font-size:9pt;color:#57606a;margin-top:3px}
.nav{font-size:9pt;color:#57606a;border-top:1px solid #d0d7de;margin-top:26px;padding-top:6px}
.toc li{margin:3px 0}
"""

# l'aide Windows (moteur d'Internet Explorer) n'a pas toujours les émojis : on les retire pour le .chm
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-⛿✀-➿️⏏-⏺⌚⌛⭐]")


def chapters(md):
    md = re.sub(r"^# .*\n+(.*@.*\n+)?", "", md, count=1)      # titre + date/auteur du document partagé
    parts = re.split(r"^## (\d+)\. (.+)$", md, flags=re.M)
    out = []
    for i in range(1, len(parts), 3):
        out.append((int(parts[i]), parts[i + 1].strip(), parts[i + 2].strip()))
    return out


def add_shots(num, body):
    groups = {}
    for after, img, cap in SHOTS.get(num, []):
        groups.setdefault(after, []).append(
            f'<div class="fig screen"><img src="images/{img}" alt="{html.escape(cap)}">'
            f'<div class="cap">{html.escape(cap)}</div></div>')
    for after, figs in groups.items():
        block = "\n\n" + "\n".join(figs) + "\n\n"
        if after is None:
            m = re.search(r"\n\n", body)
        else:
            # après le premier paragraphe (ou la première liste) qui suit le titre de section
            m = re.search(r"^### " + re.escape(after) + r".*\n+(?:(?!###).+\n)*?\n", body + "\n\n", flags=re.M)
            if not m:
                print("  ! section introuvable :", after); continue
        pos = m.end() if m else len(body)
        body = body[:pos] + block + body[pos:]
    return body


def link_chapters(text):
    """« chapitre 5 », « section 5 » deviennent des liens."""
    return re.sub(r"\b(chapitre|section) (\d{1,2})\b",
                  lambda m: f'<a href="{FILES.get(int(m.group(2)), "index.html")}">{m.group(0)}</a>'
                  if int(m.group(2)) in FILES else m.group(0), text)


def page(num, title, body_html, chaps, for_chm):
    i = [c[0] for c in chaps].index(num)
    prev_ = chaps[i - 1] if i > 0 else None
    next_ = chaps[i + 1] if i + 1 < len(chaps) else None
    nav = []
    if prev_: nav.append(f'<a href="{FILES[prev_[0]]}">◀ {prev_[0]}. {html.escape(prev_[1])}</a>')
    nav.append('<a href="index.html">Sommaire</a>')
    if next_: nav.append(f'<a href="{FILES[next_[0]]}">{next_[0]}. {html.escape(next_[1])} ▶</a>')
    toc = ""
    if num == 1:
        toc = "<h2>Sommaire</h2><ol class='toc'>" + "".join(
            f'<li><a href="{FILES[n]}">{html.escape(t)}</a></li>' for n, t, _ in chaps) + "</ol>"
    doc = (f'<!DOCTYPE html>\n<html lang="fr"><head><meta charset="utf-8">'
           f'<meta http-equiv="X-UA-Compatible" content="IE=edge">'
           f'<meta name="viewport" content="width=device-width, initial-scale=1">'
           f'<title>{num}. {html.escape(title)}</title><link rel="stylesheet" href="aide.css"></head><body>'
           f'<h1>{num}. {html.escape(title)}</h1>{body_html}{toc}'
           f'<p class="nav">{" &nbsp;·&nbsp; ".join(nav)}</p></body></html>\n')
    if for_chm:
        doc = EMOJI.sub("", doc)
    return doc


def render(body):
    # sous-listes indentées de 2 ou 3 espaces : Python-Markdown en attend 4
    body = re.sub(r"^ {2,3}(?=[-*] |\d+\. )", "    ", body, flags=re.M)
    h = markdown.markdown(body, extensions=["tables", "sane_lists"])
    return link_chapters(h)


def ent(s):
    """Texte des fichiers de sommaire et d'index (.hhc/.hhk, lus en Windows-1252)."""
    return html.escape(s).encode("cp1252", "xmlcharrefreplace").decode("cp1252")


def build_html(chaps, dest, for_chm):
    if dest.exists():
        shutil.rmtree(dest)
    (dest / "images").mkdir(parents=True)
    for f in IMG.glob("*.png"):
        shutil.copy2(f, dest / "images" / f.name)
    (dest / "aide.css").write_text(CSS, encoding="utf-8")
    for num, title, body in chaps:
        (dest / FILES[num]).write_text(page(num, title, render(add_shots(num, body)), chaps, for_chm), encoding="utf-8")


def build_chm_project(chaps):
    build_html(chaps, PROJ, for_chm=True)
    files = [FILES[n] for n, _, _ in chaps]
    imgs = ["images/" + f.name for f in sorted(IMG.glob("*.png"))]
    (PROJ / "Musicotheque.hhp").write_text(
        "[OPTIONS]\nCompatibility=1.1 or later\nCompiled file=Musicotheque.chm\nContents file=Musicotheque.hhc\n"
        "Default Window=main\nDefault topic=index.html\nDisplay compile progress=No\nFull-text search=Yes\n"
        "Index file=Musicotheque.hhk\nLanguage=0x40c French (France)\nTitle=Musicothèque — Aide\n\n"
        '[WINDOWS]\nmain="Musicothèque — Aide","Musicotheque.hhc","Musicotheque.hhk","index.html","index.html",,,,,'
        "0x63520,240,0x10184e,[60,40,1060,760],,,,,,,0\n\n"
        "[FILES]\n" + "\n".join(files + ["aide.css"] + imgs) + "\n", encoding="cp1252")
    head = ('<!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML//EN">\n<HTML><HEAD><meta name="GENERATOR" content="build_aide.py">'
            '</HEAD><BODY>\n<OBJECT type="text/site properties"><param name="ImageType" value="Folder"></OBJECT>\n<UL>\n')
    toc = head
    for n, t, body in chaps:
        toc += (f'<LI><OBJECT type="text/sitemap"><param name="Name" value="{n}. {ent(t)}">'
                f'<param name="Local" value="{FILES[n]}"></OBJECT>\n')
        subs = re.findall(r"^### (.+)$", body, flags=re.M)
        if subs:
            toc += "<UL>\n"
            for s in subs:
                s = EMOJI.sub("", s).strip()
                toc += (f'<LI><OBJECT type="text/sitemap"><param name="Name" value="{ent(s)}">'
                        f'<param name="Local" value="{FILES[n]}"></OBJECT>\n')
            toc += "</UL>\n"
    (PROJ / "Musicotheque.hhc").write_text(toc + "</UL>\n</BODY></HTML>\n", encoding="cp1252")
    titles = {n: t for n, t, _ in chaps}
    idx = head
    for word in sorted(INDEX, key=lambda w: w.lower().replace("é", "e").replace("É", "E")):
        idx += f'<LI><OBJECT type="text/sitemap"><param name="Name" value="{ent(word)}">'
        for n in INDEX[word]:
            idx += f'<param name="Name" value="{n}. {ent(titles[n])}"><param name="Local" value="{FILES[n]}">'
        idx += "</OBJECT>\n"
    (PROJ / "Musicotheque.hhk").write_text(idx + "</UL>\n</BODY></HTML>\n", encoding="cp1252")
    (PROJ / "compiler_aide.bat").write_text(
        "@echo off\r\nrem Recompile l'aide Windows avec HTML Help Workshop (hhc.exe)\r\ncd /d \"%~dp0\"\r\n"
        "set HHC=\"%ProgramFiles(x86)%\\HTML Help Workshop\\hhc.exe\"\r\n"
        "if not exist %HHC% set HHC=hhc.exe\r\n%HHC% Musicotheque.hhp\r\n"
        "copy /Y Musicotheque.chm ..\\Musicotheque.chm >nul\r\necho Aide creee : aide\\Musicotheque.chm\r\npause\r\n",
        encoding="cp1252")


def compile_chm():
    target = OUT / "Musicotheque.chm"
    for cmd in (["chmcmd", "Musicotheque.hhp"], ["hhc", "Musicotheque.hhp"]):
        if shutil.which(cmd[0]):
            r = subprocess.run(cmd, cwd=PROJ, capture_output=True, text=True, errors="replace")
            out = PROJ / "Musicotheque.chm"
            if out.exists():
                shutil.move(str(out), target)
                print("  aide Windows :", target, f"({target.stat().st_size // 1024} Ko)")
                return True
            print(r.stdout[-800:], r.stderr[-800:])
    print("  .chm non compilé ici : lancez aide\\projet_chm\\compiler_aide.bat sous Windows.")
    return False


def build_pdf(chaps):
    """Manuel complet en un seul document, imprimé en PDF par Chromium."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  PDF ignoré (Playwright absent)"); return False
    parts = []
    for n, t, body in chaps:
        parts.append(f'<section><h1>{n}. {html.escape(t)}</h1>{render(add_shots(n, body))}</section>')
    toc = "".join(f"<li>{html.escape(t)}</li>" for n, t, _ in chaps)
    doc = ('<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><style>' + CSS +
           "body{max-width:none;margin:0} section{page-break-before:always} .fig img{max-height:118mm}"
           ".cover{height:250mm;display:flex;flex-direction:column;justify-content:center;text-align:center}"
           ".cover h1{border:none;font-size:34pt} .cover p{font-size:13pt;color:#57606a}"
           "a{color:inherit;text-decoration:none} h1,h2,h3{page-break-after:avoid} .fig,tr{page-break-inside:avoid}"
           "</style></head><body><div class='cover'><h1>♪ Musicothèque</h1><p>Manuel d'utilisation</p>"
           "<p>Windows · Raspberry Pi tactile · Télécommande Android</p></div>"
           f"<section><h1>Sommaire</h1><ol class='toc'>{toc}</ol></section>" + "".join(parts) + "</body></html>")
    tmp = HTML / "_manuel_complet.html"
    tmp.write_text(doc, encoding="utf-8")
    pdf = OUT / "Musicotheque_Manuel.pdf"
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto(tmp.as_uri()); pg.wait_for_load_state("networkidle")
        pg.pdf(path=str(pdf), format="A4", print_background=True,
               margin={"top": "16mm", "bottom": "16mm", "left": "15mm", "right": "15mm"},
               display_header_footer=True, header_template="<span></span>",
               footer_template='<div style="font-size:8pt;color:#888;width:100%;text-align:center">'
                               'Musicothèque — page <span class="pageNumber"></span> / <span class="totalPages"></span></div>')
        b.close()
    tmp.unlink()
    print("  manuel PDF :", pdf, f"({pdf.stat().st_size // 1024} Ko)")
    return True


def main():
    chaps = chapters(SRC.read_text(encoding="utf-8"))
    assert [c[0] for c in chaps] == list(range(1, 13)), [c[0] for c in chaps]
    OUT.mkdir(exist_ok=True)
    build_html(chaps, HTML, for_chm=False)
    print("  pages HTML :", HTML, f"({len(chaps)} chapitres)")
    build_chm_project(chaps)
    compile_chm()
    if "--sans-pdf" not in sys.argv:
        build_pdf(chaps)


if __name__ == "__main__":
    main()
