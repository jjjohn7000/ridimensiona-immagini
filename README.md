# Ridimensiona Immagini

Programma per Windows che ridimensiona immagini in serie e comprime i file PDF.
Tutto avviene sul computer: nessun file viene inviato su Internet.

## Scaricare il programma

Vai alla pagina **[Versioni (Releases)](https://github.com/jjjohn7000/ridimensiona-immagini/releases/latest)**,
scarica `RidimensionaImmagini.exe` dalla sezione *Assets* e avvialo: non serve installare nulla.

Il programma controlla da solo, all'avvio, se è disponibile una versione più recente e la installa con un clic.

> Al primo avvio Windows potrebbe mostrare l'avviso *"Windows ha protetto il PC"*, perché il programma non è
> firmato digitalmente: scegli **Ulteriori informazioni → Esegui comunque**.

## Cosa fa

- **Ridimensiona per immagine o per cartella** (anche con le sottocartelle), mantenendo la struttura delle cartelle.
- **Dimensioni in pixel**: adatta, riempi e ritaglia, deforma; oppure mantiene le dimensioni originali.
- **Peso dei file**: peso massimo per ogni immagine e/o peso massimo totale di tutte le immagini, con scelta
  automatica della qualità.
- **Molti formati**: JPEG, PNG, HEIC/HEIF (iPhone), WebP, AVIF, TIFF, BMP, GIF, JPEG 2000, PSD e altri.
- **Comprimi PDF**: riduce il peso dei PDF con immagini (documenti d'identità, scansioni) lasciando intatti testo
  e grafica; peso massimo per ogni PDF; rimozione dei metadati.
- **Aggiornamenti automatici** e guida completa (tasto F1).

## Per chi sviluppa

Il programma è un unico file Python: `RidimensionaImmagini.py` (Python 3.9 o successivo).

```
py -m pip install pillow pillow-heif tkinterdnd2
py -m pip install --no-deps pymupdf
py RidimensionaImmagini.py
```

`pymupdf` va installato con `--no-deps`: le sue dipendenze (onnxruntime, numpy, networkx) servono solo per
funzioni di analisi dell'impaginazione che il programma non usa, e renderebbero l'eseguibile più pesante di
oltre 50 MB.

Per creare l'eseguibile su Windows basta avviare `Crea_EXE.bat`, che usa `RidimensionaImmagini.spec` e alla fine
esegue la prova automatica (`RidimensionaImmagini.exe --autotest risultato.txt`).

### Pubblicare una nuova versione

1. Aggiorna `APP_VERSION` (es. `"0.9.5 beta"`) e aggiungi le novità in cima a `CHANGELOG`, all'inizio di
   `RidimensionaImmagini.py`.
2. Carica la modifica su `main`.
3. GitHub crea da solo l'eseguibile su Windows, l'etichetta (es. `v0.9.5-beta`) e la versione con le novità
   (`.github/workflows/rilascio.yml`). Chi usa il programma la riceve all'avvio successivo.
   Se il numero di versione non cambia, non viene pubblicato nulla.

## Licenza

Copyright © 2026 Giovanni Orlando — distribuito con licenza [GNU AGPL-3.0](LICENSE).
Il programma usa [Pillow](https://python-pillow.org/), [pillow-heif](https://github.com/bigcat88/pillow_heif),
[PyMuPDF](https://pymupdf.readthedocs.io/) (AGPL-3.0) e [tkinterdnd2](https://github.com/Eliav2/tkinterdnd2).
