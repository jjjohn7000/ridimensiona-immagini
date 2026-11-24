@echo off
setlocal
cd /d "%~dp0"
title Creazione RidimensionaImmagini.exe

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
    echo Python non e' installato.
    echo Scaricalo da https://www.python.org/downloads/ e durante l'installazione
    echo spunta "Add python.exe to PATH". Poi riavvia questo file.
    pause
    exit /b 1
)

echo [1/3] Installazione dei componenti necessari...
%PY% -m pip install --upgrade pip pillow pillow-heif tkinterdnd2 pyinstaller
if errorlevel 1 goto errore
rem PyMuPDF senza le librerie aggiuntive che il programma non usa (eseguibile molto più leggero)
%PY% -m pip install --upgrade --no-deps pymupdf
if errorlevel 1 goto errore

echo.
echo [2/3] Creazione dell'eseguibile (richiede circa un minuto)...
%PY% crea_version_info.py
if errorlevel 1 goto errore
%PY% -m PyInstaller --noconfirm --clean RidimensionaImmagini.spec
if errorlevel 1 goto errore
echo Prova automatica dell'eseguibile...
"dist\RidimensionaImmagini.exe" --autotest "%~dp0prova_automatica.txt"
type "%~dp0prova_automatica.txt"
findstr /c:"TUTTO OK" "%~dp0prova_automatica.txt" >nul || goto errore

echo.
echo [3/3] Pulizia...
copy /y "dist\RidimensionaImmagini.exe" "RidimensionaImmagini.exe" >nul
rmdir /s /q build dist 2>nul
del /q prova_automatica.txt 2>nul

echo.
echo Fatto! Trovi RidimensionaImmagini.exe in questa cartella.
pause
exit /b 0

:errore
echo.
echo Si e' verificato un errore: leggi i messaggi qui sopra.
pause
exit /b 1
