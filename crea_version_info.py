# -*- coding: utf-8 -*-
"""Crea version_info.txt (le informazioni di versione dell'exe) leggendo APP_VERSION dal programma.
Usato da Crea_EXE.bat e dalla creazione automatica su GitHub."""
import os
import re

here = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(here, "RidimensionaImmagini.py"), encoding="utf-8").read()
version = re.search(r'^APP_VERSION = "([^"]+)"', src, re.M).group(1)
nums = [int(x) for x in re.findall(r"\d+", version)[:3]]
nums += [0] * (3 - len(nums))
v4 = "(%d, %d, %d, 0)" % tuple(nums)

text = """# Generato da crea_version_info.py: non modificare a mano
VSVersionInfo(
  ffi=FixedFileInfo(filevers=%(v4)s, prodvers=%(v4)s, mask=0x3f, flags=%(flags)s, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([
      StringTable('041004B0', [
        StringStruct('CompanyName', 'Giovanni Orlando'),
        StringStruct('FileDescription', 'Ridimensiona Immagini'),
        StringStruct('FileVersion', '%(ver)s'),
        StringStruct('InternalName', 'RidimensionaImmagini'),
        StringStruct('LegalCopyright', 'Giovanni Orlando - licenza AGPL-3.0'),
        StringStruct('OriginalFilename', 'RidimensionaImmagini.exe'),
        StringStruct('ProductName', 'Ridimensiona Immagini'),
        StringStruct('ProductVersion', '%(ver)s')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1040, 1200])])
  ]
)
""" % {"v4": v4, "ver": version, "flags": "0x2" if "beta" in version.lower() else "0x0"}

with open(os.path.join(here, "version_info.txt"), "w", encoding="utf-8") as f:
    f.write(text)
print("version_info.txt creato per la versione", version)
