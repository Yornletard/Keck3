#!/bin/bash

# Script de démarrage de Keck3 UI pour macOS/Linux

set -e

# Vérifie que Python est installé
if ! command -v python3 &> /dev/null; then
    echo "Erreur: Python 3 n'est pas installé"
    echo "Installez Python 3 depuis https://www.python.org"
    exit 1
fi

# Change vers le répertoire du script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Crée l'environnement virtuel s'il n'existe pas
if [ ! -d "venv" ]; then
    echo "Création de l'environnement virtuel..."
    python3 -m venv venv
fi

# Active l'environnement virtuel
source venv/bin/activate

# Installe les dépendances
echo "Installation des dépendances..."
pip install -r requirements.txt >/dev/null 2>&1

# Vérifie la configuration
if [ ! -f ".env" ]; then
    echo ""
    echo "ATTENTION: Fichier .env non trouvé!"
    echo "Copie de .env.example vers .env..."
    cp .env.example .env
    echo ""
    echo "Veuillez éditer le fichier .env avec vos paramètres"
    echo ""
    read -p "Appuyez sur Entrée pour continuer..."
fi

# Démarre Keck3 UI
echo ""
echo "==================================="
echo "Démarrage de Keck3 UI"
echo "==================================="
echo ""

python ui.py
