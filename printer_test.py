#!/usr/bin/env python
"""Outil de test des imprimantes d'étiquettes (Windows).

    python printer_test.py                 # liste les imprimantes visibles
    python printer_test.py barcode F1-1    # imprime une étiquette code-barres de test
    python printer_test.py serial F1-1     # imprime une étiquette numéro de série de test
"""

import sys
from typing import Sequence

from core.label_printer import LabelPrinter
from core.labels import LabelBuilder, Program
from config import LABELS_DIR, LABEL_PRINTER_BARCODE, LABEL_PRINTER_SERIAL

TEST_PROGRAM = Program(code=0, name='TEST', product_code='000000', duration=0,
                       labels=('ETIQUETTE DE TEST', 'KECK3', ''))


def main(argv: Sequence[str]) -> int:
    printer = LabelPrinter()
    if len(argv) < 2:
        print("Imprimantes visibles depuis ce poste :")
        for name in printer.list_network_printers():
            print(f"  - {name}")
        print(f"\nConfigurées : code-barres = {LABEL_PRINTER_BARCODE} | série = {LABEL_PRINTER_SERIAL}")
        return 0

    kind = argv[1]
    serial_number = argv[2] if len(argv) > 2 else 'F0-0'
    builder = LabelBuilder(LABELS_DIR)
    if kind == 'barcode':
        ok = printer.print_barcode(builder.barcode_label(serial_number, TEST_PROGRAM))
    elif kind == 'serial':
        ok = printer.print_serial_number(builder.serial_number_label(serial_number, TEST_PROGRAM))
    else:
        print(__doc__)
        return 2
    print("Impression envoyée" if ok else "Échec de l'impression (voir logs)")
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
