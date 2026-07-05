@echo off
REM Script de démarrage de Keck3 Web UI pour Windows

setlocal enabledelayedexpansion

REM Change vers le répertoire du script
cd /d "%~dp0"

REM Crée l'environnement virtuel s'il n'existe pas
if not exist "venv\" (
    echo Création de l'environnement virtuel...
    python -m venv venv
)

REM Installe les dépendances
echo Installation des dépendances...
call venv\Scripts\pip.exe install -q -r requirements.txt

REM Vérifie la configuration
if not exist ".env" (
    echo.
    echo ATTENTION: Fichier .env non trouvé!
    echo Copie de .env.example vers .env...
    copy .env.example .env
    echo.
    echo Veuillez éditer le fichier .env avec vos paramètres
    echo.
    pause
)

REM Démarre Keck3 Web UI
echo.
echo ===================================
echo Démarrage de Keck3 Web UI
echo ===================================
echo.
echo Ouvrez votre navigateur :
echo   http://localhost:5000
echo.

call venv\Scripts\python.exe web_ui.py

pause
