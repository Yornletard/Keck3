# Architecture Keck3

## Vue d'ensemble

Keck3 remplace le couple Keck1 (serveur Symfony + Oracle) + KeckCapture (client Python) par
une seule application Python installée sur le poste du banc.

### Avant (Keck1/KeckCapture)
```
Banc D1118 → Port série → KeckCapture → HTTP POST → Keck1 (Symfony) → Oracle
                                                        ↓ fichiers étiquettes (partage réseau)
                                        KeckCapture scanne le partage toutes les 5 s → imprimantes SATO
```

### Maintenant (Keck3)
```
Banc D1118 → Port série → Keck3 → HTTP POST → API Open Prod
                              ↓
                       étiquettes SBPL → imprimantes SATO (win32print, immédiat)
```

## Modules

- `core/serial_reader.py` : port série (9600 bauds, parité N), découpage des champs, nettoyage des octets NUL, détection de perte de port.
- `api/models.py` : **protocole du banc** (voir ci-dessous), dataclasses et payloads.
- `api/client.py` : client de l'**API Open Prod** (générique, Odoo-like) : `getToken` puis `endpoint` (`create`/`read`/`update`/`read_fields`…), jeton renouvelé automatiquement, retry sur pannes passagères.
- `api/publisher.py` : traduit un contrôle Keck3 en enregistrement Open Prod d'après `data/openprod_mapping.json` (modèle + champs), après vérification qu'il n'existe pas déjà (`dedupe_on`).
- `core/outbox.py` : file locale persistée (`data/outbox/`), un fichier JSON par contrôle, clé d'idempotence `type:série:horodatage[:voie]`.
- `core/labels.py` : référentiel des programmes, mémoire machine → programme, génération SBPL, règle d'impression.
- `core/label_printer.py` : envoi RAW vers les imprimantes réseau (Windows).
- `run.py` : orchestration, deux threads : lecteur série (parse, met en file) et publieur (rejoue la file vers Open Prod, imprime les étiquettes une fois le contrôle accepté), événements pour l'UI.
- `web_ui.py` : tableau de bord Flask branché sur les événements de `run.py`.
- `update_manager.py` : mise à jour par `git pull`.

## Protocole du banc D1118

Source de vérité : le code de keck1 (`MachineService`, `PrintService`) et les trames réelles archivées dans
ses tests. Une trame = **deux lignes** série ; chaque champ est un entier ASCII à zéros de tête terminé par
un octet NUL.

- **Ligne 1** : `jj/mm/aaaa hh:mm:ss` → horodatage du contrôle (celui du banc, pas celui du PC).
- **Ligne 2 électrique** (12 champs, donc `< 13`) :

  | # | Champ | Transformation |
  |---|-------|----------------|
  | 0 | n° d'OF | `F{OF}` |
  | 1 | n° dans l'OF | n° de série machine = `F{OF}-{n}` |
  | 2 | opérateur | |
  | 3 | programme | clé du référentiel (durée, article, libellés) |
  | 4 | continuité | |
  | 5 | tension HT | |
  | 6 | perte d'intensité HT | |
  | 7 | isolement | |
  | 8 | tension puissance | ×0.1 (V) |
  | 9 | intensité | ×0.001 (A) |
  | 10 | intensité calculée | ×0.001 (A) |
  | 11 | code statut | 1 = OK |

- **Ligne 2 chauffe** (40 champs, donc `>= 13`) : 8 voies × `[OF, n° dans l'OF, opérateur, température ×0.1, statut]`.
  Une voie dont l'OF vaut 0 est vide. Chaque voie = une machine distincte.

### Assemblage des trames
La ligne 1 est reconnue par sa date : elle **recale** toujours le tampon. Une ligne de données sans ligne date
avant elle est ignorée, une ligne date suivie d'une autre ligne date abandonne la trame incomplète. On ne peut
donc pas rester décalé d'une ligne comme avec KeckCapture.

## Flux de traitement

1. Trame assemblée → `DataParser.classify_frame()` (taille de la ligne 2).
2. Parsing → `ElectricalControlData` ou liste de `HeatControlData` (une par voie active).
3. Contrôle électrique : mémorisation `n° de série → programme` (`data/machines.json`), car la trame de chauffe
   ne porte pas le programme.
4. **Mise en file** (`data/outbox/<clé>.json`) : le contrôle est écrit sur disque avant tout envoi, un fichier par
   contrôle électrique ou par voie de chauffe. Une trame reçue deux fois n'est mise en file qu'une fois.
5. **Publication** par le thread publieur, dans l'ordre d'arrivée : `read` de contrôle d'existence (`dedupe_on`), résolution
   des many2one (`relations` : l'OF `F123456` est cherché par son `name` dans `mrp.manufacturingorder` → `x_mo_id` ;
   introuvable → créé sans lien avec un avertissement, sauf `required`) puis
   `create` sans rejeu HTTP interne. Accepté → fichier supprimé, étiquettes ; panne (`OpenProdUnavailable`) → rejeu
   avec attente croissante (5 s, 15 s, 60 s, 5 min), les suivants attendent ; refus (`OpenProdError`) → déplacé dans
   `data/outbox/failed/` avec le motif, sans étiquette, pour arbitrage humain.
6. Règle d'impression (voir PRINTING.md) → deux étiquettes SBPL, envoyées une fois le contrôle accepté par Open Prod
   (ou dès la mise en file si `PRINT_REQUIRES_API_SUCCESS=false`).
7. Événements émis vers l'UI : `port`, `api`, `frame`, `queued`, `transmitted`, `printed`, `outbox`, `error`.

## Gestion des erreurs

- **Port série** : perte détectée dans `read_line()` → handle fermé aussitôt (sinon Windows refuse la réouverture), reconnexion
  toutes les 5 s sur le même port, tampon vidé. En mode `auto`, le port est choisi par `SERIAL_PORT_MATCH` (adaptateur USB
  série) ou, à défaut, seulement s'il est unique : jamais un port Bluetooth arbitraire.
- **API** : `getToken` et les lectures sont rejoués 3 fois sur 408/429/5xx, timeout et erreur de connexion ; un `create`
  n'est **jamais** rejoué par le client (écriture non idempotente), c'est la file qui rejoue après avoir relu Open Prod :
  un timeout dont le serveur avait pourtant commité ne crée donc pas de doublon. Tout refus (`result.error`, HTTP 400)
  est rejoué **une fois avec un jeton neuf** (le libellé « jeton expiré » n'est pas documenté), puis devient définitif.
- **Panne longue d'Open Prod** : les contrôles s'accumulent dans `data/outbox/` et survivent à un redémarrage de Keck3 ;
  ils sont rejoués au retour, dans l'ordre, puis les étiquettes sortent. Le lecteur série n'est jamais bloqué par l'API.
- **Arrêt** : les deux threads ne sont pas daemon ; `stop()` leur laisse `STOP_TIMEOUT` (60 s) pour finir l'envoi et
  l'impression en cours. `start()` refuse de relancer tant qu'un thread précédent vit (jamais deux lecteurs sur le port).
- **Fichiers JSON édités à la main** (`programs.json`, `openprod_mapping.json`, `machines.json`) : un fichier illisible est
  loggé et ignoré, l'application démarre quand même. `machines.json` est borné (5 000 machines) et écrit de façon atomique ;
  une erreur disque n'empêche jamais l'envoi à Open Prod.
- **Parsing** : trame illisible = warning + événement `error`, l'acquisition continue.
- **Étiquettes** : programme inconnu = warning explicite (compléter `data/programs.json`), pas d'impression.

## Configuration

Tout vient de `.env` (voir `.env.example`). Variables clés : `OPEN_PROD_BASE_URL`, `OPEN_PROD_DB`, `OPEN_PROD_API_KEY`
(clé API personnelle de l'utilisateur Open Prod, qui en porte les droits), `OPEN_PROD_VERIFY_TLS` (`false` : le serveur
interne `misrv-opp1` a un certificat non reconnu), `OPEN_PROD_MAPPING_FILE`, `SERIAL_PORT` / `SERIAL_PORT_MATCH`, `LABEL_PRINTER_*`,
`PRINT_REQUIRES_API_SUCCESS`, `PROGRAMS_FILE`. Les chemins relatifs sont résolus depuis le dossier du projet, pas depuis
le répertoire courant.

## API Open Prod (documentation.open-prod.com, module `web.controllers.openprod_api`)

Open Prod est un ERP dérivé d'Odoo. Son API ne connaît **aucun endpoint métier** : elle expose deux routes.

```
POST /web/api/getToken   {"db": "<base>", "id_secret": "<clé API utilisateur>"}  → result.data = jeton temporaire (2 h)
POST /web/api/endpoint   {"db", "token", "method", "model", ...}
      method = read | create | update | delete | read_fields | read_model | read_wkf | wkf | call_kw | read_token
      create : "values": [["champ", valeur], ...]   (un objet par appel)      → result.data = [id]
      read   : "filters": [["champ", "=", valeur]], "fields", "limit", "order"
Erreur : HTTP 400 + {"result": {"error": {"message": "..."}}}
```

Keck3 **crée des enregistrements dans deux modèles dédiés**, créés par Objectif-PI (Florent Loirat, 29/09/2026) sur la
base de test `qhse_test` du serveur `misrv-opp1.matferbourgeat.com` (bases : `matfer_production`, `qhse_test`) :

| Modèle Open Prod | Champs (préfixe `x_` imposé par Open Prod) |
|---|---|
| `x_electrical_control` « Contrôle électrique » | `x_name` (n° de série), `x_mo_id` (many2one `mrp.manufacturingorder`), `x_operator_number`, `x_program_number`, `x_date_time`, `x_continuity_test`, `x_hv_voltage_test`, `x_hv_intensity_loss_test`, `x_insulation_test`, `x_power_voltage_test`, `x_power_intensity_test`, `x_power_calc_intensity_test`, `x_status_code`, `x_is_ok` (booléen), `x_raw_frame` |
| `x_heating_measurement` « Mesure de chauffe » | `x_name`, `x_mo_id`, `x_operator_number`, `x_way_number`, `x_date_time`, `x_temperature`, `x_status_code`, `x_is_ok` (**entier**, d'où `casts`), `x_raw_frame` |

Le banc ne connaît l'OF que par son numéro (`F123456`) : Keck3 cherche l'OF par son `name` et pose son id dans `x_mo_id`
(consigne de Florent). Le mapping est dans `openprod_mapping.example.json` (à copier dans `data/`). Vérifier les champs
avec `read_fields` avant la mise en prod. Copie locale de la doc : `~/Documents/openprod/site/`.

## Points ouverts

- **Droits d'accès** sur les deux modèles (`ir.model.access`) : aucun au 29/09/2026, même la lecture est refusée → à
  poser par Objectif-PI pour l'utilisateur dont la clé API sert à Keck3. Puis recréer les modèles à l'identique sur
  `matfer_production`.
- **OF de test** : `qhse_test` ne contient aucun ordre de fabrication ; il en faut au format `F123456` pour tester le lien.
- **Numéro de série Open Prod** : Florent souhaite à terme rattacher chaque pièce à un n° de série (m2o, non paramétré),
  à voir avec Pascal Robache. Évolution, pas un préalable.
- **Référentiel des programmes** : `data/programs.json` remplace la table Oracle `Program` et la vue
  `VW_XX_ETIQ_MAC_ELEC`. À alimenter, idéalement depuis Open Prod.

## Tests

```bash
python test_setup.py            # diagnostic + tests unitaires
python -m unittest discover tests
```

Les tests rejouent les trames réelles du banc (électrique et chauffe) et la génération des deux étiquettes.
