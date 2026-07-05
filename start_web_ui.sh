#!/bin/bash

# Script de démarrage de Keck3 Web UI pour macOS/Linux

set -e

# Vérifie que Python est installé
if ! command -v python3 &> /dev/null; then
    echo "Erreur: Python 3 n'est pas installé"
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

# Installe les dépendances
echo "Installation des dépendances..."
venv/bin/pip install -q -r requirements.txt

# Vérifie la configuration
if [ ! -f ".env" ]; then
    echo ""
    echo "ATTENTION: Fichier .env non trouvé!"
    echo "Copie de .env.example vers .env..."
    cp .env.example .env
    echo ""
    echo "Veuillez éditer le fichier .env avec vos paramètres"
    echo ""
fi

# Démarre Keck3 Web UI
echo ""
echo "==================================="
echo "Démarrage de Keck3 Web UI"
echo "==================================="
echo ""
echo "Ouvrez votre navigateur :"
echo "  👉 http://localhost:5000"
echo ""

venv/bin/python web_ui.py
