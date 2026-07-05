#!/usr/bin/env python
"""
Utilitaire de test pour les imprimantes.
Permet de lister, configurer et tester l'impression vers les imprimantes réseau.
"""

import sys
from pathlib import Path

def test_printer_availability():
    """Teste la disponibilité de win32print."""
    print("Test 1: Disponibilité de win32print")
    print("-" * 50)

    try:
        import win32print
        print("✓ win32print installé")
        return True
    except ImportError:
        print("✗ win32print non disponible")
        print("\nPour installer:")
        print("  pip install pywin32")
        print("  python -m pip install --upgrade pywin32")
        return False

def list_printers():
    """Liste toutes les imprimantes disponibles."""
    print("\nTest 2: Listage des imprimantes")
    print("-" * 50)

    try:
        from core.label_printer import LabelPrinter
        printer = LabelPrinter()
        printers = printer.list_network_printers()

        if printers:
            print(f"✓ {len(printers)} imprimante(s) trouvée(s):")
            for i, p in enumerate(printers, 1):
                print(f"  {i}. {p}")
            return printers
        else:
            print("⚠ Aucune imprimante trouvée")
            print("  Vérifiez que les imprimantes sont connectées au réseau")
            return []

    except Exception as e:
        print(f"✗ Erreur: {e}")
        return []

def test_print_to_printer(printer_name: str, test_data: str = None):
    """Teste l'impression vers une imprimante spécifique."""
    print(f"\nTest 3: Impression vers {printer_name}")
    print("-" * 50)

    if test_data is None:
        test_data = b"\x1B[?32h"  # Commande ZPL/ESC simple

    try:
        from core.label_printer import LabelPrinter
        printer = LabelPrinter()

        # Convertir string en bytes si nécessaire
        if isinstance(test_data, str):
            test_data = test_data.encode('ascii')

        success = printer.print_to_printer(
            test_data,
            printer_name,
            "Test Label",
            qty=1
        )

        if success:
            print(f"✓ Impression réussie vers {printer_name}")
        else:
            print(f"✗ Échec de l'impression vers {printer_name}")

        return success

    except Exception as e:
        print(f"✗ Erreur: {e}")
        return False

def generate_config(barcode_printer: str, serial_printer: str):
    """Génère la configuration .env pour les imprimantes."""
    print("\nTest 4: Configuration .env suggérée")
    print("-" * 50)

    config = f"""# Label Printing Configuration
LABEL_PRINTER_BARCODE={barcode_printer}
LABEL_PRINTER_SERIAL={serial_printer}
"""

    print("Copier cette configuration dans votre .env:")
    print(config)

    # Sauvegarder dans un fichier temporaire
    config_file = Path("printer_config.txt")
    config_file.write_text(config)
    print(f"Configuration sauvegardée dans: {config_file}")

def main():
    """Menu principal."""
    print("=" * 60)
    print("Keck3 - Utilitaire de Test d'Imprimantes")
    print("=" * 60)

    if not test_printer_availability():
        print("\n✗ Impossible de continuer sans win32print")
        return 1

    printers = list_printers()

    if not printers:
        print("\n✗ Aucune imprimante disponible")
        return 1

    print("\n" + "=" * 60)
    print("Menu")
    print("=" * 60)
    print("1. Tester l'impression vers une imprimante")
    print("2. Générer la configuration .env")
    print("3. Quitter")

    choice = input("\nChoisir une option (1-3): ").strip()

    if choice == "1":
        print("\nImprimantes disponibles:")
        for i, p in enumerate(printers, 1):
            print(f"  {i}. {p}")

        try:
            idx = int(input("Sélectionner le numéro d'imprimante: ")) - 1
            if 0 <= idx < len(printers):
                test_print_to_printer(printers[idx])
            else:
                print("✗ Sélection invalide")
                return 1
        except ValueError:
            print("✗ Entrée invalide")
            return 1

    elif choice == "2":
        print("\nConfigurez les imprimantes:")
        print("Imprimantes disponibles:")
        for i, p in enumerate(printers, 1):
            print(f"  {i}. {p}")

        try:
            barcode_idx = int(input("Imprimante pour code-barres (numéro): ")) - 1
            serial_idx = int(input("Imprimante pour numéro de série (numéro): ")) - 1

            if 0 <= barcode_idx < len(printers) and 0 <= serial_idx < len(printers):
                generate_config(printers[barcode_idx], printers[serial_idx])
            else:
                print("✗ Sélection invalide")
                return 1
        except ValueError:
            print("✗ Entrée invalide")
            return 1

    elif choice == "3":
        print("Au revoir!")
        return 0

    else:
        print("✗ Option invalide")
        return 1

    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nArrêt.")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Erreur: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
