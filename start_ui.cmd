@echo off
REM Script de démarrage de Keck3 UI pour Windows

setlocal enabledelayedexpansion

REM Vérifie que Python est installé
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Erreur: Python n'est pas installé ou pas dans le PATH
    echo Téléchargez Python depuis https://www.python.org
    pause
    exit /b 1
)

REM Change vers le répertoire du script
cd /d "%~dp0"

REM Crée l'environnement virtuel s'il n'existe pas
if not exist "venv\" (
    echo Création de l'environnement virtuel...
    python -m venv venv
)

REM Active l'environnement virtuel
call venv\Scripts\activate.bat

REM Installe les dépendances
echo Installation des dépendances...
pip install -r requirements.txt >nul 2>&1

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

REM Démarre Keck3 UI
echo.
echo ===================================
echo Démarrage de Keck3 UI
echo ===================================
echo.

python ui.py

pause
