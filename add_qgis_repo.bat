@echo off
setlocal enabledelayedexpansion
rem Enregistre le depot custom Karst Entry dans QGIS (mises a jour automatiques).
rem Fermer QGIS avant de lancer ce script (sinon il ecrase la modification a sa fermeture).

set SCRIPT=%~dp0add_qgis_repo.py

rem Cherche un interpreteur Python fourni par QGIS (a besoin de PyQt5/PyQt6).
set PYQGIS=

for %%D in (
    "%ProgramFiles%\QGIS*"
    "%ProgramFiles(x86)%\QGIS*"
    "C:\OSGeo4W\bin"
    "C:\OSGeo4W64\bin"
) do (
    if exist "%%~D\bin\python-qgis.bat" set PYQGIS=%%~D\bin\python-qgis.bat
    if exist "%%~D\bin\python-qgis-ltr.bat" if "!PYQGIS!"=="" set PYQGIS=%%~D\bin\python-qgis-ltr.bat
)

if "%PYQGIS%"=="" (
    for /d %%D in ("%ProgramFiles%\QGIS *" "%ProgramFiles(x86)%\QGIS *") do (
        if exist "%%~D\bin\python-qgis.bat" set PYQGIS=%%~D\bin\python-qgis.bat
        if exist "%%~D\bin\python-qgis-ltr.bat" if "!PYQGIS!"=="" set PYQGIS=%%~D\bin\python-qgis-ltr.bat
    )
)

if "%PYQGIS%"=="" (
    echo Python de QGIS introuvable automatiquement.
    echo Lancez a la main : ^<dossier QGIS^>\bin\python-qgis.bat "%SCRIPT%"
    exit /b 1
)

echo Interpreteur QGIS : %PYQGIS%
call "%PYQGIS%" "%SCRIPT%" %*
