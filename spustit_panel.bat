@echo off
rem Spusti ovladaci panel tydenniho reportu dvojklikem.
chcp 65001 >nul
cd /d "%~dp0"
title Týdenní report – ovládací panel

if not exist ".venv\Scripts\streamlit.exe" (
    echo.
    echo Chybí připravené prostředí .venv – panel teď nejde spustit.
    echo Postup instalace je v souboru README.md v části „Jak spustit“.
    echo.
    pause
    exit /b 1
)

echo.
echo Spouštím ovládací panel, za chvíli se otevře v prohlížeči:
echo     http://localhost:8501
echo Toto okno nechte otevřené. Jeho zavřením panel vypnete.
echo.
rem Prohlizec se otevre s kratkym zpozdenim, az panel nabehne (PANEL_BEZ_PROHLIZECE=1 ho neotevre).
if not defined PANEL_BEZ_PROHLIZECE start "" /min cmd /c "timeout /t 4 /nobreak >nul & start http://localhost:8501"
".venv\Scripts\streamlit.exe" run app.py --server.port 8501 %*

echo.
echo Panel se ukončil.
pause
