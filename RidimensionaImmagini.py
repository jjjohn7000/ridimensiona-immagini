# -*- coding: utf-8 -*-
"""
Ridimensiona Immagini - ridimensionamento in serie di immagini.
Autore: Giovanni Orlando - https://github.com/jjjohn7000/ridimensiona-immagini

Richiede: Python 3.9+ e Pillow.
Opzionali: pillow-heif (foto HEIC/HEIF degli iPhone), tkinterdnd2 (trascinamento dei file).
"""
import hashlib
import io
import json
import math
import os
import queue
import re
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zlib
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageOps, features

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
except Exception:
    HAS_DND = False

try:
    import pymupdf  # compressione dei PDF
except Exception:
    try:
        import fitz as pymupdf
    except Exception:
        pymupdf = None
HAS_PDF = pymupdf is not None

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except Exception:
    pass

APP_NAME = "Ridimensiona Immagini"
APP_VERSION = "0.9.6 beta"
AUTHOR_NAME = "Giovanni Orlando"

# --------------------------------------------------------------------------- aggiornamenti

GITHUB_REPO = "jjjohn7000/ridimensiona-immagini"
GITHUB_URL = "https://github.com/" + GITHUB_REPO
RELEASES_URL = GITHUB_URL + "/releases"
RELEASES_API = "https://api.github.com/repos/%s/releases" % GITHUB_REPO
EXE_ASSET = "RidimensionaImmagini.exe"

# Novità delle versioni, dalla più recente. La sezione della versione corrente viene usata
# anche come descrizione della versione pubblicata su GitHub.
CHANGELOG = """## 0.9.6 beta - 24 novembre 2026
- Controllo degli aggiornamenti più affidabile: se il servizio principale di GitHub non risponde (per esempio perché la rete di un ufficio ha superato il limite di 60 controlli all'ora), il programma usa una seconda strada.
- Se il controllo non riesce, il messaggio spiega il motivo preciso (nessuna connessione, limite di GitHub, antivirus o rete aziendale che bloccano, proxy, tempo scaduto) e propone di aprire la pagina delle versioni.

## 0.9.5 beta - 24 novembre 2026
- Programma molto più leggero: il file scende da circa 114 MB a circa la metà, quindi si scarica e si aggiorna più in fretta.
- Tolte dall'eseguibile parti della libreria PDF che il programma non usava (un motore di intelligenza artificiale per riconoscere tabelle); funzioni e risultati restano identici.
- Ogni nuova versione viene provata automaticamente (immagini, tutti i formati e PDF) prima di essere pubblicata.
- Nella finestra "Informazioni su", al posto dell'indirizzo email, il link per segnalare problemi o suggerimenti sulla pagina del progetto.

## 0.9.4 beta - 24 novembre 2026
- Controllo degli aggiornamenti: all'avvio il programma verifica su GitHub se esiste una versione più recente e, se c'è, ne mostra le novità e permette di installarla con un clic.
- Nel menu "?": "Novità delle versioni", "Controlla aggiornamenti" e l'opzione per attivare o disattivare il controllo all'avvio.

## 0.9.3 beta - 16 novembre 2026
- Nuova scheda "Comprimi PDF": riduce il peso dei PDF che contengono immagini (documenti d'identità, scansioni), lasciando intatti testo e grafica.
- Tipi di documento pronti (a colori, scala di grigi, bianco e nero), risoluzione e qualità regolabili, peso massimo per ogni PDF.
- Rimozione di metadati e miniature; avvisi per i PDF protetti da password o con firma digitale.

## 0.9.2 beta - 10 novembre 2026
- Finestra semplificata: dimensioni in pixel e limiti di peso sono indipendenti e si possono combinare liberamente.
- Peso massimo per ogni immagine e peso massimo totale si possono usare anche insieme.
- Opzione "Se la qualità non basta, consenti di ridurre i pixel" (qualità minima 40).
- Elaborazione circa 3 volte più veloce con i limiti di peso.
- Indicazione del peso complessivo attuale delle immagini scelte.
- La casella Qualità compare solo quando serve; sezioni con barra colorata.
- Corretto l'errore "box can't exceed original image size" con alcune foto ritagliate.

## 0.9.1 beta - 10 novembre 2026
- Peso massimo totale del gruppo di immagini.
- Schede "Ridimensiona per immagine" e "Ridimensiona per cartella", con le sottocartelle.
- Molti più formati: HEIC/HEIF degli iPhone, WebP, AVIF, TIFF, JPEG 2000, PSD e altri.

## 0.9 beta - 10 novembre 2026
- Prima versione: ridimensionamento in serie in pixel o per peso massimo di ogni file.
- Guida completa (tasto F1) e finestra "Informazioni su".
"""


def parse_version(text):
    """'0.9.4 beta' oppure 'v0.9.4-beta' -> (0, 9, 4, 0). Una beta viene prima della versione definitiva."""
    text = text or ""
    nums = [int(x) for x in re.findall(r"\d+", text)[:3]]
    nums += [0] * (3 - len(nums))
    return tuple(nums) + (0 if "beta" in text.lower() else 1,)


def config_path():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "RidimensionaImmagini", "impostazioni.json")


def load_config():
    try:
        with open(config_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_config(cfg):
    try:
        os.makedirs(os.path.dirname(config_path()), exist_ok=True)
        with open(config_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _http_open(url, timeout=10, accept="application/vnd.github+json"):
    req = urllib.request.Request(url, headers={"User-Agent": "RidimensionaImmagini/%s" % APP_VERSION,
                                               "Accept": accept})
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_releases():
    """Versioni pubblicate su GitHub, dalla più recente."""
    with _http_open(RELEASES_API) as r:
        data = json.loads(r.read().decode("utf-8"))
    out = []
    for rel in data:
        if rel.get("draft"):
            continue
        tag = rel.get("tag_name") or ""
        assets = {a.get("name"): a for a in rel.get("assets", [])}
        exe = assets.get(EXE_ASSET, {})
        out.append({
            "version": parse_version(tag),
            "label": tag.lstrip("vV").replace("-", " "),
            "notes": re.split(r"(?m)^---\s*$", rel.get("body") or "")[0].strip(),
            "url": rel.get("html_url") or RELEASES_URL,
            "date": italian_date(rel.get("published_at") or ""),
            "exe": exe.get("browser_download_url"),
            "exe_size": exe.get("size", 0),
            "sha": assets.get(EXE_ASSET + ".sha256", {}).get("browser_download_url"),
        })
    out.sort(key=lambda r: r["version"], reverse=True)
    return out


MESI = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre",
        "ottobre", "novembre", "dicembre")


def italian_date(iso):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", iso or "")
    if not m:
        return ""
    y, mo, d = (int(x) for x in m.groups())
    return "%d %s %d" % (d, MESI[mo - 1], y) if 1 <= mo <= 12 else ""


class NoReleases(Exception):
    """Su GitHub non è ancora pubblicata nessuna versione."""


def fetch_latest_via_web():
    """Seconda strada: legge l'ultima versione dalla normale pagina web di GitHub (senza il limite
    di 60 controlli all'ora del servizio usato di solito). Non fornisce le novità, solo numero e file."""
    with _http_open(RELEASES_URL + "/latest", accept="text/html") as r:
        final = r.geturl()  # GitHub reindirizza a .../releases/tag/<etichetta>
    m = re.search(r"/releases/tag/([^/?#]+)/?$", final)
    if not m:
        raise NoReleases()
    tag = urllib.parse.unquote(m.group(1))
    base = RELEASES_URL + "/download/" + urllib.parse.quote(tag) + "/"
    return [{
        "version": parse_version(tag),
        "label": tag.lstrip("vV").replace("-", " "),
        "notes": "",
        "url": final,
        "date": "",
        "exe": base + EXE_ASSET,
        "exe_size": 0,
        "sha": base + EXE_ASSET + ".sha256",
    }]


def newer_releases():
    """Versioni più recenti di quella in uso. Se il servizio principale di GitHub non risponde
    (limite di controlli, blocco della rete...), prova la seconda strada."""
    try:
        releases = fetch_releases()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise NoReleases()
        first_error = e
        releases = None
    except Exception as e:
        first_error = e
        releases = None
    if releases is None:
        try:
            releases = fetch_latest_via_web()
        except NoReleases:
            raise
        except Exception:
            raise first_error
    if not releases:
        raise NoReleases()
    current = parse_version(APP_VERSION)
    return [r for r in releases if r["version"] > current]


def describe_net_error(e):
    """Spiega in italiano perché il collegamento a GitHub non è riuscito."""
    reason = getattr(e, "reason", None)
    text = str(reason if reason is not None else e)
    if isinstance(e, urllib.error.HTTPError):
        if e.code == 429 or (e.code == 403 and e.headers.get("X-RateLimit-Remaining") == "0"):
            when = ""
            try:
                when = " (dalle %s)" % time.strftime("%H:%M", time.localtime(int(e.headers.get("X-RateLimit-Reset"))))
            except (TypeError, ValueError):
                pass
            return ("GitHub ha raggiunto il numero massimo di controlli consentiti da questa rete senza account "
                    "(60 all'ora per indirizzo Internet; in un ufficio l'indirizzo è condiviso da tutti). "
                    "Riprova più tardi%s." % when)
        if e.code == 407:
            return ("La rete usa un proxy che richiede l'accesso: chiedi all'amministratore di rete di consentire "
                    "il collegamento a github.com e api.github.com.")
        return "GitHub ha risposto con un errore (codice %d)." % e.code
    if isinstance(reason, ssl.SSLCertVerificationError) or isinstance(e, ssl.SSLCertVerificationError) \
            or "CERTIFICATE_VERIFY_FAILED" in text:
        return ("Il certificato di sicurezza di GitHub non è stato accettato. Succede di solito quando un antivirus "
                "o la rete aziendale controllano le connessioni sicure: prova ad aggiungere il programma alle "
                "eccezioni dell'antivirus, oppure chiedi all'amministratore di rete.")
    if isinstance(reason, ssl.SSLError) or isinstance(e, ssl.SSLError):
        return "La connessione sicura con GitHub non è riuscita (%s)." % text
    if "407" in text or "Tunnel connection failed" in text or "proxy" in text.lower():
        return ("La rete usa un proxy che non consente il collegamento a GitHub: chiedi all'amministratore di rete "
                "di consentire github.com e api.github.com.")
    if isinstance(reason, socket.gaierror) or isinstance(e, socket.gaierror):
        return "Il computer non riesce a trovare GitHub: probabilmente non è collegato a Internet."
    if isinstance(reason, (TimeoutError, socket.timeout)) or isinstance(e, (TimeoutError, socket.timeout)) \
            or "timed out" in text:
        return ("GitHub non ha risposto in tempo: la connessione potrebbe essere lenta, oppure bloccata da un "
                "firewall o da un antivirus.")
    if isinstance(reason, (ConnectionRefusedError, ConnectionResetError, ConnectionAbortedError)) \
            or isinstance(e, (ConnectionRefusedError, ConnectionResetError, ConnectionAbortedError)):
        return ("Il collegamento a GitHub è stato rifiutato o interrotto: potrebbe bloccarlo un firewall "
                "o un antivirus.")
    return "Errore di connessione: %s" % text


def download_file(url, dest, progress=lambda done, total: None):
    """Scarica url in dest, comunicando l'avanzamento. Restituisce l'impronta SHA-256."""
    h = hashlib.sha256()
    with _http_open(url, timeout=30, accept="application/octet-stream") as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            progress(done, total)
    return h.hexdigest()


def can_write(folder):
    test = os.path.join(folder, ".ri_prova_scrittura")
    try:
        with open(test, "w") as f:
            f.write("x")
        os.remove(test)
        return True
    except OSError:
        return False


def launch_replacement(new_exe, exe):
    """Dopo la chiusura del programma sostituisce l'eseguibile con quello nuovo e lo riavvia (solo Windows)."""
    bat = os.path.join(tempfile.gettempdir(), "aggiorna_ridimensiona_immagini.bat")
    lines = [
        "@echo off",
        "chcp 65001 >nul",
        "set tentativi=0",
        ":sostituisci",
        'move /y "%s" "%s" >nul 2>&1' % (new_exe, exe),
        "if not errorlevel 1 goto avvia",
        "set /a tentativi+=1",
        'if %tentativi% geq 60 (start "" explorer /select,"' + new_exe + '" & goto fine)',
        "timeout /t 1 /nobreak >nul",
        "goto sostituisci",
        ":avvia",
        'start "" "%s"' % exe,
        ":fine",
        '(goto) 2>nul & del "%~f0"',
    ]
    with open(bat, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(lines) + "\n")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("_PYI", "_MEIPASS"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"  # il nuovo eseguibile parte da zero
    subprocess.Popen(["cmd", "/c", bat], env=env, close_fds=True,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def insert_markup(txt, text):
    """Scrive in un widget Text un testo con titoli (#, ##) ed elenchi (-)."""
    for line in text.strip().splitlines():
        line = line.rstrip().replace("**", "")
        if not line:
            continue
        if line.startswith("### ") or line.startswith("## "):
            txt.insert("end", line.lstrip("#").strip() + "\n", "sub")
        elif line.startswith("# "):
            txt.insert("end", line[2:] + "\n", "h")
        elif line.startswith(("- ", "* ")):
            txt.insert("end", "•  " + line[2:] + "\n", "li")
        else:
            txt.insert("end", line + "\n")


def make_text_window(parent, title, size="720x560"):
    """Finestra con un'area di testo formattato e scorrevole; restituisce (finestra, testo, riga dei pulsanti)."""
    win = tk.Toplevel(parent)
    win.title(title)
    win.geometry(size)
    win.minsize(420, 280)
    buttons = ttk.Frame(win)
    buttons.pack(side="bottom", fill="x", padx=10, pady=10)
    frame = ttk.Frame(win)
    frame.pack(fill="both", expand=True, padx=10, pady=(10, 0))
    txt = tk.Text(frame, wrap="word", padx=14, pady=10, relief="flat",
                  font=("Segoe UI", 10), spacing1=2, spacing3=2, cursor="arrow")
    sb = ttk.Scrollbar(frame, orient="vertical", command=txt.yview)
    txt.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    txt.pack(side="left", fill="both", expand=True)
    txt.tag_configure("title", font=("Segoe UI", 15, "bold"), spacing3=6)
    txt.tag_configure("h", font=("Segoe UI", 11, "bold"), spacing1=12, spacing3=4, foreground="#1a4f8b")
    txt.tag_configure("sub", font=("Segoe UI", 10, "bold"), spacing1=10, foreground="#1a4f8b")
    txt.tag_configure("li", lmargin1=12, lmargin2=28)
    txt.tag_configure("small", font=("Segoe UI", 9), foreground="#555")
    win.bind("<Escape>", lambda e: win.destroy())
    return win, txt, buttons

LANCZOS = getattr(Image, "Resampling", Image).LANCZOS

# Colore pastello della barra laterale di ciascuna sezione
SECTION_COLORS = {
    "pixel": "#8DB3DE",   # azzurro
    "peso": "#86C394",    # verde salvia
    "salva": "#E2AA78",   # pesca
    "pdf": "#B39DDB",     # lilla
}

# --------------------------------------------------------------------------- formati

Image.init()
# Estensioni che Pillow registra ma che non sono immagini utilizzabili qui
# (dati scientifici, video, formati vettoriali che richiedono programmi esterni).
_EXCLUDED_EXT = {".bufr", ".grib", ".h5", ".hdf", ".emf", ".wmf", ".eps", ".ps", ".mpeg", ".mpg"}
IMAGE_EXT = sorted(e.lower() for e, f in Image.registered_extensions().items()
                   if f in Image.OPEN and e.lower() not in _EXCLUDED_EXT)
IMAGE_EXT_SET = set(IMAGE_EXT)


def _can_save(fmt):
    if fmt not in Image.SAVE:
        return False
    if fmt == "AVIF":
        try:
            return features.check("avif")
        except Exception:
            return False
    return True


# (etichetta, formato Pillow, estensione, usa la qualità, mantiene la trasparenza)
_ALL_OUT = [
    ("JPEG", "JPEG", ".jpg", True, False),
    ("PNG", "PNG", ".png", False, True),
    ("WebP", "WEBP", ".webp", True, True),
    ("AVIF", "AVIF", ".avif", True, True),
    ("HEIC", "HEIF", ".heic", True, True),
    ("TIFF", "TIFF", ".tif", False, True),
    ("BMP", "BMP", ".bmp", False, False),
    ("GIF", "GIF", ".gif", False, True),
    ("JPEG 2000", "JPEG2000", ".jp2", False, True),
    ("TGA", "TGA", ".tga", False, True),
]
OUT_FORMATS = [f for f in _ALL_OUT if _can_save(f[1])]
OUT_BY_FMT = {f[1]: f for f in OUT_FORMATS}
LOSSY_FORMATS = [f for f in OUT_FORMATS if f[3]]          # usabili con i limiti di peso
ORIGINAL = "Come l'originale"
_ALIASES = {"MPO": "JPEG"}  # foto JPEG "multi-immagine" di alcune fotocamere

# --------------------------------------------------------------------------- guida

# Righe che iniziano con "# " = titolo, "## " = sottotitolo, "- " = punto elenco, il resto = testo normale
HELP_TEXT = """# A cosa serve
Ridimensiona Immagini crea, a partire da un gruppo di immagini, delle nuove copie con le dimensioni (in pixel) o il peso (in KB o MB) che scegli tu. Con la scheda "Comprimi PDF" riduce anche il peso dei file PDF (vedi il punto 6). Gli originali non vengono mai modificati né sovrascritti.

# 1. Scegli la scheda: per immagine o per cartella
In alto ci sono due schede. Il programma elabora soltanto le immagini della scheda aperta nel momento in cui premi "Ridimensiona".

## Ridimensiona per immagine
Serve per scegliere una a una le immagini da elaborare, anche se si trovano in cartelle diverse.
- "Aggiungi immagini..." apre una finestra in cui selezionarne una o più (tieni premuto Ctrl o Maiusc per selezionarne più di una).
- Puoi anche trascinare le immagini da Esplora risorse direttamente nell'elenco. Se trascini una cartella, vengono aggiunte le immagini contenute al suo interno (non quelle delle sottocartelle).
- "Rimuovi selezionate" toglie dall'elenco le righe selezionate; "Svuota elenco" le toglie tutte. I file sul disco non vengono toccati.
- Le immagini già presenti nell'elenco non vengono aggiunte una seconda volta.
- Sotto l'elenco viene indicato quante immagini contiene e il loro peso complessivo attuale.
Se non indichi una cartella di destinazione, le nuove immagini vengono salvate nella sottocartella "ridimensionate", creata accanto a ciascuna immagine originale.

## Ridimensiona per cartella
Serve per elaborare in un colpo solo tutte le immagini contenute in una cartella.
- Scegli la cartella con "Sfoglia..." oppure trascinala nella scheda.
- "Includi le sottocartelle": elabora anche le immagini contenute nelle cartelle interne, a qualsiasi livello.
- "Mantieni la struttura delle sottocartelle": nella destinazione vengono ricreate le stesse sottocartelle dell'originale. Se la disattivi, tutte le nuove immagini finiscono nella stessa cartella (i nomi uguali vengono numerati automaticamente).
- Sotto viene indicato quante immagini sono state trovate e il loro peso complessivo attuale.
Se non indichi una cartella di destinazione, il programma crea accanto alla cartella scelta una nuova cartella con lo stesso nome seguito da "_ridimensionate" (es. "Vacanze" diventa "Vacanze_ridimensionate").

# 2. Dimensioni in pixel
Qui decidi se cambiare le dimensioni in pixel (larghezza × altezza) delle immagini.
- Mantieni le dimensioni originali: i pixel restano quelli dell'originale. È la scelta giusta se ti interessa solo ridurre il peso dei file (sezione 3) o cambiare formato.
- Ridimensiona a: indica la larghezza e l'altezza desiderate e scegli una modalità.
Le modalità di ridimensionamento sono tre:
- Adatta entro le dimensioni: l'immagine viene rimpicciolita finché non sta tutta dentro il riquadro indicato, senza essere deformata. Esempio: con 1920 × 1080, una foto orizzontale 4000 × 3000 diventa 1440 × 1080, una verticale 3000 × 4000 diventa 810 × 1080.
- Riempi e ritaglia al centro: l'immagine copre tutto il riquadro e la parte in eccesso viene tagliata ai bordi, mantenendo il centro. Il risultato ha esattamente le misure indicate. È utile per miniature quadrate o formati fissi.
- Deforma alle dimensioni esatte: l'immagine viene stirata o schiacciata fino alle misure indicate. Le proporzioni possono cambiare.
Nella modalità "Adatta" puoi mettere 0 in uno dei due campi: quel lato viene calcolato in automatico. Esempio: larghezza 800 e altezza 0 porta tutte le immagini a 800 pixel di larghezza.
L'opzione "Non ingrandire le immagini piccole" (solo in modalità Adatta) lascia invariate le immagini già più piccole del riquadro, per non perdere nitidezza.

# 3. Peso dei file
Qui decidi se le nuove immagini devono rispettare un peso massimo. Le due caselle si possono usare da sole o insieme, e si combinano con qualsiasi scelta della sezione 2.

## Peso massimo per ogni immagine
Nessuna immagine supererà i KB indicati (1 MB = 1024 KB). Per ciascuna il programma cerca la qualità più alta che rispetta il limite. Esempio: un sito che accetta foto fino a 500 KB l'una.

## Peso massimo totale di tutte le immagini
La somma dei pesi di tutte le nuove immagini non supererà i MB indicati. Puoi usare i decimali (es. 9,5). Esempio: un allegato email da 20 MB o una piattaforma che accetta al massimo 50 MB in tutto.
Il programma applica a tutte le immagini lo stesso livello di compressione, il migliore possibile che rispetta il totale: così le foto hanno una qualità uniforme. Il totale riguarda tutte le immagini elaborate: quelle dell'elenco nella scheda "per immagine", oppure tutte quelle trovate nella scheda "per cartella" (sottocartelle comprese, se incluse).
- Il programma fa alcuni tentativi per trovare il livello giusto, quindi con molte immagini impiega un po' più tempo: la barra mostra l'avanzamento di ciascun tentativo.
- Per sicurezza, con gli allegati email lascia un piccolo margine (es. 18 MB per un limite di 20 MB): durante l'invio la codifica dell'email ne aumenta leggermente il peso.

## Entrambi i limiti insieme
Se attivi tutte e due le caselle, valgono entrambe le condizioni. Esempio: nessuna foto sopra 2 MB e, in tutto, non più di 20 MB.

## Se la qualità non basta
Normalmente il programma rispetta il peso abbassando solo la qualità, fino a un minimo di 30, senza toccare i pixel. Se nemmeno così il limite si può rispettare, avvisa e non salva quelle immagini.
- Attivando "Se la qualità non basta, consenti di ridurre i pixel", la qualità scende al massimo fino a 40 e poi, se serve, vengono ridotti anche i pixel, un poco alla volta. In genere il risultato è più gradevole di una qualità molto bassa.
- Se alcune immagini vengono salvate con qualità inferiore a 40 (succede solo senza riduzione dei pixel), al termine compare un avviso: potrebbero apparire visibilmente rovinate.
- Al termine, la riga di stato indica il peso ottenuto, le qualità usate e, se sono stati ridotti, di quanto sono stati ridotti i pixel.

## Esempi di combinazioni
- Solo pixel: "Ridimensiona a" 1920 × 1080, nessun limite di peso. Tutte le immagini vengono portate a quelle dimensioni.
- Solo peso: "Mantieni le dimensioni originali" e "Peso massimo per ogni immagine" 1000 KB. I pixel restano invariati, cambia solo la compressione.
- Pixel e peso: "Ridimensiona a" 1920 × 1080 e "Peso massimo totale" 20 MB. Prima si riducono i pixel, poi la compressione viene regolata per stare nei 20 MB.
- Solo conversione: "Mantieni le dimensioni originali", nessun limite e formato JPEG. Utile per esempio per trasformare le foto HEIC dell'iPhone in JPEG.

# 4. Salvataggio
- Formato: senza limiti di peso puoi mantenere il formato di ciascuna immagine ("Come l'originale") oppure convertirle tutte in un unico formato. Con "Come l'originale", le immagini in un formato che il programma non sa scrivere (per esempio PSD o ICO) vengono salvate in PNG.
- Con i limiti di peso si può scegliere solo fra i formati compressi: JPEG, WebP, AVIF e HEIC.
- Qualità: da 1 a 100; stabilisce quanto vengono compressi i file JPEG, WebP, AVIF e HEIC. Tra 80 e 90 si ottiene un buon compromesso fra qualità e peso. La casella compare solo quando serve: con i limiti di peso la qualità viene scelta in automatico, mentre i formati senza perdita (PNG, TIFF, BMP, GIF, JPEG 2000, TGA) non la usano.
- Cartella: dove salvare le nuove immagini. Se la lasci vuota, vale quanto descritto nelle due schede al punto 1.
- Suffisso: testo aggiunto al nome delle nuove immagini (es. "vacanze.jpg" diventa "vacanze_ridimensionata.jpg"). Puoi lasciarlo vuoto: anche in quel caso le immagini originali non vengono mai sovrascritte.
Attenzione: se nella cartella di destinazione esiste già un file con lo stesso nome, viene sostituito.

## Quale formato scegliere?
- JPEG: il più diffuso, adatto alle foto e accettato ovunque. Non conserva la trasparenza.
- PNG: senza perdita di qualità, adatto a grafica, loghi, schermate e immagini trasparenti. I file sono più pesanti.
- WebP: a parità di qualità pesa circa un terzo in meno del JPEG; è accettato da tutti i browser e dalla maggior parte dei programmi recenti.
- AVIF e HEIC: i più efficienti (file molto leggeri), ma non tutti i programmi e i siti li accettano. AVIF è anche più lento da creare.
- TIFF: usato in tipografia e in archivio, senza perdita di qualità (file pesanti).
- BMP, GIF, JPEG 2000, TGA: per esigenze particolari. GIF è limitato a 256 colori, quindi non è adatto alle foto.
Nel dubbio, usa JPEG.

# 5. Avvia
Premi "Ridimensiona". La barra mostra l'avanzamento; al termine viene indicato quante immagini sono state salvate. Con "Apri cartella di uscita" vedi subito i risultati.
Se qualche immagine non può essere elaborata (file danneggiato, formato non supportato, cartella protetta, peso impossibile da rispettare) il programma prosegue con le altre e alla fine mostra l'elenco degli errori.

# 6. Comprimi PDF
La scheda "Comprimi PDF" riduce il peso dei file PDF che contengono immagini: documenti d'identità fotografati o scansionati, pagine passate allo scanner, relazioni con foto. Spesso questi PDF pesano molti MB perché le immagini al loro interno hanno una risoluzione molto più alta del necessario.
Il programma riduce e ricomprime soltanto le immagini contenute nel PDF. Il testo vero, i link, i segnalibri e la grafica restano intatti, e il testo che si poteva selezionare resta selezionabile.
- Aggiungi i PDF con "Aggiungi PDF..." oppure trascinandoli nell'elenco (anche un'intera cartella).
- Sotto l'elenco vengono indicati il peso complessivo e quanta parte è occupata dalle immagini. Se le immagini sono una piccola parte del peso, la compressione servirà poco: il peso dipende da testo, caratteri o grafica.
Quando questa scheda è aperta, al posto delle sezioni per le immagini compaiono quelle per i PDF.

## Tipo di documento
- Documento d'identità o foto (a colori): 200 dpi, colori mantenuti. Adatto a carte d'identità, patenti, passaporti, tessere e foto. Di solito un documento fotografato col telefono passa da alcuni MB a poche centinaia di KB, restando ben leggibile.
- Documento di testo scansionato (scala di grigi): 200 dpi, senza colori. Adatto a lettere, contratti, moduli e ricevute.
- Solo testo, bianco e nero (file minimi): ogni punto diventa bianco o nero. Il testo resta nitidissimo e i file diventano piccolissimi, ma foto, timbri colorati e documenti d'identità diventano scuri o illeggibili: usalo solo per pagine di testo nero su fondo chiaro.
- Personalizzato: scegli liberamente colori, risoluzione e qualità. Diventa "Personalizzato" automaticamente se modifichi uno di questi valori.

## Risoluzione e qualità
- Risoluzione (dpi, punti per pollice): quanto sono dettagliate le immagini sulla pagina. 300 dpi = stampa di qualità; 200 dpi = ottimo per documenti; 150 dpi = buono a schermo e per la stampa d'ufficio; 100 dpi o meno = solo per leggere a schermo. Le immagini che hanno già una risoluzione più bassa non vengono ingrandite.
- Qualità: compressione JPEG delle immagini a colori o in scala di grigi, da 1 a 100. Tra 65 e 80 si ottiene un buon compromesso. Non si usa in bianco e nero.

## Peso massimo per ogni PDF
Indica quanti MB al massimo deve pesare ciascun PDF (es. 2 MB per un portale che accetta solo file piccoli). Il programma prova da solo risoluzioni e qualità, da 300 fino a 50 dpi, e sceglie la migliore che rispetta il limite, mantenendo l'impostazione dei colori scelta.
- Se il limite non si può raggiungere (per esempio perché il peso dipende soprattutto dal testo o dalla grafica), il PDF viene comunque salvato nella versione più leggera ottenuta e al termine compare un avviso.
- Per i documenti di solo testo, il bianco e nero rispetta limiti molto bassi restando nitido; a colori, con limiti molto bassi, il testo può diventare sfocato.

## Altre opzioni
- Rimuovi metadati e miniature: elimina dal PDF informazioni come autore, programma usato, date e anteprime delle pagine. Consigliato per i documenti personali.
- Cartella e suffisso: i PDF compressi vengono salvati accanto agli originali, con "_compresso" aggiunto al nome (es. "carta_identita.pdf" diventa "carta_identita_compresso.pdf"), oppure nella cartella indicata. L'originale non viene mai modificato.

## Da sapere
- I PDF protetti da password non possono essere elaborati: il programma li segnala.
- Se un PDF contiene una firma digitale, nella versione compressa la firma non è più valida: il programma avvisa. Se la firma è necessaria, invia il PDF originale.
- Se un PDF è già compresso al meglio, viene salvata una copia identica e compare un avviso.
- Tutto avviene sul tuo computer: i documenti non vengono inviati da nessuna parte.

# 7. Aggiornamenti e novità
All'avvio il programma controlla su GitHub, in pochi secondi e senza bloccare il lavoro, se è disponibile una versione più recente. Se c'è, mostra una finestra con le novità e tre scelte:
- Scarica e installa: il programma scarica la nuova versione, controlla che il file sia integro, poi si chiude, si aggiorna e si riapre da solo.
- Salta questa versione: non verrà più proposta all'avvio (resta disponibile con "Controlla aggiornamenti").
- Più tardi: la proposta ricompare alla prossima apertura.
Dal menu "?" puoi anche:
- Novità delle versioni: l'elenco delle novità di tutte le versioni.
- Controlla aggiornamenti: controlla subito, in qualsiasi momento.
- Controlla gli aggiornamenti all'avvio: togli la spunta per disattivare il controllo automatico.
Per il controllo serve la connessione a Internet, ma non serve un account GitHub. Senza connessione il programma funziona normalmente e semplicemente non controlla.
Se con "Controlla aggiornamenti" il controllo non riesce, il messaggio spiega il motivo: nessuna connessione, limite di controlli di GitHub (60 all'ora per ogni indirizzo Internet, condiviso da tutti i computer di un ufficio), antivirus o rete aziendale che bloccano il collegamento, proxy, tempo scaduto. In ogni caso puoi aprire la pagina delle versioni nel browser e scaricare a mano la versione più recente. Non viene inviato nessun dato personale né alcuna informazione sui tuoi file.
Se il programma si trova in una cartella protetta (per esempio "Programmi"), la nuova versione viene scaricata nella cartella Download e va copiata a mano al posto di quella vecchia.

# Formati supportati
- In lettura: JPEG, PNG, HEIC/HEIF (le foto degli iPhone), WebP, AVIF, TIFF, BMP, GIF, JPEG 2000, PSD (Photoshop: viene letta l'immagine unita), TGA, ICO, PCX, DDS, QOI, PPM/PGM/PBM e altri formati meno diffusi. L'elenco delle estensioni riconosciute si trova in fondo alla guida.
- In scrittura: JPEG, PNG, WebP, AVIF, HEIC, TIFF, BMP, GIF, JPEG 2000 e TGA.
- Non sono supportati i file RAW delle fotocamere (CR2, NEF, ARW...), i formati vettoriali (SVG, EPS, AI) e i PDF.

# Buono a sapersi
- Le foto scattate col telefono vengono raddrizzate in automatico secondo l'orientamento registrato dalla fotocamera.
- La trasparenza viene mantenuta in PNG, WebP, AVIF, HEIC, TIFF, GIF, JPEG 2000 e TGA; in JPEG e BMP le parti trasparenti diventano bianche.
- Delle immagini animate (GIF, WebP, APNG) viene salvato solo il primo fotogramma; dei file con più pagine (TIFF) solo la prima pagina.
- Il profilo colore delle immagini viene conservato, quando il formato di destinazione lo permette.
- I dati EXIF (data di scatto, fotocamera, posizione GPS) non vengono copiati nelle nuove immagini.
- Le immagini a 16 bit per canale vengono salvate a 8 bit.
"""

# --------------------------------------------------------------------------- logica immagini


def compute_geometry(sw, sh, tw, th, mode, no_upscale):
    """Restituisce (larghezza, altezza, box_sorgente) per il ridimensionamento."""
    if mode == "fit":
        if tw == 0 and th == 0:
            r = 1.0
        elif tw == 0:
            r = th / sh
        elif th == 0:
            r = tw / sw
        else:
            r = min(tw / sw, th / sh)
        if no_upscale and r > 1:
            r = 1.0
        return max(1, round(sw * r)), max(1, round(sh * r)), (0, 0, sw, sh)
    if mode == "crop":
        r = max(tw / sw, th / sh)
        cw, ch = min(sw, tw / r), min(sh, th / r)
        left, top = (sw - cw) / 2, (sh - ch) / 2
        return tw, th, (left, top, left + cw, top + ch)
    return tw, th, (0, 0, sw, sh)  # deforma


def has_alpha(img):
    return "A" in img.getbands() or "transparency" in img.info


def normalize(img):
    """Porta l'immagine in modalità RGB, RGBA o L (8 bit), adatte al ricampionamento di qualità."""
    if img.mode in ("RGB", "RGBA", "L"):
        return img
    if img.mode.startswith("I"):                      # 16/32 bit in scala di grigi
        return img.convert("I").point(lambda v: v * (1 / 256)).convert("L")
    if img.mode == "F":
        return img.convert("L")
    if img.mode == "1":
        return img.convert("L")
    return img.convert("RGBA" if has_alpha(img) else "RGB")


def flatten_on_white(img):
    """La trasparenza diventa sfondo bianco (per i formati che non la supportano)."""
    if img.mode in ("RGB", "L"):
        return img
    rgba = img.convert("RGBA")
    bg = Image.new("RGB", rgba.size, (255, 255, 255))
    bg.paste(rgba, mask=rgba.split()[3])
    return bg


def icc_matches(icc, mode):
    """Il profilo colore va allegato solo se corrisponde allo spazio colore finale."""
    if not icc or len(icc) < 20:
        return False
    space = icc[16:20]
    return (space == b"RGB " and mode in ("RGB", "RGBA")) or (space == b"GRAY" and mode in ("L", "LA"))


def encode(img, fmt, quality, icc=None):
    """Codifica l'immagine nel formato richiesto e restituisce i byte."""
    if not OUT_BY_FMT[fmt][4]:
        img = flatten_on_white(img)
    kw = {}
    if fmt == "JPEG":
        kw = {"quality": quality, "optimize": True, "progressive": True}
    elif fmt == "WEBP":
        kw = {"quality": quality, "method": 4}
    elif fmt in ("AVIF", "HEIF"):
        kw = {"quality": quality}
    elif fmt == "PNG":
        kw = {"optimize": True}
    elif fmt == "TIFF":
        kw = {"compression": "tiff_lzw"}
    elif fmt == "GIF":
        img = img.convert("RGBA") if img.mode == "RGBA" else img.convert("RGB")
    if fmt in ("JPEG", "PNG", "WEBP", "TIFF", "AVIF", "HEIF", "JPEG2000") and icc_matches(icc, img.mode):
        kw["icc_profile"] = icc
    buf = io.BytesIO()
    img.save(buf, fmt, **kw)
    return buf.getvalue()


def friendly_error(e):
    """Messaggio d'errore comprensibile, in italiano."""
    from PIL import UnidentifiedImageError
    if isinstance(e, UnidentifiedImageError):
        return "file danneggiato o non riconosciuto come immagine"
    if HAS_PDF and isinstance(e, getattr(pymupdf, "FileDataError", ())):
        return "file PDF danneggiato o non valido"
    if isinstance(e, FileNotFoundError):
        return "file o cartella non trovati"
    if isinstance(e, PermissionError):
        return "accesso negato (file in uso o cartella protetta)"
    if isinstance(e, MemoryError):
        return "memoria insufficiente per un'immagine così grande"
    if isinstance(e, Image.DecompressionBombError):
        return "immagine troppo grande per essere elaborata in sicurezza"
    if isinstance(e, OSError) and getattr(e, "errno", None) == 28:
        return "spazio su disco esaurito"
    return str(e) or e.__class__.__name__


def output_path(src, out_dir, suffix, ext, used=None):
    base = os.path.splitext(os.path.basename(src))[0] + suffix
    out = os.path.join(out_dir, base + ext)
    k = 1
    # mai sovrascrivere l'originale né un altro file creato nella stessa elaborazione
    while (os.path.normcase(os.path.abspath(out)) == os.path.normcase(os.path.abspath(src))
           or (used is not None and os.path.normcase(os.path.abspath(out)) in used)):
        out = os.path.join(out_dir, "%s_%d%s" % (base, k, ext))
        k += 1
    if used is not None:
        used.add(os.path.normcase(os.path.abspath(out)))
    return out


def write_file(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def fmt_size(n):
    if n >= 1024 * 1024:
        return ("%.2f MB" % (n / 1024 / 1024)).replace(".", ",")
    return "%d KB" % max(1, round(n / 1024))


# --- livelli di compressione per i limiti di peso
# Ogni livello è (scala dei pixel, qualità), dal migliore al più leggero.

QUALITY_STEPS = (95, 92, 90, 88, 86, 84, 82, 80, 78, 76, 74, 72, 70, 67, 64, 60)
QUALITY_LOW = (56, 52, 48, 44, 40, 36, 33, 30)   # usate solo se i pixel non si possono ridurre
MIN_QUALITY_SHRINK = 40                          # con riduzione dei pixel: qualità minima prima di ridurli
LOW_QUALITY_WARNING = 40                         # sotto questa qualità si avvisa l'utente
CACHE_LIMIT = 1_200_000_000   # byte di immagini tenute in memoria per accelerare i tentativi
PREVIEW_PIXELS = 1_500_000    # dimensione dell'anteprima usata per stimare i pesi
PROBE_QUALITIES = (95, 86, 76, 60, 45, 30)
SAFETY = 0.97                 # margine sulla prima stima
PLAUSIBLE = 0.03              # dopo la calibrazione si prova un livello migliore solo se la stima sfora al massimo del 3%


def make_ladder(allow_shrink):
    if allow_shrink:
        # prima si abbassa la qualità fino a 40, poi si riducono i pixel del 5% alla volta
        qs = QUALITY_STEPS + tuple(q for q in QUALITY_LOW if q >= MIN_QUALITY_SHRINK)
        return [(1.0, q) for q in qs] + [(0.95 ** k, MIN_QUALITY_SHRINK) for k in range(1, 90)]
    return [(1.0, q) for q in QUALITY_STEPS + QUALITY_LOW]


def _plan_dims(W, H, s):
    """Dimensioni finali (alla scala 1) e riquadro sorgente per un'immagine raddrizzata W × H."""
    if s["resize"]:
        return compute_geometry(W, H, s["tw"], s["th"], s["mode"], s["no_upscale"])
    return W, H, (0, 0, W, H)


def _oriented_size(im):
    """Dimensioni dell'immagine dopo la correzione della rotazione indicata nell'EXIF."""
    raw_w, raw_h = im.size
    try:
        orient = im.getexif().get(0x0112, 1)
    except Exception:
        orient = 1
    return (raw_h, raw_w) if orient in (5, 6, 7, 8) else (raw_w, raw_h)


def target_size(path, s):
    """Dimensioni finali in pixel (alla scala 1), leggendo solo l'intestazione del file."""
    with Image.open(path) as im:
        w, h, _ = _plan_dims(*_oriented_size(im), s)
    return w, h


def load_base(path, s, scale=1.0):
    """Apre l'immagine già alla dimensione richiesta (dimensioni finali × scala).
    Per i JPEG grandi usa la decodifica ridotta (1/2, 1/4, 1/8), molto più veloce.
    Restituisce (immagine, profilo colore, formato originale, scala)."""
    with Image.open(path) as im:
        fmt = _ALIASES.get(im.format, im.format)
        icc = im.info.get("icc_profile")
        if getattr(im, "n_frames", 1) > 1:
            im.seek(0)
        raw_w, raw_h = im.size
        W, H = _oriented_size(im)
        w, h, box = _plan_dims(W, H, s)
        tw, th = max(1, round(w * scale)), max(1, round(h * scale))
        f = max(tw / (box[2] - box[0]), th / (box[3] - box[1]))  # pixel finali per pixel sorgente
        if f <= 0.5 and im.format in ("JPEG", "MPO"):
            im.draft(None, (math.ceil(raw_w * f), math.ceil(raw_h * f)))
        dec_w, dec_h = im.size  # dimensioni effettivamente decodificate (prima della rotazione)
        im = ImageOps.exif_transpose(im)  # corregge la rotazione delle foto
        im.load()
    im = normalize(im)

    # Dimensioni piene reali dopo la rotazione effettiva (che può differire da quanto letto nell'EXIF)
    swapped = im.size == (dec_h, dec_w) and dec_w != dec_h
    full = (raw_h, raw_w) if swapped else (raw_w, raw_h)
    if full != (W, H):
        w, h, box = _plan_dims(full[0], full[1], s)
        tw, th = max(1, round(w * scale)), max(1, round(h * scale))
    # Scala separata per larghezza e altezza: la decodifica ridotta arrotonda per eccesso
    kx, ky = full[0] / im.width, full[1] / im.height
    box = (max(0.0, box[0] / kx), max(0.0, box[1] / ky),
           min(float(im.width), box[2] / kx), min(float(im.height), box[3] / ky))
    if (tw, th) != im.size or box != (0, 0, im.width, im.height):
        im = im.resize((tw, th), LANCZOS, box=box)
    return im, icc, fmt, scale


def encode_level(base, scale, quality, fmt):
    img, icc, _, s0 = base
    if scale < s0 * 0.999:
        r = scale / s0
        img = img.resize((max(1, round(img.width * r)), max(1, round(img.height * r))), LANCZOS)
    return encode(img, fmt, quality, icc)


def find_best(fits, start, last):
    """Indice più basso (= risultato migliore) per cui fits(indice) è vero, partendo da una stima.
    Si allarga a passi crescenti (1, 2, 4...) e poi si restringe: pochi tentativi se la stima è buona.
    Restituisce None se nemmeno l'ultimo livello va bene."""
    start = min(max(start, 0), last)
    if fits(start):
        good, bad, step = start, -1, 1
        while good > 0:
            cand = max(good - step, 0)
            if fits(cand):
                good = cand
                step *= 2
            else:
                bad = cand
                break
    else:
        bad, step, good = start, 1, None
        while True:
            idx = min(bad + step, last)
            if fits(idx):
                good = idx
                break
            if idx == last:
                return None
            bad = idx
            step *= 2
    lo, hi = bad + 1, good
    while lo < hi:
        mid = (lo + hi) // 2
        if fits(mid):
            hi = mid
        else:
            lo = mid + 1
    return hi


def find_near(fits, start, last, plausible):
    """Come find_best, ma per una stima già calibrata: si sposta di un livello alla volta.
    Verso la qualità migliore prova solo i livelli che la stima considera plausibili."""
    start = min(max(start, 0), last)
    if fits(start):
        L = start
        while L > 0 and plausible(L - 1) and fits(L - 1):
            L -= 1
        return L
    L = start
    for _ in range(2):  # troppo pesante: un livello alla volta, poi una ricerca più ampia
        if L >= last:
            return None
        L += 1
        if fits(L):
            return L
    return find_best(fits, L, last)


def describe_levels(levels):
    """Testo riassuntivo delle qualità e delle dimensioni usate."""
    qs = [q for _, q in levels]
    ss = [sc for sc, _ in levels]
    q_txt = "qualità %d" % qs[0] if min(qs) == max(qs) else "qualità da %d a %d" % (min(qs), max(qs))
    if min(ss) < 1:
        lo, hi = round(min(ss) * 100), round(max(ss) * 100)
        q_txt += ", pixel ridotti al %d%%" % lo if lo == hi else ", pixel ridotti fino al %d%%" % lo
    return q_txt


def process_all(jobs, s, report=lambda kind, val: None):
    """
    Elabora tutte le immagini.
    jobs: elenco di (immagine, cartella di destinazione).
    s: impostazioni (resize, tw, th, mode, no_upscale, per_file, max_kb, total, total_bytes,
       allow_shrink, out_fmt, weight_fmt, quality, suffix).
    Restituisce (immagini salvate, errori, riepilogo, qualità minima usata o None).
    """
    errors = []
    used = set()
    n = len(jobs)
    written = 0

    def fail(path, e):
        errors.append("%s: %s" % (os.path.basename(path), friendly_error(e)))

    # --- nessun limite di peso: dimensioni (o originali) + formato e qualità scelti
    if not (s["per_file"] or s["total"]):
        report("max", n)
        for i, (path, out_dir) in enumerate(jobs, 1):
            report("status", "Elaborazione %d di %d: %s" % (i, n, os.path.basename(path)))
            try:
                im, icc, src_fmt, _ = load_base(path, s)
                fmt = s["out_fmt"]
                if fmt == ORIGINAL:
                    fmt = src_fmt if src_fmt in OUT_BY_FMT else "PNG"
                data = encode(im, fmt, s["quality"], icc)
                write_file(output_path(path, out_dir, s["suffix"], OUT_BY_FMT[fmt][2], used), data)
                written += 1
                report("out", out_dir)
            except Exception as e:
                fail(path, e)
            report("progress", i)
        return written, errors, "", None

    # --- con limiti di peso
    fmt = s["weight_fmt"]
    ext = OUT_BY_FMT[fmt][2]
    ladder = make_ladder(s["allow_shrink"])
    last = len(ladder) - 1
    no_shrink_hint = "" if s["allow_shrink"] else \
        " senza ridurre i pixel (attiva \"consenti di ridurre i pixel\" o aumenta il limite)"
    cache, cached = {}, [0]
    valid = list(jobs)

    def base_of(path, need):
        """Immagine di lavoro con risoluzione almeno pari alla scala richiesta (tenuta in memoria se possibile)."""
        b = cache.get(path)
        if b is not None and b[3] >= need * 0.999:
            return b
        if b is not None:
            cached[0] -= b[0].width * b[0].height * len(b[0].getbands())
            del cache[path]
        b = load_base(path, s, min(1.0, need * 1.25))  # un po' di margine per i tentativi successivi
        size = b[0].width * b[0].height * len(b[0].getbands())
        if cached[0] + size <= CACHE_LIMIT:
            cache[path] = b
            cached[0] += size
        return b

    def enc(path, idx):
        sc, q = ladder[idx]
        return encode_level(base_of(path, sc), sc, q, fmt)

    # 1) analisi rapida: su un'anteprima ridotta si misura quanto pesa ogni immagine alle varie qualità
    est = {}
    report("max", n)
    for i, job in enumerate(jobs, 1):
        path = job[0]
        report("status", "Analisi delle immagini: %d di %d: %s" % (i, n, os.path.basename(path)))
        try:
            w, h = target_size(path, s)
            ps = min(1.0, math.sqrt(PREVIEW_PIXELS / (w * h)))
            prev, icc, _, _ = load_base(path, s, ps)
            small = prev.resize((max(1, prev.width // 2), max(1, prev.height // 2)), LANCZOS)
            pix, pix_s = prev.width * prev.height, small.width * small.height
            probes = []
            for q in PROBE_QUALITIES:
                b = len(encode(prev, fmt, q, icc)) / pix
                b_s = len(encode(small, fmt, q, icc)) / pix_s
                # come cambia il peso per pixel al variare della risoluzione (le foto grandi si comprimono meglio)
                alpha = math.log(b / b_s) / math.log(pix / pix_s) if pix > pix_s and b_s > 0 else 0.0
                probes.append((q, b, min(0.05, max(-0.6, alpha))))
            est[path] = (w * h, pix, probes)
        except Exception as e:
            fail(path, e)
            valid.remove(job)
        report("progress", i)

    def predict(path, idx):
        """Peso stimato dell'immagine al livello idx."""
        sc, q = ladder[idx]
        full, pix, probes = est[path]
        for (q1, b1, a1), (q2, b2, a2) in zip(probes, probes[1:]):  # interpolazione fra le qualità misurate
            if q2 <= q <= q1:
                t = (q1 - q) / (q1 - q2) if q1 != q2 else 0
                bpp, alpha = b1 * (b2 / b1) ** t, a1 + (a2 - a1) * t
                break
        else:
            _, bpp, alpha = probes[0] if q > probes[0][0] else probes[-1]
        target = full * sc * sc
        return bpp * (target / pix) ** alpha * target

    def first_predicted(test):
        return next((i for i in range(last + 1) if test(i)), last)

    # 2) peso massimo per ogni immagine
    pf = {}
    if s["per_file"]:
        cap = s["max_kb"] * 1024
        report("max", len(valid))
        levels = []
        for i, job in enumerate(list(valid), 1):
            path, out_dir = job
            report("status", "Peso per immagine: %d di %d: %s" % (i, len(est), os.path.basename(path)))
            try:
                memo = {}

                def fits(idx, path=path, memo=memo):
                    if idx not in memo:
                        d = enc(path, idx)
                        memo[idx] = (len(d) <= cap, d)
                    return memo[idx][0]

                start = first_predicted(lambda k: predict(path, k) <= cap * SAFETY)
                ratio = 1.0
                for _ in range(2):  # correzione della stima con il peso reale
                    fits(start)
                    ratio = len(memo[start][1]) / predict(path, start)
                    new_start = first_predicted(lambda k: ratio * predict(path, k) <= cap)
                    if new_start == start:
                        break
                    start = new_start
                best = find_near(fits, start, last,
                                 lambda k: ratio * predict(path, k) <= cap * (1 + PLAUSIBLE))
                if best is None:
                    raise RuntimeError("impossibile scendere sotto %d KB%s" % (s["max_kb"], no_shrink_hint))
                pf[path] = best
                if not s["total"]:
                    write_file(output_path(path, out_dir, s["suffix"], ext, used), memo[best][1])
                    written += 1
                    levels.append(ladder[best])
                    report("out", out_dir)
            except Exception as e:
                fail(path, e)
                valid.remove(job)
            if not s["total"]:
                b = cache.pop(path, None)  # non serve più: libera memoria
                if b is not None:
                    cached[0] -= b[0].width * b[0].height * len(b[0].getbands())
            report("progress", i)
        if not s["total"]:
            cache.clear()
            if not levels:
                return written, errors, "", None
            return written, errors, describe_levels(levels), min(q for _, q in levels)

    # 3) peso massimo totale: stesso livello per tutte (mai migliore di quello imposto dal peso per file)
    limit = s["total_bytes"]
    if not valid:
        return written, errors, "", None
    # le immagini più pesanti per prime: se un tentativo sfora, ce ne si accorge subito
    valid.sort(key=lambda j: -predict(j[0], 0))
    attempt = [0]
    results = {}
    calib = {}  # livello -> rapporto fra peso reale e peso stimato

    def try_global(L):
        attempt[0] += 1
        out, total, pred = [], 0, 0.0
        todo = list(valid)
        report("max", len(todo))
        for i, job in enumerate(todo, 1):
            path = job[0]
            report("status", "Compressione, tentativo %d: immagine %d di %d" % (attempt[0], i, len(todo)))
            idx = max(L, pf.get(path, 0))
            try:
                data = enc(path, idx)
            except Exception as e:
                fail(path, e)
                valid.remove(job)
                cache.pop(path, None)
                continue
            out.append((job, data, idx))
            total += len(data)
            pred += predict(path, idx)
            report("progress", i)
            if total > limit:
                calib[L] = total / pred
                return None  # già troppo: inutile proseguire con questo livello
        if pred:
            calib[L] = total / pred
        return out if out else None

    def fits_global(L):
        if L not in results:
            results[L] = try_global(L)
        return results[L] is not None

    def total_pred(L):
        return sum(predict(j[0], max(L, pf.get(j[0], 0))) for j in valid)

    # primo tentativo sulla stima, poi la stima viene corretta con il peso reale (due volte al massimo)
    start = first_predicted(lambda L: total_pred(L) <= limit * SAFETY)
    ratio = 1.0
    for _ in range(2):
        if not valid:
            break
        fits_global(start)
        ratio = calib.get(start, ratio)
        new_start = first_predicted(lambda L: ratio * total_pred(L) <= limit)
        if new_start == start:
            break
        start = new_start
    best_L = find_near(fits_global, start, last,
                       lambda L: ratio * total_pred(L) <= limit * (1 + PLAUSIBLE)) if valid else None
    best = results.get(best_L) if best_L is not None else None
    results.clear()
    cache.clear()

    if best is None:
        if valid:
            raise RuntimeError("Il peso totale di %s non si può raggiungere%s." % (fmt_size(limit), no_shrink_hint))
        return written, errors, "", None

    best = [r for r in best if r[0] in valid]  # esclude eventuali immagini fallite in tentativi successivi
    report("max", len(best))
    total = 0
    for i, ((path, out_dir), data, idx) in enumerate(best, 1):
        report("status", "Salvataggio %d di %d: %s" % (i, len(best), os.path.basename(path)))
        try:
            write_file(output_path(path, out_dir, s["suffix"], ext, used), data)
            total += len(data)
            written += 1
            report("out", out_dir)
        except Exception as e:
            fail(path, e)
        report("progress", i)

    levels = [ladder[idx] for _, _, idx in best]
    info = "totale %s su %s, %s" % (fmt_size(total), fmt_size(limit), describe_levels(levels))
    return written, errors, info, min(q for _, q in levels)


# --------------------------------------------------------------------------- PDF

# Tipi di documento proposti: (risoluzione in dpi, qualità JPEG, colori)
PDF_PRESETS = [
    ("Documento d'identità o foto (a colori)", 200, 75, "color"),
    ("Documento di testo scansionato (scala di grigi)", 200, 70, "gray"),
    ("Solo testo, bianco e nero (file minimi)", 200, 70, "bw"),
    ("Personalizzato", None, None, None),
]
PDF_COLORS = [("A colori", "color"), ("Scala di grigi", "gray"), ("Bianco e nero", "bw")]
# Livelli provati per il peso massimo, dal migliore al più leggero: (dpi, qualità)
PDF_LEVELS = [(300, 85), (250, 82), (200, 80), (200, 72), (175, 70), (150, 70), (150, 62), (125, 60),
              (110, 55), (100, 50), (90, 45), (80, 42), (72, 40), (60, 40), (50, 40)]


def pdf_analyze(path):
    """Informazioni rapide su un PDF: pagine, peso, quota occupata dalle immagini, protezione, firma."""
    info = {"size": os.path.getsize(path), "pages": 0, "images": 0, "encrypted": False, "signed": False}
    doc = pymupdf.open(path)
    try:
        if doc.needs_pass:
            info["encrypted"] = True
            return info
        info["pages"] = doc.page_count
        try:
            info["signed"] = doc.get_sigflags() > 0
        except Exception:
            pass
        seen = set()
        for page in doc:
            for img in page.get_images(full=True):
                xref = img[0]
                if xref in seen:
                    continue
                seen.add(xref)
                try:
                    info["images"] += len(doc.xref_stream_raw(xref))
                    smask = img[1]
                    if smask and smask not in seen:
                        seen.add(smask)
                        info["images"] += len(doc.xref_stream_raw(smask))
                except Exception:
                    pass
    finally:
        doc.close()
    return info


def _otsu(img):
    """Soglia automatica per il bianco e nero (metodo di Otsu)."""
    hist = img.histogram()[:256]
    total = sum(hist)
    sum_all = sum(i * h for i, h in enumerate(hist))
    w_b = sum_b = 0
    best, thr = -1.0, 128
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b, m_f = sum_b / w_b, (sum_all - sum_b) / w_f
        between = w_b * w_f * (m_b - m_f) ** 2
        if between > best:
            best, thr = between, t
    return thr


def _image_placements(doc):
    """Per ogni immagine (xref): area massima occupata sulla pagina, in pollici quadrati."""
    areas = {}
    for page in doc:
        try:
            infos = page.get_image_info(xrefs=True)
        except Exception:
            infos = []
        for inf in infos:
            xref = inf.get("xref", 0)
            if xref <= 0:
                continue
            x0, y0, x1, y1 = inf["bbox"]
            area = abs(x1 - x0) * abs(y1 - y0) / (72.0 * 72.0)
            areas[xref] = max(areas.get(xref, 0.0), area)
    return areas


def _recompress_image(doc, xref, area_in2, dpi, quality, color):
    """Ricomprime un'immagine del PDF. Restituisce True se è stata sostituita."""
    if doc.xref_get_key(xref, "Subtype")[1] != "/Image":
        return False
    if doc.xref_get_key(xref, "ImageMask")[1] == "true":
        return False  # maschere a 1 bit: già leggerissime
    try:
        bpc = int(doc.xref_get_key(xref, "BitsPerComponent")[1])
    except ValueError:
        bpc = 8
    raw_len = len(doc.xref_stream_raw(xref))
    pix = pymupdf.Pixmap(doc, xref)
    if bpc == 1 and color != "bw":
        return False  # già in bianco e nero: non conviene toccarla
    if pix.alpha:
        pix = pymupdf.Pixmap(pix, 0)
    if pix.colorspace is None or pix.colorspace.n not in (1, 3):
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    img = Image.frombytes("L" if pix.n == 1 else "RGB", (pix.width, pix.height), pix.samples)
    pix = None

    # risoluzione effettiva sulla pagina e riduzione se supera quella richiesta
    if area_in2 > 0:
        eff_dpi = math.sqrt(img.width * img.height / area_in2)
        if eff_dpi > dpi * 1.05:
            r = dpi / eff_dpi
            img = img.resize((max(1, round(img.width * r)), max(1, round(img.height * r))), LANCZOS)

    if color in ("gray", "bw") and img.mode != "L":
        img = img.convert("L")
    if color == "bw":
        thr = _otsu(img)
        img = img.point(lambda v: 255 if v > thr else 0).convert("1")
        data = zlib.compress(img.tobytes(), 9)
        keys = {"Filter": "/FlateDecode", "ColorSpace": "/DeviceGray", "BitsPerComponent": "1"}
    else:
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
        data = buf.getvalue()
        keys = {"Filter": "/DCTDecode", "ColorSpace": "/DeviceGray" if img.mode == "L" else "/DeviceRGB",
                "BitsPerComponent": "8"}

    if len(data) >= raw_len and color == "color":
        return False  # la versione nuova non è più leggera: si tiene l'originale
    doc.update_stream(xref, data, compress=False)
    doc.xref_set_key(xref, "Width", str(img.width))
    doc.xref_set_key(xref, "Height", str(img.height))
    for k, v in keys.items():
        doc.xref_set_key(xref, k, v)
    for k in ("DecodeParms", "Decode", "Intent"):
        doc.xref_set_key(xref, k, "null")
    return True


def pdf_compress_bytes(path, dpi, quality, color, clean_meta):
    """Comprime un PDF e restituisce i byte del nuovo file."""
    doc = pymupdf.open(path)
    try:
        if doc.needs_pass:
            raise RuntimeError("il PDF è protetto da password")
        for xref, area in _image_placements(doc).items():
            try:
                _recompress_image(doc, xref, area, dpi, quality, color)
            except Exception:
                pass  # un'immagine che non si riesce a decodificare resta com'era
        if clean_meta:
            try:
                doc.set_metadata({})
                doc.del_xml_metadata()
            except Exception:
                pass
            for page in doc:
                try:
                    doc.xref_set_key(page.xref, "Thumb", "null")
                except Exception:
                    pass
        try:
            return doc.tobytes(garbage=4, deflate=True, use_objstms=1)
        except TypeError:  # versioni meno recenti di PyMuPDF
            return doc.tobytes(garbage=4, deflate=True)
    finally:
        doc.close()


def process_pdfs(jobs, s, report=lambda kind, val: None):
    """
    Comprime i PDF. jobs: elenco di (pdf, cartella di destinazione).
    s: dpi, quality, color, target (bool), target_bytes, clean_meta, suffix.
    Restituisce (PDF salvati, errori, riepilogo, avvisi).
    """
    errors, warnings = [], []
    used = set()
    n = len(jobs)
    before = after = written = 0
    report("max", n)
    for i, (path, out_dir) in enumerate(jobs, 1):
        name = os.path.basename(path)
        report("status", "Compressione PDF %d di %d: %s" % (i, n, name))
        try:
            info = pdf_analyze(path)
            if info["encrypted"]:
                raise RuntimeError("il PDF è protetto da password")
            if s["target"]:
                limit = s["target_bytes"]
                memo = {}

                def fits(idx, path=path, memo=memo):
                    if idx not in memo:
                        dpi, q = PDF_LEVELS[idx]
                        memo[idx] = pdf_compress_bytes(path, dpi, q, s["color"], s["clean_meta"])
                    return len(memo[idx]) <= limit

                best = find_best(fits, 2, len(PDF_LEVELS) - 1)
                if best is None:
                    data = min(memo.values(), key=len)
                    warnings.append("%s: non si è potuto scendere sotto %s, ottenuti %s (il peso dipende "
                                    "soprattutto da testo o grafica, non dalle immagini)"
                                    % (name, fmt_size(limit), fmt_size(len(data))))
                else:
                    data = memo[best]
            else:
                data = pdf_compress_bytes(path, s["dpi"], s["quality"], s["color"], s["clean_meta"])
            if len(data) >= info["size"]:
                with open(path, "rb") as fh:
                    data = fh.read()
                warnings.append("%s: era già compresso al meglio, salvata una copia identica" % name)
            if info["signed"]:
                warnings.append("%s: conteneva una firma digitale, che nel file compresso non è più valida" % name)
            write_file(output_path(path, out_dir, s["suffix"], ".pdf", used), data)
            before += info["size"]
            after += len(data)
            written += 1
            report("out", out_dir)
        except Exception as e:
            errors.append("%s: %s" % (name, friendly_error(e)))
        report("progress", i)
    summary = ""
    if written:
        pct = math.floor(100 * (1 - after / before)) if before else 0
        summary = "da %s a %s, %d%% in meno" % (fmt_size(before), fmt_size(after), max(0, min(99, pct)))
    return written, errors, summary, warnings


# --- ricerca delle immagini

def is_image(path):
    return os.path.splitext(path)[1].lower() in IMAGE_EXT_SET


def scan_folder(folder, recursive, exclude=None):
    """Elenca le immagini di una cartella (ed eventualmente delle sottocartelle).
    exclude: cartella da saltare (di solito quella di destinazione)."""
    found = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs
                         if not (exclude and os.path.normcase(os.path.abspath(os.path.join(root, d))) == exclude))
        found += [os.path.join(root, f) for f in sorted(files, key=str.lower) if is_image(f)]
        if not recursive:
            break
    return found


def default_folder_output(folder):
    folder = os.path.abspath(folder)
    return folder.rstrip("\\/") + "_ridimensionate"


# --------------------------------------------------------------------------- interfaccia

class App:
    def __init__(self, root):
        self.root = root
        self.files = []
        self.last_out = None
        self.queue = queue.Queue()
        self.running = False
        self.help_win = None
        self.changelog_win = None
        self._checking = False
        self.cfg = load_config()
        self.check_on_start = tk.BooleanVar(value=self.cfg.get("check_on_start", True))

        root.title("%s %s" % (APP_NAME, APP_VERSION))
        root.resizable(False, False)
        pad = {"padx": 10, "pady": 4}
        style = ttk.Style(root)
        style.configure("Tab.TNotebook.Tab", padding=(16, 6), font=("Segoe UI", 10, "bold"))
        style.configure("Summary.TLabel", font=("Segoe UI", 10, "bold"), foreground="#1a4f8b")
        self.stats = {0: (0, 0), 1: (0, 0)}  # (numero immagini, peso complessivo) per scheda
        self.file_sizes = {}

        # --- menu
        menubar = tk.Menu(root)
        m_file = tk.Menu(menubar, tearoff=0)
        m_file.add_command(label="Aggiungi immagini...", command=lambda: (self.nb.select(0), self.add_files()))
        m_file.add_command(label="Scegli una cartella...", command=lambda: (self.nb.select(1), self.browse_folder()))
        if HAS_PDF:
            m_file.add_command(label="Aggiungi PDF...", command=lambda: (self.nb.select(2), self.add_pdf_dialog()))
        m_file.add_separator()
        m_file.add_command(label="Esci", command=root.destroy)
        menubar.add_cascade(label="File", menu=m_file)
        m_help = tk.Menu(menubar, tearoff=0)
        m_help.add_command(label="Guida", accelerator="F1", command=self.show_help)
        m_help.add_command(label="Novità delle versioni...", command=self.show_changelog)
        m_help.add_separator()
        m_help.add_command(label="Controlla aggiornamenti...", command=lambda: self.check_updates(manual=True))
        m_help.add_checkbutton(label="Controlla gli aggiornamenti all'avvio", variable=self.check_on_start,
                               command=self.toggle_check_on_start)
        m_help.add_separator()
        m_help.add_command(label="Informazioni su %s" % APP_NAME, command=self.show_about)
        menubar.add_cascade(label="?", menu=m_help)
        root.config(menu=menubar)
        root.bind("<F1>", lambda e: self.show_help())

        # --- schede
        self.nb = ttk.Notebook(root, style="Tab.TNotebook")
        self.nb.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        self.nb.bind("<<NotebookTabChanged>>", lambda e: self.on_tab_changed())

        # scheda 1: per immagine
        t1 = ttk.Frame(self.nb, padding=10)
        self.nb.add(t1, text="Ridimensiona per immagine")
        hint = "trascinale qui o usa i pulsanti" if HAS_DND else "usa i pulsanti a destra"
        ttk.Label(t1, text="Immagini da elaborare (%s):" % hint).grid(row=0, column=0, columnspan=2, sticky="w")
        lf = ttk.Frame(t1)
        lf.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        self.listbox = tk.Listbox(lf, width=72, height=7, selectmode=tk.EXTENDED, activestyle="none")
        sy = ttk.Scrollbar(lf, orient="vertical", command=self.listbox.yview)
        sx = ttk.Scrollbar(lf, orient="horizontal", command=self.listbox.xview)
        self.listbox.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self.listbox.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        self.listbox.bind("<Delete>", lambda e: self.remove_selected())
        bf = ttk.Frame(t1)
        bf.grid(row=1, column=1, sticky="n", padx=(10, 0), pady=(4, 0))
        for text, cmd in (("Aggiungi immagini...", self.add_files),
                          ("Rimuovi selezionate", self.remove_selected),
                          ("Svuota elenco", self.clear)):
            ttk.Button(bf, text=text, width=20, command=cmd).pack(pady=2, fill="x")
        self.files_info = tk.StringVar(value="Nessuna immagine nell'elenco.")
        ttk.Label(t1, textvariable=self.files_info, style="Summary.TLabel").grid(row=2, column=0, columnspan=2,
                                                                                 sticky="w", pady=(6, 0))

        # scheda 2: per cartella
        t2 = ttk.Frame(self.nb, padding=10)
        self.nb.add(t2, text="Ridimensiona per cartella")
        hint2 = " (o trascinala qui)" if HAS_DND else ""
        ttk.Label(t2, text="Cartella con le immagini da elaborare%s:" % hint2).grid(row=0, column=0, columnspan=2, sticky="w")
        self.folder = tk.StringVar()
        self.ent_folder = ttk.Entry(t2, textvariable=self.folder, width=74)
        self.ent_folder.grid(row=1, column=0, sticky="w", pady=(4, 6))
        self.ent_folder.bind("<FocusOut>", lambda e: self.update_folder_info())
        self.ent_folder.bind("<Return>", lambda e: self.update_folder_info())
        ttk.Button(t2, text="Sfoglia...", width=14, command=self.browse_folder).grid(row=1, column=1, sticky="w", padx=(8, 0))
        self.recursive = tk.BooleanVar(value=True)
        ttk.Checkbutton(t2, text="Includi le sottocartelle", variable=self.recursive,
                        command=self.update_folder_info).grid(row=2, column=0, sticky="w", pady=2)
        self.keep_tree = tk.BooleanVar(value=True)
        self.chk_tree = ttk.Checkbutton(t2, text="Mantieni la struttura delle sottocartelle nella destinazione",
                                        variable=self.keep_tree)
        self.chk_tree.grid(row=3, column=0, sticky="w", padx=(20, 0), pady=2)
        self.folder_info = tk.StringVar(value="Nessuna cartella scelta.")
        ttk.Label(t2, textvariable=self.folder_info, style="Summary.TLabel").grid(row=4, column=0, columnspan=2,
                                                                                  sticky="w", pady=(10, 0))

        # scheda 3: comprimi PDF
        self.pdf_files = []
        self.pdf_info = {}
        if HAS_PDF:
            t3 = ttk.Frame(self.nb, padding=10)
            self.nb.add(t3, text="Comprimi PDF")
            hint3 = "trascinali qui o usa i pulsanti" if HAS_DND else "usa i pulsanti a destra"
            ttk.Label(t3, text="PDF da comprimere (%s):" % hint3).grid(row=0, column=0, columnspan=2, sticky="w")
            pf = ttk.Frame(t3)
            pf.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
            self.pdf_list = tk.Listbox(pf, width=72, height=7, selectmode=tk.EXTENDED, activestyle="none")
            psy = ttk.Scrollbar(pf, orient="vertical", command=self.pdf_list.yview)
            psx = ttk.Scrollbar(pf, orient="horizontal", command=self.pdf_list.xview)
            self.pdf_list.configure(yscrollcommand=psy.set, xscrollcommand=psx.set)
            self.pdf_list.grid(row=0, column=0, sticky="nsew")
            psy.grid(row=0, column=1, sticky="ns")
            psx.grid(row=1, column=0, sticky="ew")
            self.pdf_list.bind("<Delete>", lambda e: self.remove_pdfs())
            pbf = ttk.Frame(t3)
            pbf.grid(row=1, column=1, sticky="n", padx=(10, 0), pady=(4, 0))
            for text, cmd in (("Aggiungi PDF...", self.add_pdf_dialog),
                              ("Rimuovi selezionati", self.remove_pdfs),
                              ("Svuota elenco", self.clear_pdfs)):
                ttk.Button(pbf, text=text, width=20, command=cmd).pack(pady=2, fill="x")
            self.pdf_summary = tk.StringVar(value="Nessun PDF nell'elenco.")
            ttk.Label(t3, textvariable=self.pdf_summary, style="Summary.TLabel", wraplength=740,
                      justify="left").grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        if HAS_DND:
            if HAS_PDF:
                self.pdf_list.drop_target_register(DND_FILES)
                self.pdf_list.dnd_bind("<<Drop>>", lambda e: self.add_pdfs(root.tk.splitlist(e.data)))
            self.listbox.drop_target_register(DND_FILES)
            self.listbox.dnd_bind("<<Drop>>", lambda e: self.add_paths(root.tk.splitlist(e.data)))
            for w in (t2, self.ent_folder):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self.on_folder_drop)

        # --- dimensioni in pixel
        gp = self.make_section(1, "Dimensioni in pixel", "pixel")
        self.resize = tk.BooleanVar(value=False)
        ttk.Radiobutton(gp, text="Mantieni le dimensioni originali", variable=self.resize, value=False,
                        command=self.update_state).grid(row=0, column=0, columnspan=6, sticky="w", **pad)
        ttk.Radiobutton(gp, text="Ridimensiona a:", variable=self.resize, value=True,
                        command=self.update_state).grid(row=1, column=0, sticky="w", **pad)

        self.width = tk.IntVar(value=1920)
        self.height = tk.IntVar(value=1080)
        self.px_widgets = []
        lbl = ttk.Label(gp, text="Larghezza:")
        lbl.grid(row=1, column=1, sticky="e", padx=(10, 4))
        sp_w = ttk.Spinbox(gp, from_=0, to=30000, increment=10, textvariable=self.width, width=7)
        sp_w.grid(row=1, column=2, sticky="w")
        lbl2 = ttk.Label(gp, text="Altezza:")
        lbl2.grid(row=1, column=3, sticky="e", padx=(14, 4))
        sp_h = ttk.Spinbox(gp, from_=0, to=30000, increment=10, textvariable=self.height, width=7)
        sp_h.grid(row=1, column=4, sticky="w")
        lbl3 = ttk.Label(gp, text="px  (0 = calcolata in automatico)")
        lbl3.grid(row=1, column=5, sticky="w", padx=8)

        self.modes = ["Adatta entro le dimensioni (mantiene le proporzioni)",
                      "Riempi e ritaglia al centro (dimensioni esatte)",
                      "Deforma alle dimensioni esatte"]
        self.mode = tk.StringVar(value=self.modes[0])
        lbl4 = ttk.Label(gp, text="Modalità:")
        lbl4.grid(row=2, column=1, sticky="e", padx=(10, 4), pady=(4, 8))
        self.cmb_mode = ttk.Combobox(gp, textvariable=self.mode, values=self.modes, state="readonly", width=46)
        self.cmb_mode.grid(row=2, column=2, columnspan=4, sticky="w", pady=(4, 8))
        self.cmb_mode.bind("<<ComboboxSelected>>", lambda e: self.update_state())
        self.no_upscale = tk.BooleanVar(value=True)
        self.chk_noup = ttk.Checkbutton(gp, text="Non ingrandire le immagini piccole", variable=self.no_upscale)
        self.chk_noup.grid(row=3, column=1, columnspan=5, sticky="w", padx=(10, 0), pady=(0, 8))
        self.px_widgets = [lbl, sp_w, lbl2, sp_h, lbl3, lbl4]

        # --- peso dei file
        gw = self.make_section(2, "Peso dei file", "peso")
        gwi = ttk.Frame(gw)
        gwi.pack(anchor="w")
        self.per_file = tk.BooleanVar(value=False)
        self.total = tk.BooleanVar(value=False)
        self.allow_shrink = tk.BooleanVar(value=False)
        self.max_kb = tk.IntVar(value=500)
        self.total_mb = tk.StringVar(value="20")

        ttk.Checkbutton(gwi, text="Peso massimo per ogni immagine:", variable=self.per_file,
                        command=self.update_state).grid(row=0, column=0, sticky="w", **pad)
        self.spin_kb = ttk.Spinbox(gwi, from_=5, to=1000000, increment=50, textvariable=self.max_kb, width=8)
        self.spin_kb.grid(row=0, column=1, sticky="w")
        ttk.Label(gwi, text="KB").grid(row=0, column=2, sticky="w", padx=6)

        ttk.Checkbutton(gwi, text="Peso massimo totale di tutte le immagini:", variable=self.total,
                        command=self.update_state).grid(row=1, column=0, sticky="w", **pad)
        self.spin_mb = ttk.Spinbox(gwi, from_=0.1, to=100000, increment=1, textvariable=self.total_mb, width=8)
        self.spin_mb.grid(row=1, column=1, sticky="w")
        self.mb_hint = tk.StringVar(value="MB  (somma di tutte le nuove immagini)")
        ttk.Label(gwi, textvariable=self.mb_hint).grid(row=1, column=2, sticky="w", padx=6)

        self.chk_shrink = ttk.Checkbutton(gwi, text="Se la qualità non basta, consenti di ridurre i pixel",
                                          variable=self.allow_shrink, command=self.update_state)
        self.chk_shrink.grid(row=2, column=0, columnspan=3, sticky="w", **pad)
        self.weight_hint = tk.StringVar()
        ttk.Label(gw, textvariable=self.weight_hint, foreground="#555", wraplength=760, justify="left").pack(
            anchor="w", padx=10, pady=(0, 8))

        # --- salvataggio
        go = self.make_section(3, "Salvataggio", "salva")
        self.fmt_pixel_values = [ORIGINAL] + [f[0] for f in OUT_FORMATS]
        self.fmt_weight_values = [f[0] for f in LOSSY_FORMATS]
        self.fmt_pixel = ORIGINAL
        self.fmt_weight = self.fmt_weight_values[0]
        self.format = tk.StringVar(value=ORIGINAL)
        ttk.Label(go, text="Formato:").grid(row=0, column=0, sticky="w", **pad)
        self.cmb_format = ttk.Combobox(go, textvariable=self.format, state="readonly", width=18)
        self.cmb_format.grid(row=0, column=1, sticky="w")
        self.cmb_format.bind("<<ComboboxSelected>>", lambda e: self.remember_format())
        self.quality = tk.IntVar(value=90)
        self.lbl_q = ttk.Label(go, text="Qualità:")
        self.lbl_q.grid(row=0, column=2, sticky="e", **pad)
        self.spin_q = ttk.Spinbox(go, from_=1, to=100, textvariable=self.quality, width=5)
        self.spin_q.grid(row=0, column=3, sticky="w")
        self.q_hint = tk.StringVar()
        self.lbl_qhint = ttk.Label(go, textvariable=self.q_hint, foreground="#555")
        self.lbl_qhint.grid(row=0, column=4, sticky="w", **pad)

        self.out_dir = tk.StringVar()
        ttk.Label(go, text="Cartella:").grid(row=1, column=0, sticky="w", **pad)
        of = ttk.Frame(go)
        of.grid(row=1, column=1, columnspan=5, sticky="w")
        ttk.Entry(of, textvariable=self.out_dir, width=62).pack(side="left")
        ttk.Button(of, text="Sfoglia...", command=self.browse_out).pack(side="left", padx=10)
        self.out_hint = tk.StringVar()
        ttk.Label(go, textvariable=self.out_hint, foreground="#555").grid(row=2, column=1, columnspan=5, sticky="w")

        self.suffix = tk.StringVar(value="_ridimensionata")
        ttk.Label(go, text="Suffisso:").grid(row=3, column=0, sticky="w", **pad)
        ttk.Entry(go, textvariable=self.suffix, width=20).grid(row=3, column=1, sticky="w")
        ttk.Label(go, text="(aggiunto al nome delle nuove immagini, può restare vuoto)", foreground="#555").grid(
            row=3, column=2, columnspan=4, sticky="w", **pad)

        # --- opzioni PDF (visibili solo nella scheda "Comprimi PDF")
        self.image_sections = [gp.master, gw.master, go.master]
        self.pdf_sections = []
        if HAS_PDF:
            gc = self.make_section(1, "Compressione PDF", "pdf")
            gci = ttk.Frame(gc)
            gci.pack(anchor="w")
            self.pdf_preset = tk.StringVar(value=PDF_PRESETS[0][0])
            ttk.Label(gci, text="Tipo di documento:").grid(row=0, column=0, sticky="w", **pad)
            cbp = ttk.Combobox(gci, textvariable=self.pdf_preset, values=[x[0] for x in PDF_PRESETS],
                               state="readonly", width=46)
            cbp.grid(row=0, column=1, columnspan=2, sticky="w")
            cbp.bind("<<ComboboxSelected>>", lambda e: self.apply_pdf_preset())

            self.pdf_color = tk.StringVar(value=PDF_COLORS[0][0])
            ttk.Label(gci, text="Colori:").grid(row=1, column=0, sticky="w", **pad)
            cbc = ttk.Combobox(gci, textvariable=self.pdf_color, values=[c[0] for c in PDF_COLORS],
                               state="readonly", width=16)
            cbc.grid(row=1, column=1, sticky="w")
            cbc.bind("<<ComboboxSelected>>", lambda e: self.pdf_custom())
            rq = ttk.Frame(gci)
            rq.grid(row=1, column=2, sticky="w")
            self.pdf_dpi = tk.IntVar(value=200)
            self.lbl_pdf_dpi = ttk.Label(rq, text="Risoluzione:")
            self.lbl_pdf_dpi.pack(side="left", padx=(16, 4))
            self.spin_pdf_dpi = ttk.Spinbox(rq, from_=50, to=600, increment=25, textvariable=self.pdf_dpi,
                                            width=6, command=self.pdf_custom)
            self.spin_pdf_dpi.pack(side="left")
            ttk.Label(rq, text="dpi").pack(side="left", padx=(4, 0))
            self.pdf_quality = tk.IntVar(value=75)
            self.lbl_pdf_q = ttk.Label(rq, text="Qualità:")
            self.lbl_pdf_q.pack(side="left", padx=(20, 4))
            self.spin_pdf_q = ttk.Spinbox(rq, from_=1, to=100, textvariable=self.pdf_quality, width=5,
                                          command=self.pdf_custom)
            self.spin_pdf_q.pack(side="left")
            for w in (self.spin_pdf_dpi, self.spin_pdf_q):
                w.bind("<KeyRelease>", lambda e: self.pdf_custom())

            self.pdf_target = tk.BooleanVar(value=False)
            ttk.Checkbutton(gci, text="Peso massimo per ogni PDF:", variable=self.pdf_target,
                            command=self.update_pdf_state).grid(row=2, column=0, columnspan=2, sticky="w", **pad)
            self.pdf_target_mb = tk.StringVar(value="2")
            rm = ttk.Frame(gci)
            rm.grid(row=2, column=2, sticky="w")
            self.spin_pdf_mb = ttk.Spinbox(rm, from_=0.1, to=10000, increment=0.5,
                                           textvariable=self.pdf_target_mb, width=6)
            self.spin_pdf_mb.pack(side="left", padx=(16, 0))
            ttk.Label(rm, text="MB  (risoluzione e qualità scelte in automatico)").pack(side="left", padx=(4, 0))
            self.pdf_clean = tk.BooleanVar(value=True)
            ttk.Checkbutton(gci, text="Rimuovi metadati e miniature (consigliato per i documenti personali)",
                            variable=self.pdf_clean).grid(row=3, column=0, columnspan=3, sticky="w", **pad)
            self.pdf_hint = tk.StringVar()
            ttk.Label(gc, textvariable=self.pdf_hint, foreground="#555", wraplength=760, justify="left").pack(
                anchor="w", padx=10, pady=(0, 8))

            gs2 = self.make_section(2, "Salvataggio PDF", "salva")
            self.pdf_out = tk.StringVar()
            ttk.Label(gs2, text="Cartella:").grid(row=0, column=0, sticky="w", **pad)
            of2 = ttk.Frame(gs2)
            of2.grid(row=0, column=1, sticky="w")
            ttk.Entry(of2, textvariable=self.pdf_out, width=62).pack(side="left")
            ttk.Button(of2, text="Sfoglia...", command=self.browse_pdf_out).pack(side="left", padx=10)
            ttk.Label(gs2, text="Se vuota, i PDF compressi vengono salvati accanto agli originali.",
                      foreground="#555").grid(row=1, column=1, sticky="w")
            self.pdf_suffix = tk.StringVar(value="_compresso")
            ttk.Label(gs2, text="Suffisso:").grid(row=2, column=0, sticky="w", **pad)
            sf2 = ttk.Frame(gs2)
            sf2.grid(row=2, column=1, sticky="w", pady=(0, 6))
            ttk.Entry(sf2, textvariable=self.pdf_suffix, width=20).pack(side="left")
            ttk.Label(sf2, text="(aggiunto al nome dei nuovi PDF; l'originale non viene mai modificato)",
                      foreground="#555").pack(side="left", padx=10)
            self.pdf_sections = [gc.master, gs2.master]
            self.apply_pdf_preset()

        # --- avanzamento e comandi
        self.progress = ttk.Progressbar(root, mode="determinate")
        self.progress.grid(row=4, column=0, sticky="ew", padx=10, pady=(10, 2))
        self.status = tk.StringVar(value="Pronto.")
        ttk.Label(root, textvariable=self.status).grid(row=5, column=0, sticky="w", padx=10)

        cf = ttk.Frame(root)
        cf.grid(row=6, column=0, sticky="w", padx=10, pady=(6, 12))
        self.btn_start = ttk.Button(cf, text="Ridimensiona", width=22, command=self.start)
        self.btn_start.pack(side="left")
        self.btn_open = ttk.Button(cf, text="Apri cartella di uscita", width=24, command=self.open_out, state="disabled")
        self.btn_open.pack(side="left", padx=8)

        self.update_state()
        self.on_tab_changed()
        if self.check_on_start.get():
            root.after(2000, lambda: self.check_updates(manual=False))

    # --- sezioni con barra laterale colorata
    def make_section(self, row, title, key):
        """Crea una sezione con la barra colorata a sinistra e restituisce il contenitore dei controlli."""
        outer = ttk.Frame(self.root)
        outer.grid(row=row, column=0, sticky="ew", padx=10, pady=4)
        tk.Frame(outer, bg=SECTION_COLORS[key], width=7).pack(side="left", fill="y", pady=(8, 0))
        lf = ttk.LabelFrame(outer, text=title)
        lf.pack(side="left", fill="both", expand=True)
        return lf

    # --- guida e informazioni
    def show_help(self):
        if self.help_win is not None and self.help_win.winfo_exists():
            self.help_win.deiconify()
            self.help_win.lift()
            return
        win, txt, buttons = make_text_window(self.root, "Guida - %s %s" % (APP_NAME, APP_VERSION), "720x620")
        self.help_win = win
        txt.insert("end", "%s %s\n" % (APP_NAME, APP_VERSION), "title")
        insert_markup(txt, HELP_TEXT + "\n# Estensioni riconosciute in questa versione")
        txt.insert("end", "  ".join(IMAGE_EXT) + "\n", "small")
        txt.configure(state="disabled")
        ttk.Button(buttons, text="Chiudi", command=win.destroy).pack(side="right")
        txt.focus_set()

    def show_changelog(self):
        if self.changelog_win is not None and self.changelog_win.winfo_exists():
            self.changelog_win.deiconify()
            self.changelog_win.lift()
            return
        win, txt, buttons = make_text_window(self.root, "Novità delle versioni - %s" % APP_NAME, "680x560")
        self.changelog_win = win
        txt.insert("end", "Novità delle versioni\n", "title")
        txt.insert("end", "Versione in uso: %s\n" % APP_VERSION, "small")
        insert_markup(txt, CHANGELOG)
        txt.configure(state="disabled")
        ttk.Button(buttons, text="Controlla aggiornamenti",
                   command=lambda: self.check_updates(manual=True)).pack(side="left")
        ttk.Button(buttons, text="Tutte le versioni su GitHub",
                   command=lambda: webbrowser.open(RELEASES_URL)).pack(side="left", padx=8)
        ttk.Button(buttons, text="Chiudi", command=win.destroy).pack(side="right")

    # --- aggiornamenti
    def toggle_check_on_start(self):
        self.cfg["check_on_start"] = bool(self.check_on_start.get())
        save_config(self.cfg)

    def check_updates(self, manual=True):
        """Controlla su GitHub se c'è una versione più recente (in un thread separato)."""
        if self._checking:
            return
        self._checking = True
        state = {}

        def work():
            try:
                state["newer"] = newer_releases()
            except Exception as e:
                state["error"] = e

        threading.Thread(target=work, daemon=True).start()
        if manual and not self.running:
            self.status.set("Controllo degli aggiornamenti in corso...")

        def wait():
            if "newer" not in state and "error" not in state:
                self.root.after(200, wait)
                return
            self._checking = False
            if manual and not self.running:
                self.status.set("Pronto.")
            if "error" in state:
                if manual:
                    if isinstance(state["error"], NoReleases):
                        messagebox.showinfo(APP_NAME, "Su GitHub non è ancora stata pubblicata nessuna versione.")
                    elif messagebox.askyesno(APP_NAME, "Non è stato possibile controllare gli aggiornamenti.\n\n%s\n\n"
                                                       "Vuoi aprire la pagina delle versioni nel browser per "
                                                       "controllare a mano?" % describe_net_error(state["error"])):
                        webbrowser.open(RELEASES_URL)
                return
            newer = state["newer"]
            if not newer:
                if manual:
                    messagebox.showinfo(APP_NAME, "Hai già la versione più recente (%s)." % APP_VERSION)
                return
            if not manual and parse_version(self.cfg.get("skip_version", "")) >= newer[0]["version"]:
                return  # l'utente ha scelto di saltare questa versione
            self.show_update_dialog(newer)

        wait()

    def show_update_dialog(self, newer):
        latest = newer[0]
        win, txt, buttons = make_text_window(self.root, "Aggiornamento disponibile - %s" % APP_NAME, "640x480")
        win.transient(self.root)
        txt.insert("end", "È disponibile la versione %s\n" % latest["label"], "title")
        txt.insert("end", "Tu hai la versione %s. Ecco le novità:\n" % APP_VERSION, "small")
        for rel in newer:
            notes = rel["notes"].strip() or "Le novità di questa versione sono descritte nella sua pagina su GitHub."
            if not notes.lstrip().startswith("#"):
                notes = "## %s%s\n%s" % (rel["label"], " - " + rel["date"] if rel["date"] else "", notes)
            insert_markup(txt, notes)
        txt.configure(state="disabled")

        can_install = getattr(sys, "frozen", False) and sys.platform == "win32" and latest["exe"]
        if can_install:
            ttk.Button(buttons, text="Scarica e installa",
                       command=lambda: (win.destroy(), self.install_update(latest))).pack(side="left")
        else:
            ttk.Button(buttons, text="Apri la pagina di download",
                       command=lambda: (win.destroy(), webbrowser.open(latest["url"]))).pack(side="left")

        def skip():
            self.cfg["skip_version"] = latest["label"]
            save_config(self.cfg)
            win.destroy()

        ttk.Button(buttons, text="Più tardi", command=win.destroy).pack(side="right")
        ttk.Button(buttons, text="Salta questa versione", command=skip).pack(side="right", padx=8)

    def install_update(self, rel):
        """Scarica il nuovo eseguibile, controlla l'impronta e lo installa al riavvio."""
        if self.running:
            messagebox.showinfo(APP_NAME, "Attendi la fine dell'elaborazione in corso, poi riprova "
                                          "da \"?\" > \"Controlla aggiornamenti\".")
            return
        exe = os.path.abspath(sys.executable)
        folder = os.path.dirname(exe)
        in_place = can_write(folder)
        if not in_place:  # cartella protetta (es. Programmi): si scarica nella cartella Download
            folder = os.path.join(os.path.expanduser("~"), "Downloads")
            os.makedirs(folder, exist_ok=True)
        new_exe = os.path.join(folder, "RidimensionaImmagini_%s.exe" % rel["label"].replace(" ", "_"))
        part = new_exe + ".download"

        win = tk.Toplevel(self.root)
        win.title("Aggiornamento - %s" % APP_NAME)
        win.resizable(False, False)
        win.transient(self.root)
        body = ttk.Frame(win, padding=20)
        body.pack()
        msg = tk.StringVar(value="Download della versione %s in corso..." % rel["label"])
        ttk.Label(body, textvariable=msg, width=60).pack(anchor="w")
        bar = ttk.Progressbar(body, mode="determinate", length=420, maximum=max(1, rel["exe_size"]))
        bar.pack(pady=10)
        win.protocol("WM_DELETE_WINDOW", lambda: None)  # non si chiude durante il download
        state = {"done": 0}

        def work():
            try:
                digest = download_file(rel["exe"], part, lambda d, tot: state.update(done=d, total=tot))
                if rel["sha"]:
                    with _http_open(rel["sha"], accept="application/octet-stream") as r:
                        expected = r.read().decode("utf-8", "replace").split()[0].strip().lower()
                    if expected != digest:
                        raise RuntimeError("il file scaricato non corrisponde a quello pubblicato (impronta diversa)")
                os.replace(part, new_exe)
                state["ok"] = True
            except Exception as e:
                net = isinstance(e, (urllib.error.URLError, OSError)) and not isinstance(e, FileNotFoundError)
                state["error"] = describe_net_error(e).rstrip(".") if net else friendly_error(e)
                try:
                    os.remove(part)
                except OSError:
                    pass

        threading.Thread(target=work, daemon=True).start()

        def wait():
            bar.configure(maximum=max(1, state.get("total") or rel["exe_size"] or 1), value=state["done"])
            msg.set("Download della versione %s: %s" % (rel["label"], fmt_size(state["done"])))
            if "ok" not in state and "error" not in state:
                self.root.after(150, wait)
                return
            win.destroy()
            if "error" in state:
                messagebox.showwarning(APP_NAME, "Aggiornamento non riuscito: %s.\n\nPuoi scaricare la nuova "
                                                 "versione dalla pagina che si aprirà ora." % state["error"])
                webbrowser.open(rel["url"])
                return
            if not in_place:
                messagebox.showinfo(APP_NAME, "La nuova versione è stata scaricata nella cartella Download:\n%s\n\n"
                                              "La cartella in cui si trova il programma è protetta: chiudi il "
                                              "programma e sostituisci a mano il vecchio file con quello nuovo."
                                    % new_exe)
                subprocess.Popen(["explorer", "/select,", new_exe])
                return
            if messagebox.askokcancel(APP_NAME, "Versione %s scaricata.\n\nIl programma ora si chiude, si "
                                                "aggiorna e si riapre da solo." % rel["label"]):
                launch_replacement(new_exe, exe)
                self.root.destroy()

        wait()

    def show_about(self):
        win = tk.Toplevel(self.root)
        win.title("Informazioni su %s" % APP_NAME)
        win.resizable(False, False)
        win.transient(self.root)

        body = ttk.Frame(win, padding=(30, 20, 30, 14))
        body.pack()
        ttk.Label(body, text=APP_NAME, font=("Segoe UI", 15, "bold")).pack()
        ttk.Label(body, text="Versione %s" % APP_VERSION).pack(pady=(2, 12))
        ttk.Label(body, text="Ridimensionamento di immagini in serie,\nper dimensioni in pixel o per peso,\n"
                             "e compressione di file PDF.",
                  justify="center").pack()
        ttk.Separator(body).pack(fill="x", pady=12)
        ttk.Label(body, text=AUTHOR_NAME, font=("Segoe UI", 10, "bold")).pack()
        gh = tk.Label(body, text="Pagina del progetto su GitHub", fg="#1a5fb4", cursor="hand2",
                      font=("Segoe UI", 10, "underline"))
        gh.pack(pady=(6, 0))
        gh.bind("<Button-1>", lambda e: webbrowser.open(GITHUB_URL))
        issues = tk.Label(body, text="Segnala un problema o un suggerimento", fg="#1a5fb4", cursor="hand2",
                          font=("Segoe UI", 10, "underline"))
        issues.pack(pady=(2, 0))
        issues.bind("<Button-1>", lambda e: webbrowser.open(GITHUB_URL + "/issues/new"))
        bf = ttk.Frame(body)
        bf.pack(pady=(16, 0))
        ttk.Button(bf, text="Controlla aggiornamenti", command=lambda: (win.destroy(), self.check_updates(True))).pack(side="left")
        ttk.Button(bf, text="OK", width=10, command=win.destroy).pack(side="left", padx=(8, 0))

        win.bind("<Escape>", lambda e: win.destroy())
        win.bind("<Return>", lambda e: win.destroy())
        win.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - win.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - win.winfo_height()) // 3
        win.geometry("+%d+%d" % (max(0, x), max(0, y)))
        win.grab_set()
        win.focus_set()

    # --- schede
    def tab_index(self):
        return self.nb.index(self.nb.select())

    def by_folder(self):
        return self.tab_index() == 1

    def is_pdf_tab(self):
        return HAS_PDF and self.tab_index() == 2

    def update_summary_hint(self):
        """Ricorda il peso attuale accanto al campo del peso totale."""
        n, size = self.stats[1 if self.by_folder() else 0]
        if n:
            self.mb_hint.set("MB  (somma di tutte le nuove immagini; oggi pesano %s)" % fmt_size(size))
        else:
            self.mb_hint.set("MB  (somma di tutte le nuove immagini)")

    def on_tab_changed(self):
        pdf = self.is_pdf_tab()
        for f in self.image_sections:
            if pdf:
                f.grid_remove()
            else:
                f.grid()
        for f in self.pdf_sections:
            if pdf:
                f.grid()
            else:
                f.grid_remove()
        self.btn_start.configure(text="Comprimi PDF" if pdf else "Ridimensiona")
        if pdf:
            return
        self.update_summary_hint()
        if self.by_folder():
            self.out_hint.set("Se vuota, viene creata la cartella '<nome cartella>_ridimensionate' "
                              "accanto alla cartella scelta.")
        else:
            self.out_hint.set("Se vuota, le immagini vanno nella sottocartella 'ridimensionate' "
                              "accanto alle immagini originali.")

    # --- scheda "Comprimi PDF"
    def add_pdfs(self, paths):
        for p in paths:
            if os.path.isdir(p):
                found = [os.path.join(p, f) for f in sorted(os.listdir(p), key=str.lower) if f.lower().endswith(".pdf")]
            elif p.lower().endswith(".pdf"):
                found = [p]
            else:
                found = []
            for f in found:
                f = os.path.normpath(f)
                if f not in self.pdf_files and os.path.isfile(f):
                    self.pdf_files.append(f)
                    self.pdf_list.insert("end", f)
                    try:
                        self.pdf_info[f] = pdf_analyze(f)
                    except Exception:
                        self.pdf_info[f] = None
        self.update_pdf_summary()

    def add_pdf_dialog(self):
        names = filedialog.askopenfilenames(title="Scegli i PDF", filetypes=[("PDF", "*.pdf"), ("Tutti i file", "*.*")])
        self.add_pdfs(names)

    def remove_pdfs(self):
        for i in reversed(self.pdf_list.curselection()):
            self.pdf_list.delete(i)
            del self.pdf_files[i]
        self.update_pdf_summary()

    def clear_pdfs(self):
        self.pdf_list.delete(0, "end")
        self.pdf_files.clear()
        self.update_pdf_summary()

    def update_pdf_summary(self):
        n = len(self.pdf_files)
        if n == 0:
            self.pdf_summary.set("Nessun PDF nell'elenco.")
            return
        infos = [self.pdf_info.get(f) for f in self.pdf_files]
        size = sum(i["size"] if i else os.path.getsize(f) for f, i in zip(self.pdf_files, infos) if os.path.exists(f))
        readable = [i for i in infos if i and not i["encrypted"]]
        img = sum(i["images"] for i in readable)
        img_base = sum(i["size"] for i in readable)
        parts = ["1 PDF nell'elenco" if n == 1 else "%d PDF nell'elenco" % n,
                 "peso complessivo attuale: %s" % fmt_size(size)]
        if img_base:
            parts.append("immagini: %d%% del peso" % round(100 * img / img_base))
        text = "  ·  ".join(parts)
        notes = []
        bad = sum(1 for i in infos if i is None)
        enc = sum(1 for i in infos if i and i["encrypted"])
        sig = sum(1 for i in infos if i and i["signed"])
        if enc:
            notes.append("%d protett%s da password (non elaborabil%s)" % (enc, "o" if enc == 1 else "i", "e" if enc == 1 else "i"))
        if sig:
            notes.append("%d con firma digitale" % sig)
        if bad:
            notes.append("%d non leggibil%s" % (bad, "e" if bad == 1 else "i"))
        if notes:
            text += "\nAttenzione: " + "; ".join(notes) + "."
        if img_base and img / img_base < 0.5:
            text += "\nLe immagini occupano meno della metà del peso: la compressione potrà ridurlo solo in parte."
        self.pdf_summary.set(text)

    def browse_pdf_out(self):
        d = filedialog.askdirectory(title="Cartella in cui salvare i PDF compressi")
        if d:
            self.pdf_out.set(os.path.normpath(d))

    def pdf_color_code(self):
        return next(c[1] for c in PDF_COLORS if c[0] == self.pdf_color.get())

    def apply_pdf_preset(self):
        for label, dpi, q, color in PDF_PRESETS:
            if label == self.pdf_preset.get() and dpi:
                self.pdf_dpi.set(dpi)
                self.pdf_quality.set(q)
                self.pdf_color.set(next(c[0] for c in PDF_COLORS if c[1] == color))
        self.update_pdf_state()

    def pdf_custom(self):
        """Se colori, risoluzione o qualità non corrispondono più a un tipo di documento, diventa "Personalizzato"."""
        try:
            dpi, q = int(self.pdf_dpi.get()), int(self.pdf_quality.get())
        except (tk.TclError, ValueError):
            dpi = q = None
        color = self.pdf_color_code()
        self.pdf_preset.set(next((x[0] for x in PDF_PRESETS if x[1] == dpi and x[2] == q and x[3] == color),
                                 PDF_PRESETS[-1][0]))
        self.update_pdf_state()

    def update_pdf_state(self):
        target = self.pdf_target.get()
        color = self.pdf_color_code()
        self.spin_pdf_mb.configure(state="normal" if target else "disabled")
        for w in (self.lbl_pdf_dpi, self.spin_pdf_dpi):
            w.configure(state="disabled" if target else "normal")
        for w in (self.lbl_pdf_q, self.spin_pdf_q):
            w.configure(state="disabled" if target or color == "bw" else "normal")
        hints = {
            PDF_PRESETS[0][0]: "Adatto a carte d'identità, patenti, passaporti e foto di documenti: "
                               "mantiene i colori e una buona leggibilità.",
            PDF_PRESETS[1][0]: "Adatto a lettere, contratti e moduli scansionati: elimina il colore, spesso inutile, "
                               "e riduce molto il peso.",
            PDF_PRESETS[2][0]: "Solo per pagine di testo nero su fondo chiaro: file minimi e testo nitido. Non adatto "
                               "a foto e documenti d'identità, che diventerebbero scuri o illeggibili.",
            PDF_PRESETS[3][0]: "Imposta liberamente colori, risoluzione e qualità.",
        }
        hint = hints.get(self.pdf_preset.get(), "")
        if target:
            hint += " Con il peso massimo, risoluzione e qualità vengono scelte in automatico (da 300 a 50 dpi)."
        self.pdf_hint.set(hint)

    # --- scheda "per immagine"
    def update_files_info(self):
        n = len(self.files)
        size = sum(self.file_sizes.get(f, 0) for f in self.files)
        self.stats[0] = (n, size)
        if n == 0:
            self.files_info.set("Nessuna immagine nell'elenco.")
        else:
            self.files_info.set("%s nell'elenco  ·  peso complessivo attuale: %s" % (
                "1 immagine" if n == 1 else "%d immagini" % n, fmt_size(size)))
        self.update_summary_hint()

    def add_paths(self, paths):
        for p in paths:
            if os.path.isdir(p):
                found = scan_folder(p, recursive=False)
            elif is_image(p):
                found = [p]
            else:
                found = []
            for f in found:
                f = os.path.normpath(f)
                if f not in self.files:
                    self.files.append(f)
                    self.listbox.insert("end", f)
                    try:
                        self.file_sizes[f] = os.path.getsize(f)
                    except OSError:
                        self.file_sizes[f] = 0
        self.update_files_info()

    def add_files(self):
        patterns = " ".join("*" + e for e in IMAGE_EXT)
        types = [("Tutte le immagini", patterns),
                 ("JPEG", "*.jpg *.jpeg *.jpe *.jfif"),
                 ("PNG", "*.png"),
                 ("HEIC/HEIF (iPhone)", "*.heic *.heif *.hif"),
                 ("WebP", "*.webp"),
                 ("AVIF", "*.avif"),
                 ("TIFF", "*.tif *.tiff"),
                 ("Tutti i file", "*.*")]
        names = filedialog.askopenfilenames(title="Scegli le immagini", filetypes=types)
        self.add_paths(names)

    def remove_selected(self):
        for i in reversed(self.listbox.curselection()):
            self.listbox.delete(i)
            del self.files[i]
        self.update_files_info()

    def clear(self):
        self.listbox.delete(0, "end")
        self.files.clear()
        self.update_files_info()

    # --- scheda "per cartella"
    def browse_folder(self):
        d = filedialog.askdirectory(title="Scegli la cartella con le immagini")
        if d:
            self.folder.set(os.path.normpath(d))
            self.update_folder_info()

    def on_folder_drop(self, event):
        for p in self.root.tk.splitlist(event.data):
            if os.path.isdir(p):
                self.folder.set(os.path.normpath(p))
                self.update_folder_info()
                return
        messagebox.showinfo(APP_NAME, "In questa scheda trascina una cartella.\n"
                                      "Per singole immagini usa la scheda \"Ridimensiona per immagine\".")

    def update_folder_info(self):
        self.chk_tree.configure(state="normal" if self.recursive.get() else "disabled")
        folder = self.folder.get().strip()
        self.stats[1] = (0, 0)
        self.update_summary_hint()
        if not folder:
            self.folder_info.set("Nessuna cartella scelta.")
            return
        if not os.path.isdir(folder):
            self.folder_info.set("La cartella indicata non esiste.")
            return
        files = scan_folder(folder, self.recursive.get(), self.folder_exclude(folder))
        size = 0
        for f in files:
            try:
                size += os.path.getsize(f)
            except OSError:
                pass
        n = len(files)
        self.stats[1] = (n, size)
        self.update_summary_hint()
        if n == 0:
            self.folder_info.set("Nessuna immagine trovata.")
        else:
            where = " (sottocartelle comprese)" if self.recursive.get() else ""
            self.folder_info.set("%s%s  ·  peso complessivo attuale: %s" % (
                "Trovata 1 immagine" if n == 1 else "Trovate %d immagini" % n, where, fmt_size(size)))

    def folder_exclude(self, folder):
        dest = self.out_dir.get().strip() or default_folder_output(folder)
        return os.path.normcase(os.path.abspath(dest))

    # --- impostazioni
    def browse_out(self):
        d = filedialog.askdirectory(title="Cartella in cui salvare le immagini ridimensionate")
        if d:
            self.out_dir.set(os.path.normpath(d))

    def open_out(self):
        if self.last_out and os.path.isdir(self.last_out):
            if sys.platform == "win32":
                os.startfile(self.last_out)
            else:
                subprocess.Popen(["xdg-open", self.last_out])

    def limited(self):
        return self.per_file.get() or self.total.get()

    def remember_format(self):
        if self.limited():
            self.fmt_weight = self.format.get()
        else:
            self.fmt_pixel = self.format.get()
        self.update_state()

    def update_state(self):
        resize = self.resize.get()
        for w in self.px_widgets:
            w.configure(state="normal" if resize else "disabled")
        self.cmb_mode.configure(state="readonly" if resize else "disabled")
        fit = self.mode.get() == self.modes[0]
        self.chk_noup.configure(state="normal" if resize and fit else "disabled")

        per_file, total = self.per_file.get(), self.total.get()
        self.spin_kb.configure(state="normal" if per_file else "disabled")
        self.spin_mb.configure(state="normal" if total else "disabled")
        limited = per_file or total
        self.chk_shrink.configure(state="normal" if limited else "disabled")

        if not limited:
            hint = ("Nessun limite di peso: il peso dei file dipende dalle dimensioni e dal formato "
                    "(e dalla qualità) scelti nella sezione Salvataggio.")
        elif self.allow_shrink.get():
            hint = ("La qualità viene scelta in automatico e scende fino a %d; se non basta, "
                    "vengono ridotti anche i pixel." % MIN_QUALITY_SHRINK)
        else:
            hint = ("La qualità viene scelta in automatico (minimo %d) senza toccare i pixel. "
                    "Se il limite non si può rispettare, il programma avvisa." % QUALITY_LOW[-1])
        self.weight_hint.set(hint)

        # La qualità si mostra solo quando ha effetto: senza limiti di peso e con un formato compresso.
        if limited:
            self.cmb_format.configure(values=self.fmt_weight_values)
            self.format.set(self.fmt_weight)
            show_q = False
        else:
            self.cmb_format.configure(values=self.fmt_pixel_values)
            self.format.set(self.fmt_pixel)
            show_q = self.fmt_pixel == ORIGINAL or self.fmt_pixel in {f[0] for f in LOSSY_FORMATS}
            self.q_hint.set("(vale per le immagini JPEG, WebP, AVIF e HEIC)" if self.fmt_pixel == ORIGINAL
                            else "(da 1 a 100; consigliata tra 80 e 90)")
        for w in (self.lbl_q, self.spin_q, self.lbl_qhint):
            if show_q:
                w.grid()
            else:
                w.grid_remove()

    # --- elaborazione
    def build_jobs(self):
        """Restituisce l'elenco (immagine, cartella di destinazione) oppure None se manca qualcosa."""
        user_out = self.out_dir.get().strip()
        if not self.by_folder():
            if not self.files:
                messagebox.showinfo(APP_NAME, "Aggiungi almeno un'immagine all'elenco.")
                return None
            return [(f, user_out or os.path.join(os.path.dirname(f), "ridimensionate")) for f in self.files]

        folder = self.folder.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showinfo(APP_NAME, "Scegli una cartella esistente.")
            return None
        folder = os.path.abspath(folder)
        base = os.path.abspath(user_out) if user_out else default_folder_output(folder)
        files = scan_folder(folder, self.recursive.get(), os.path.normcase(base))
        if not files:
            messagebox.showinfo(APP_NAME, "Nella cartella scelta non ci sono immagini da elaborare.")
            return None
        keep = self.recursive.get() and self.keep_tree.get()
        jobs = []
        for f in files:
            rel = os.path.relpath(os.path.dirname(f), folder)
            jobs.append((f, os.path.join(base, rel) if keep and rel != "." else base))
        return jobs

    def start(self):
        if self.running:
            return
        if self.is_pdf_tab():
            return self.start_pdf()
        self.run_kind = "img"
        try:
            tw, th = int(self.width.get()), int(self.height.get())
            max_kb, quality = int(self.max_kb.get()), int(self.quality.get())
            total_mb = float(self.total_mb.get().strip().replace(",", "."))
        except (tk.TclError, ValueError):
            messagebox.showwarning(APP_NAME, "Controlla i valori numerici inseriti.")
            return
        if min(tw, th) < 0 or max_kb < 1 or not 1 <= quality <= 100 or total_mb <= 0:
            messagebox.showwarning(APP_NAME, "Controlla i valori numerici inseriti.")
            return
        mode = ("fit", "crop", "stretch")[self.modes.index(self.mode.get())]
        if self.resize.get():
            if mode != "fit" and (tw == 0 or th == 0):
                messagebox.showwarning(APP_NAME, "Con questa modalità servono sia la larghezza sia l'altezza.")
                return
            if tw == 0 and th == 0:
                messagebox.showwarning(APP_NAME, "Indica almeno la larghezza o l'altezza.")
                return

        jobs = self.build_jobs()
        if not jobs:
            return

        label_to_fmt = {f[0]: f[1] for f in OUT_FORMATS}
        settings = {
            "resize": self.resize.get(), "tw": tw, "th": th, "mode": mode, "no_upscale": self.no_upscale.get(),
            "per_file": self.per_file.get(), "max_kb": max_kb,
            "total": self.total.get(), "total_bytes": int(total_mb * 1024 * 1024),
            "allow_shrink": self.allow_shrink.get(),
            "out_fmt": ORIGINAL if self.fmt_pixel == ORIGINAL else label_to_fmt[self.fmt_pixel],
            "weight_fmt": label_to_fmt[self.fmt_weight],
            "quality": quality, "suffix": self.suffix.get(),
        }
        self.running = True
        self.btn_start.configure(state="disabled")
        self.btn_open.configure(state="disabled")
        self.progress.configure(maximum=len(jobs), value=0)
        threading.Thread(target=self.worker, args=(jobs, settings), daemon=True).start()
        self.root.after(100, self.poll)

    def start_pdf(self):
        if not self.pdf_files:
            messagebox.showinfo(APP_NAME, "Aggiungi almeno un PDF all'elenco.")
            return
        try:
            dpi, quality = int(self.pdf_dpi.get()), int(self.pdf_quality.get())
            target_mb = float(self.pdf_target_mb.get().strip().replace(",", "."))
        except (tk.TclError, ValueError):
            messagebox.showwarning(APP_NAME, "Controlla i valori numerici inseriti.")
            return
        if not 30 <= dpi <= 1200 or not 1 <= quality <= 100 or target_mb <= 0:
            messagebox.showwarning(APP_NAME, "Controlla i valori numerici inseriti.")
            return
        out = self.pdf_out.get().strip()
        jobs = [(f, out or os.path.dirname(f)) for f in self.pdf_files]
        settings = {
            "dpi": dpi, "quality": quality, "color": self.pdf_color_code(),
            "target": self.pdf_target.get(), "target_bytes": int(target_mb * 1024 * 1024),
            "clean_meta": self.pdf_clean.get(), "suffix": self.pdf_suffix.get(),
        }
        self.run_kind = "pdf"
        self.running = True
        self.btn_start.configure(state="disabled")
        self.btn_open.configure(state="disabled")
        self.progress.configure(maximum=len(jobs), value=0)
        threading.Thread(target=self.worker_pdf, args=(jobs, settings), daemon=True).start()
        self.root.after(100, self.poll)

    def worker_pdf(self, jobs, settings):
        try:
            ok, errors, info, warnings = process_pdfs(jobs, settings, lambda k, v: self.queue.put((k, v)))
        except Exception as e:
            ok, errors, info, warnings = 0, [friendly_error(e)], "", []
        self.queue.put(("done", (ok, errors, info, None, warnings)))

    def worker(self, jobs, settings):
        try:
            result = process_all(jobs, settings, lambda k, v: self.queue.put((k, v)))
        except Exception as e:
            result = (0, ["Nessuna immagine salvata. %s" % e], "", None)
        self.queue.put(("done", result))


    def poll(self):
        try:
            while True:
                kind, val = self.queue.get_nowait()
                if kind == "status":
                    self.status.set(val)
                elif kind == "progress":
                    self.progress.configure(value=val)
                elif kind == "max":
                    self.progress.configure(maximum=max(1, val), value=0)
                elif kind == "out":
                    self.last_out = val
                elif kind == "done":
                    self.finish(*val)
                    return
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def finish(self, ok, errors, info="", min_quality=None, warnings=None):
        self.running = False
        self.btn_start.configure(state="normal")
        if self.last_out:
            self.btn_open.configure(state="normal")
        pdf = getattr(self, "run_kind", "img") == "pdf"
        if pdf:
            saved = "1 PDF salvato" if ok == 1 else "%d PDF salvati" % ok
        else:
            saved = "1 immagine salvata" if ok == 1 else "%d immagini salvate" % ok
        if info:
            saved += " (%s)" % info
        n_err = "1 errore" if len(errors) == 1 else "%d errori" % len(errors)
        self.status.set("Completato: %s, %s." % (saved, n_err))
        if errors and ok == 0 and len(errors) == 1 and errors[0].startswith("Nessuna immagine salvata"):
            self.status.set("Nessuna immagine salvata.")
            messagebox.showwarning(APP_NAME, errors[0])
        elif errors:
            msg = ("Alcuni PDF non sono stati elaborati:" if pdf else "Alcune immagini non sono state elaborate:")
            msg += "\n\n" + "\n".join(errors[:15])
            if len(errors) > 15:
                msg += ("\n... e altri %d" if pdf else "\n... e altre %d") % (len(errors) - 15)
            messagebox.showwarning(APP_NAME, msg)
        if warnings:
            messagebox.showinfo(APP_NAME, "Da sapere:\n\n" + "\n\n".join(warnings[:10]))
        if ok and min_quality is not None and min_quality < LOW_QUALITY_WARNING:
            messagebox.showwarning(APP_NAME, (
                "Attenzione: per rispettare il peso indicato, alcune immagini sono state salvate con "
                "qualità %d, inferiore a %d, e potrebbero apparire visibilmente rovinate.\n\n"
                "Per un risultato migliore puoi aumentare il limite di peso, ridurre i pixel "
                "(\"Ridimensiona a\") oppure attivare \"consenti di ridurre i pixel\"."
            ) % (min_quality, LOW_QUALITY_WARNING))
        if self.by_folder():
            self.update_folder_info()


def run_selftest(log_path):
    """Prova automatica dell'eseguibile (la usa GitHub dopo averlo creato):
    ridimensionamento, limiti di peso, tutti i formati di uscita e compressione PDF."""
    import shutil
    import traceback
    lines, ok = [], [True]

    def check(name, cond):
        ok[0] = ok[0] and bool(cond)
        lines.append(("OK      " if cond else "ERRORE  ") + name)

    tmp = tempfile.mkdtemp(prefix="ri_prova_")
    try:
        src, out = os.path.join(tmp, "in"), os.path.join(tmp, "out")
        os.makedirs(src)
        img = Image.effect_noise((1600, 1200), 40).convert("RGB")
        img.save(os.path.join(src, "foto.jpg"), quality=95)
        img.save(os.path.join(src, "foto.png"))
        try:
            img.save(os.path.join(src, "foto.heic"), quality=90)
        except Exception as e:
            check("scrittura HEIC: %s" % e, False)
        jobs = [(os.path.join(src, f), out) for f in sorted(os.listdir(src))]
        base = dict(resize=True, tw=800, th=800, mode="fit", no_upscale=True, per_file=False, max_kb=100,
                    total=False, total_bytes=0, allow_shrink=True, out_fmt=ORIGINAL, weight_fmt="JPEG",
                    quality=85, suffix="_a")
        n, err, _, _ = process_all(jobs, base)
        check("ridimensionamento in pixel: %d di %d %s" % (n, len(jobs), err or ""), n == len(jobs) and not err)
        n, err, info, _ = process_all(jobs, dict(base, total=True, total_bytes=150 * 1024, suffix="_b"))
        tot = sum(os.path.getsize(os.path.join(out, f)) for f in os.listdir(out) if "_b" in f)
        check("peso totale 150 KB: %s" % info, n == len(jobs) and not err and tot <= 150 * 1024)
        small = img.resize((64, 48))
        for label, fmt, _ext, _q, _a in OUT_FORMATS:
            try:
                check("formato %s" % label, len(encode(small, fmt, 80)) > 0)
            except Exception as e:
                check("formato %s: %s" % (label, e), False)
        if HAS_PDF:
            pdf = os.path.join(src, "documento.pdf")
            doc = pymupdf.open()
            page = doc.new_page()
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=95)
            page.insert_image(page.rect, stream=buf.getvalue())
            page.insert_text((72, 72), "Prova")
            doc.save(pdf)
            doc.close()
            n, err, info, _ = process_pdfs([(pdf, out)], dict(dpi=100, quality=60, color="color", target=False,
                                                              target_bytes=0, clean_meta=True, suffix="_c"))
            res = os.path.join(out, "documento_c.pdf")
            check("compressione PDF: %s" % info,
                  n == 1 and not err and os.path.getsize(res) < os.path.getsize(pdf))
        else:
            check("libreria PDF presente", False)
    except Exception:
        check("errore imprevisto:\n" + traceback.format_exc(), False)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    lines.append("TUTTO OK" if ok[0] else "PROBLEMI")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("%s %s\n" % (APP_NAME, APP_VERSION) + "\n".join(lines) + "\n")
    return 0 if ok[0] else 1


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--autotest":
        sys.exit(run_selftest(sys.argv[2]))
    if sys.platform == "win32":
        try:  # testo nitido sugli schermi ad alta risoluzione
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
