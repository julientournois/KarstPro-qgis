@echo off
setlocal enabledelayedexpansion
set "ZIP=%~dp0karstpro.zip"
set "FOUND=0"
set "LASTDST="
echo === Installation du plugin KarstPro ===
if not exist "%ZIP%" (
  echo   karstpro.zip introuvable a cote de ce script.
  pause & exit /b 1
)
for %%V in (QGIS4 QGIS3) do (
  if exist "%APPDATA%\QGIS\%%V\profiles\default\python\plugins" (
    set "PLUGDIR=%APPDATA%\QGIS\%%V\profiles\default\python\plugins"
    set "DST=!PLUGDIR!\karstpro"
    if exist "!DST!" rmdir /S /Q "!DST!"
    powershell -NoProfile -Command "Expand-Archive -LiteralPath '%ZIP%' -DestinationPath '!PLUGDIR!' -Force"
    echo   plugin installe dans %%V : !DST!
    set "FOUND=1"
    set "LASTDST=!DST!"
  )
)
if "!FOUND!"=="0" (
  echo   Aucun profil QGIS trouve.
  echo   Utilise plutot : QGIS ^> Extensions ^> Installer depuis un ZIP ^> karstpro.zip
)

echo.
echo === Installation des dependances Python ===
if defined LASTDST if exist "!LASTDST!\install_deps.bat" (
  call "!LASTDST!\install_deps.bat"
) else (
  echo   Ouvre QGIS ^> Extensions ^> Console Python, puis :
  echo       import karstpro.install_dependencies
)
echo.
echo Termine. Redemarre QGIS, puis active "KarstPro" dans les extensions.
pause
