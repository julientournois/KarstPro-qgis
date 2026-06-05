@echo off
setlocal enabledelayedexpansion

echo.
echo ============================================================
echo   KarstPro -- Installation des dependances Python
echo ============================================================
echo.

:: -----------------------------------------------------------------------
:: Recherche du Python QGIS
:: Priorite : QGIS 4.x avant QGIS 3.x, lecteurs C: D: E:
:: -----------------------------------------------------------------------

set PYTHON_EXE=
set QGIS_VER=
set QGIS_DIR=

:: QGIS 4.x
for %%L in (C D E) do (
    for /d %%D in ("%%L:\Program Files\QGIS 4*") do (
        for %%P in (Python312 Python311 Python310) do (
            if "!PYTHON_EXE!"=="" (
                if exist "%%D\apps\%%P\python.exe" (
                    set "PYTHON_EXE=%%D\apps\%%P\python.exe"
                    set "QGIS_VER=4"
                    set "QGIS_DIR=%%D"
                )
            )
        )
    )
)

:: QGIS 3.x (si 4.x non trouve)
if "!PYTHON_EXE!"=="" (
    for %%L in (C D E) do (
        for /d %%D in ("%%L:\Program Files\QGIS 3*") do (
            for %%P in (Python312 Python311 Python39) do (
                if "!PYTHON_EXE!"=="" (
                    if exist "%%D\apps\%%P\python.exe" (
                        set "PYTHON_EXE=%%D\apps\%%P\python.exe"
                        set "QGIS_VER=3"
                        set "QGIS_DIR=%%D"
                    )
                )
            )
        )
    )
)

:: -----------------------------------------------------------------------
:: Resultat de la detection
:: -----------------------------------------------------------------------
if "!PYTHON_EXE!"=="" (
    echo [ERREUR] Aucune installation QGIS detectee.
    echo.
    echo Solutions :
    echo   1. Verifiez que QGIS est installe dans C:\Program Files ou D:\Program Files
    echo   2. Editez ce script et renseignez manuellement PYTHON_EXE :
    echo      set PYTHON_EXE=C:\chemin\vers\QGIS\apps\Python312\python.exe
    echo.
    pause
    exit /b 1
)

echo [OK] QGIS !QGIS_VER! detecte
echo      Dossier : !QGIS_DIR!
echo      Python  : !PYTHON_EXE!
echo.

:: -----------------------------------------------------------------------
:: Verification pip
:: -----------------------------------------------------------------------
"!PYTHON_EXE!" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] pip non disponible.
    echo Relancez ce script en tant qu'Administrateur.
    pause
    exit /b 1
)

:: -----------------------------------------------------------------------
:: Installation
:: -----------------------------------------------------------------------
echo Installation en cours : whitebox rasterio geopandas reportlab pyproj
echo.

"!PYTHON_EXE!" -m pip install --upgrade whitebox rasterio geopandas reportlab pyproj

if errorlevel 1 (
    echo.
    echo [ERREUR] L'installation a echoue.
    echo   - Relancez en tant qu'Administrateur
    echo   - Verifiez votre connexion internet
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Installation terminee avec succes !
echo   Rechargez le plugin KarstPro dans QGIS pour appliquer.
echo ============================================================
echo.
pause
