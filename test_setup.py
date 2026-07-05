#!/usr/bin/env python
"""
Script de test de configuration pour Keck3.
Vérifie que tous les dépendances et configurations sont correctes.
"""

import sys
import os
from pathlib import Path

def test_imports():
    """Teste que tous les imports essentiels fonctionnent."""
    print("Testing imports...")
    try:
        import serial
        print("  ✓ pyserial")
    except ImportError:
        print("  ✗ pyserial (installer: pip install pyserial)")
        return False

    try:
        import requests
        print("  ✓ requests")
    except ImportError:
        print("  ✗ requests (installer: pip install requests)")
        return False

    try:
        import dotenv
        print("  ✓ python-dotenv")
    except ImportError:
        print("  ✗ python-dotenv (installer: pip install python-dotenv)")
        return False

    # Imports internes
    try:
        from core.logger import setup_logger
        print("  ✓ core.logger")
    except ImportError as e:
        print(f"  ✗ core.logger: {e}")
        return False

    try:
        from core.serial_reader import SerialReader
        print("  ✓ core.serial_reader")
    except ImportError as e:
        print(f"  ✗ core.serial_reader: {e}")
        return False

    try:
        from api.client import OpenProdAPIClient
        print("  ✓ api.client")
    except ImportError as e:
        print(f"  ✗ api.client: {e}")
        return False

    try:
        from api.models import DataParser
        print("  ✓ api.models")
    except ImportError as e:
        print(f"  ✗ api.models: {e}")
        return False

    return True

def test_directories():
    """Teste que les répertoires existent."""
    print("\nTesting directories...")
    dirs = [
        Path("core"),
        Path("api"),
        Path("logs"),
        Path("data"),
    ]

    for d in dirs:
        if d.exists():
            print(f"  ✓ {d}")
        else:
            print(f"  ✗ {d} (sera créé)")

    return True

def test_config():
    """Teste la configuration."""
    print("\nTesting configuration...")

    try:
        from config import (
            OPEN_PROD_BASE_URL,
            OPEN_PROD_API_KEY,
            SERIAL_PORT,
            SERIAL_BAUDRATE,
        )

        print(f"  ✓ OPEN_PROD_BASE_URL: {OPEN_PROD_BASE_URL}")

        if not OPEN_PROD_API_KEY:
            print("  ⚠ OPEN_PROD_API_KEY: non configurée (créer .env)")
            return False
        else:
            print("  ✓ OPEN_PROD_API_KEY: configurée")

        print(f"  ✓ SERIAL_PORT: {SERIAL_PORT}")
        print(f"  ✓ SERIAL_BAUDRATE: {SERIAL_BAUDRATE}")

        return True
    except Exception as e:
        print(f"  ✗ Erreur de configuration: {e}")
        return False

def test_serial_ports():
    """Liste les ports série disponibles."""
    print("\nTesting serial ports...")
    try:
        from core.serial_reader import SerialReader
        ports = SerialReader.list_available_ports()
        if ports:
            print(f"  ✓ {len(ports)} port(s) disponible(s)")
            return True
        else:
            print("  ⚠ Aucun port série détecté (branchez le banc)")
            return True
    except Exception as e:
        print(f"  ✗ Erreur: {e}")
        return False

def test_data_parser():
    """Teste le parser de données."""
    print("\nTesting data parser...")
    try:
        from api.models import DataParser

        # Test electrical control
        frame = (["1"], ["1", "2", "3", "4", "5", "6", "7"])
        control_type = DataParser.classify_frame(frame)
        if control_type == 'electrical':
            print("  ✓ Electrical control classification")
        else:
            print(f"  ✗ Electrical control classification (got {control_type})")
            return False

        # Test heat control
        frame = (["1"], ["75.5", "76.2", "74.8"])
        control_type = DataParser.classify_frame(frame)
        if control_type == 'heat':
            print("  ✓ Heat control classification")
        else:
            print(f"  ✗ Heat control classification (got {control_type})")
            return False

        return True
    except Exception as e:
        print(f"  ✗ Erreur: {e}")
        return False

def main():
    """Exécute tous les tests."""
    print("=" * 60)
    print("Keck3 Setup Test")
    print("=" * 60)

    results = []

    results.append(("Imports", test_imports()))
    results.append(("Directories", test_directories()))
    results.append(("Configuration", test_config()))
    results.append(("Serial Ports", test_serial_ports()))
    results.append(("Data Parser", test_data_parser()))

    print("\n" + "=" * 60)
    print("Résumé des tests")
    print("=" * 60)

    all_ok = True
    for name, result in results:
        status = "✓" if result else "✗"
        print(f"{status} {name}")
        if not result:
            all_ok = False

    print()
    if all_ok:
        print("✓ Tous les tests sont passés!")
        print("\nVous pouvez démarrer Keck3 avec:")
        print("  python run.py")
        return 0
    else:
        print("✗ Certains tests ont échoué.")
        print("\nVérifiez les erreurs ci-dessus et réessayez.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
