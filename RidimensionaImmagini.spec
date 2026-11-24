# -*- mode: python ; coding: utf-8 -*-
# Configurazione di PyInstaller per creare RidimensionaImmagini.exe
# (usata da Crea_EXE.bat e dalla creazione automatica su GitHub).
# Esegui prima "python crea_version_info.py", poi "python -m PyInstaller --noconfirm --clean RidimensionaImmagini.spec".
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for pkg in ("tkinterdnd2", "pillow_heif"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# Parti delle librerie che il programma non usa: il motore di intelligenza artificiale di PyMuPDF
# per riconoscere tabelle e impaginazione (oltre 100 MB) e le librerie che si porta dietro.
EXCLUDES = ["numpy", "onnxruntime", "networkx", "pymupdf.layout", "pymupdf4llm", "pandas",
            "matplotlib", "scipy", "IPython", "yaml", "tabulate", "psutil"]

a = Analysis(
    ["RidimensionaImmagini.py"],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
    excludes=EXCLUDES,
)


def unused(path):
    path = path.replace("\\", "/")
    return path.startswith(("pymupdf/layout/", "pymupdf4llm/", "onnxruntime/", "numpy/", "numpy.libs/"))


a.datas = [x for x in a.datas if not unused(x[0])]
a.binaries = [x for x in a.binaries if not unused(x[0])]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="RidimensionaImmagini",
    console=False,
    version="version_info.txt",
    upx=False,
)
