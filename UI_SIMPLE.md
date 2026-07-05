# Keck3 UI - Interface Ultra-Simple

## 📦 Installation : 3 clics

### Windows

1. Double-clic sur **`start_ui.cmd`**
2. Attendre que ça s'installe (2-3 min la première fois)
3. Une fenêtre s'ouvre → C'est bon !

### Mac / Linux

1. Double-clic sur **`start_ui.sh`** (ou `chmod +x start_ui.sh && ./start_ui.sh`)
2. Attendre que ça s'installe
3. Une fenêtre s'ouvre → C'est bon !

## 🎨 L'interface

### Fenêtre principale

```
╔═══════════════════════════════════════════════════════════════════════════╗
║  KECK3 - Banc de Contrôle D1118                         ⚙ ❌            ║
╠═══════════════════════════════════════════════════════════════════════════╣
║                                                                           ║
║  Port Série: ✓ Connecté (COM3)        Open Prod: ✓ Connecté            ║
║                                                                           ║
║  ┌─────────────────────────────────────────────────────────────────────┐ ║
║  │ Contrôles électriques: 42  │  Contrôles thermiques: 38              │ ║
║  │ Succès: 78                 │  Erreurs: 2                             │ ║
║  └─────────────────────────────────────────────────────────────────────┘ ║
║                                                                           ║
║  Historique des contrôles (derniers 20)                                  ║
║  ┌───────────┬────────────┬───────────┬──────────────────────────────┐  ║
║  │ Heure     │ Type       │ Statut    │ Détails                      │  ║
║  ├───────────┼────────────┼───────────┼──────────────────────────────┤  ║
║  │ 14:30:45  │ Électrique │ ✓ OK      │ {'continuity': 0.5}          │  ║
║  │ 14:28:12  │ Thermique  │ ✓ OK      │ {'temps': 'V1:75° V2:76°'}   │  ║
║  │ 14:25:38  │ Électrique │ ✓ OK      │ {'continuity': 0.4}          │  ║
║  │ 14:22:05  │ Électrique │ ✗ Erreur  │ {}                           │  ║
║  └───────────┴────────────┴───────────┴──────────────────────────────┘  ║
║                                                                           ║
║  Logs en direct                                                          ║
║  ┌─────────────────────────────────────────────────────────────────────┐ ║
║  │ [14:30:47] INFO     | ✓ Code-barres imprimé                        │ ║
║  │ [14:30:46] INFO     | ✓ Données électriques transmises             │ ║
║  │ [14:30:45] INFO     | → Contrôle électrique                        │ ║
║  │ [14:30:31] INFO     | En attente des données...                    │ ║
║  └─────────────────────────────────────────────────────────────────────┘ ║
║                                                                           ║
╚═══════════════════════════════════════════════════════════════════════════╝
```

## 🎛️ Boutons

- **⚙** : Ouvrir la configuration
- **❌** : Fermer l'app

## ⚙️ Configuration

Clic sur le bouton **⚙** pour :

```
┌─────────────────────────────────────────────┐
│ Configuration Keck3                         │
├─────────────────────────────────────────────┤
│                                             │
│ Port Série: [COM3          ] [Détecter]    │
│ Open Prod URL: [https://... ]              │
│ Clé API: [••••••••••••••••]                │
│                                             │
│ [Sauvegarder] [Annuler]                   │
└─────────────────────────────────────────────┘
```

## 📊 Ce que tu vois

### Statut
- ✓ = Connecté et OK
- ✗ = Erreur/Disconnecté

### Statistiques en direct
- Compte des contrôles électriques
- Compte des contrôles thermiques
- Nombre de succès
- Nombre d'erreurs

### Historique
- Derniers 20 contrôles
- Type : Électrique ou Thermique
- Statut : ✓ OK ou ✗ Erreur
- Détails : valeurs clés

### Logs
- Ce qui se passe en temps réel
- Auto-scroll vers le bas
- Conserve les 100 derniers logs

## 🚀 Workflow type

1. Lancer `start_ui.cmd` ou `start_ui.sh`
2. Fenêtre s'ouvre
3. Vérifier "Port Série" et "Open Prod" = ✓ Connectés
4. Faire un test sur le banc
5. Voir immédiatement les résultats dans l'historique
6. Vérifier les logs pour les détails

## 💾 Données

- **Historique** : stocké en mémoire (50 derniers)
- **Logs** : stocké en mémoire (100 derniers)
- **Stats** : persistence en temps réel
- **Détails complets** : stockés par Open Prod

## 🔧 Dépannage

### "Port Série: ✗ Erreur"
- Vérifier que le banc est branché
- Clic ⚙ → Détecter → Sélectionner le bon port

### "Open Prod: ✗ Erreur"
- Vérifier la clé API dans `.env`
- Vérifier la connexion internet
- Clic ⚙ → Vérifier l'URL

### Interface figée
- Fermer et relancer
- Vérifier `logs/keck3.log`

## 📝 Fichiers de configuration

Le fichier `.env` doit exister :

```env
# Configuration Open Prod
OPEN_PROD_BASE_URL=https://open-prod.matferbourgeat.com
OPEN_PROD_API_KEY=votre_clé_ici

# Port Série
SERIAL_PORT=COM3
SERIAL_BAUDRATE=9600

# Imprimantes
LABEL_PRINTER_BARCODE=\\serveur\imprimante1
LABEL_PRINTER_SERIAL=\\serveur\imprimante2

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/keck3.log
```

## 🎯 C'est tout !

C'est ultra simple :
- ✅ Installation automatique
- ✅ Interface claire et légère
- ✅ Pas de configuration complexe
- ✅ Juste double-clic et c'est parti

Questions ? Regarder `logs/keck3.log` pour les détails techniques.
