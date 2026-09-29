# Impression des étiquettes

## Principe (repris de keck1)

Chaque machine reçoit **deux étiquettes**, imprimées ensemble et immédiatement :

| Étiquette | Gabarit | Imprimante (défaut) | Contenu |
|-----------|---------|---------------------|---------|
| Code-barres produit | `labels/barcode.sbpl` | `\\misrv-imp\MI-IMPCB-M1-01` | n° de série (code-barres), année (2 chiffres), libellés article 1 à 3 |
| Numéro de série | `labels/serial_number.sbpl` | `\\misrv-imp\MI-IMPCB-M1-02` | code article, n° de série (code-barres + clair) |

Les gabarits sont les fichiers SBPL (imprimantes SATO) de keck1 (`web/tmp/model/void.txt` et `serial.txt`),
avec des marqueurs remplacés à la volée : `NUMERO_OF` (reçoit le n° de série, comme dans keck1), `YEAR`,
`LIBELLE1..3`, `CODE`, `NUMEROSERIECB` (×2). Ils sont envoyés en RAW via `win32print`.

## Quand imprime-t-on ?

Règle `core/labels.should_print()` :

1. Le contrôle doit être **OK** (code statut `1`).
2. Le **programme** de la machine doit être connu (`data/programs.json`).
3. Si le programme a une **durée 0** (pas de test de chauffe) → impression après le **contrôle électrique**.
   Si la durée est **> 0** → impression après le **contrôle de chauffe** OK (par voie, donc par machine).
4. Par défaut, les étiquettes sortent **une fois le contrôle accepté par Open Prod** (`PRINT_REQUIRES_API_SUCCESS=true`,
   comportement keck1). Si Open Prod est en panne, le contrôle attend dans `data/outbox/` et les étiquettes sortent au
   retour. Un contrôle refusé par Open Prod (`data/outbox/failed/`) n'est jamais étiqueté. Avec `false`, on imprime dès
   la mise en file.

Le programme d'une machine est appris lors de son contrôle électrique et mémorisé dans `data/machines.json`
(la trame de chauffe ne le contient pas).

## Référentiel des programmes

`data/programs.json` (modèle : `programs.example.json`) remplace la table Oracle `Program` et la vue
`VW_XX_ETIQ_MAC_ELEC` :

```json
{
  "1": { "name": "CALORIBAC", "product_code": "260434", "duration": 0,
         "labels": ["CALORIBAC 260434", "220-240 V~50 Hz  300 W     IPX3", ""] }
}
```

Clé = code programme envoyé par le banc (champ 4 de la trame électrique).

## Configuration et test

```bash
python printer_test.py                 # liste les imprimantes visibles depuis le poste
python printer_test.py barcode F1-1    # imprime une étiquette code-barres de test
python printer_test.py serial F1-1     # imprime une étiquette n° de série de test
```

Puis dans `.env` : `LABEL_PRINTER_BARCODE`, `LABEL_PRINTER_SERIAL` (noms exacts), `PRINT_LABELS`,
`PRINT_REQUIRES_API_SUCCESS`.

## Dépannage

- **« win32print non disponible »** : `pip install pywin32` (installé automatiquement sur Windows via `requirements.txt`).
- **« Programme N inconnu … impossible d'imprimer »** : ajouter le programme dans `data/programs.json`.
- **Rien ne s'imprime alors que le contrôle est OK** : vérifier la durée du programme (0 ↔ électrique, > 0 ↔ chauffe) et le statut de transmission dans les logs.
- **Nom d'imprimante introuvable** : copier le nom exact affiché par `printer_test.py`.

## Limites

- Windows uniquement (`win32print`).
- Pas de confirmation d'impression physique (envoi au spouleur seulement).
