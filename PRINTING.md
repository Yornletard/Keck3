# Guide d'impression Keck3

## Nouvelle approche : Impression immédiate

À partir de Keck3, l'impression des étiquettes fonctionne en **mode immédiat** vers les imprimantes réseau connectées. Il n'y a plus besoin de dossier partagé ni de scanner périodique.

### Architecture

```
Banc D1118
    ↓
Données de contrôle reçues
    ↓
Transmission Open Prod API
    ↓
✓ Succès ?
    ↓
Impression immédiate vers imprimante réseau
```

### Avantages

- ✅ **Plus rapide** : pas d'attente de scan (5s → instantané)
- ✅ **Plus simple** : pas de dossier partagé à configurer
- ✅ **Plus fiable** : pas de fichiers temporaires à perdre
- ✅ **Plus contrôlé** : impression déclenchée par l'application, pas par un scanner

## Configuration

### Étape 1 : Découvrir les imprimantes

Lancez l'outil de test :

```bash
python printer_test.py
```

Cet outil listera toutes les imprimantes réseau disponibles :

```
Imprimantes disponibles:
  1. \\serveur\imprimante_barcode
  2. \\serveur\imprimante_serial
  3. \\autre_serveur\imprimante_3
```

### Étape 2 : Configurer .env

Créez ou éditez le fichier `.env` :

```env
# Configuration Impression Étiquettes
LABEL_PRINTER_BARCODE=\\serveur\imprimante_barcode
LABEL_PRINTER_SERIAL=\\serveur\imprimante_serial
```

**Important :** Les noms doivent correspondre EXACTEMENT à ce que `printer_test.py` affiche.

### Étape 3 : Tester l'impression

Lancez le menu de test :

```bash
python printer_test.py

# Puis:
# Option 1 : Tester une imprimante spécifique
# Option 2 : Générer la configuration .env
```

## Flux d'impression

### 1. Contrôle Électrique → Code-barres

```
Données électriques reçues
    ↓
Validation & transmission Open Prod
    ↓
✓ Réponse 200/201
    ↓
LabelPrinter.print_barcode(data)
    ↓
Impression sur \\serveur\imprimante_barcode
```

### 2. Contrôle Thermique → Numéro de série

```
Données thermiques reçues
    ↓
Validation & transmission Open Prod
    ↓
✓ Réponse 200/201
    ↓
LabelPrinter.print_serial_number(data)
    ↓
Impression sur \\serveur\imprimante_serial
```

## Données d'impression

Les données envoyées à l'imprimante peuvent être :

1. **Format ZPL** (Zebra Programming Language)
   - Format vectoriel pour étiquettes
   - Utilisé par les imprimantes Zebra, Honeywell, etc.

2. **Format texte ASCII**
   - Commandes ESC (Escape sequences)
   - Format ESC/P (Epson)

3. **Format binaire**
   - Données brutes directives à l'imprimante

### Exemple : Générer du ZPL

```python
def generate_barcode_zpl(barcode_data: str) -> bytes:
    zpl = f"""^XA
^BY2,3.0,50
^FO50,50
^BC^FD{barcode_data}^FS
^XZ"""
    return zpl.encode('ascii')

# Utilisation
from core.label_printer import LabelPrinter
printer = LabelPrinter()
data = generate_barcode_zpl("123456789")
printer.print_barcode(data)
```

## Intégration dans Keck3

### Déclencher l'impression manuellement

```python
from core.label_printer import LabelPrinter

printer = LabelPrinter()

# Impression code-barres
data = b"^XA^BC^FD123456^FS^XZ"  # ZPL
printer.print_barcode(data, qty=1)

# Impression numéro de série
printer.print_serial_number(data, qty=1)

# Impression vers une imprimante spécifique
printer.print_to_printer(data, "\\serveur\imprimante", "Étiquette Test", qty=2)
```

### Intégration dans le flux de traitement

C'est fait automatiquement dans `run.py` :

```python
def _process_electrical_control(self, frame: tuple):
    # ...
    response = self.api_client.post_electrical_control(data_payload)
    if response:
        # Impression automatique
        self._trigger_barcode_print()
```

Pour passer des données au lieu d'imprimer vide :

```python
def _trigger_barcode_print(self, data: Optional[bytes] = None, qty: int = 1):
    if data is None:
        logger.debug("Impression code-barres demandée (données vides)")
        return
    # ...
```

## Dépannage

### Problème : "Impression non disponible (win32print manquant)"

**Cause :** win32print n'est pas installé (nécessite Windows)

**Solution :**
```bash
pip install pywin32
python -m pip install --upgrade pywin32
```

### Problème : "Impossible de trouver l'imprimante"

**Cause :** Le nom d'imprimante dans `.env` est incorrect

**Solution :**
1. Lancer `python printer_test.py`
2. Copier le nom exact de l'imprimante
3. Mettre à jour `.env`

### Problème : "Erreur lors de l'impression"

**Cause :** Imprimante indisponible ou problème de connexion réseau

**Vérifier :**
```bash
# Windows
ping \\serveur
net view \\serveur

# Ou depuis l'Explorateur Windows
# Ouvrir : \\serveur
```

### Logs

Les logs d'impression se trouvent dans `logs/keck3.log` :

```
2025-07-05 14:30:00,123 - Keck3.core.label_printer - INFO - ✓ Barcode imprimé sur \\serveur\imprimante_barcode (copie 1/1)
```

## Limites

- **Windows uniquement** : win32print ne fonctionne que sur Windows
- **Format d'étiquette** : dépend de l'imprimante réseau (ZPL, ESC/P, etc.)
- **Pas d'attente d'impression** : la transmission est asynchrone (pas de confirmation)

## Améliorations futures

1. Support macOS/Linux via CUPS
2. Queue d'impression pour gérer les pics
3. Retry automatique en cas d'échec imprimante
4. Template d'étiquettes configurables
5. Historique d'impressions
