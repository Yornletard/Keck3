"""Publication des contrôles du banc dans Open Prod.

L'API Open Prod est générique (``create`` sur un modèle) : ce module traduit un
contrôle Keck3 en enregistrement Open Prod d'après un **fichier de mapping**
(``data/openprod_mapping.json``, modèle : ``openprod_mapping.example.json``) :

.. code-block:: json

    { "electrical": { "model": "x_electrical_control",
                      "fields": { "serial_number": "x_name", "status_code": "x_status_code" },
                      "casts": { "status_ok": "int" },
                      "relations": { "fab_order_number": { "field": "x_mo_id", "model": "mrp.manufacturingorder",
                                                           "search_field": "name", "required": false } },
                      "constants": { "company_id": 1 },
                      "raw_frame_field": "x_raw_frame",
                      "dedupe_on": ["serial_number", "datetime"] },
      "heat": { "model": "x_heating_measurement", "fields": {...} } }

``fields`` : attribut Keck3 (voir ``ControlData.as_dict``) → champ Open Prod. Seuls les
attributs listés sont envoyés. ``casts`` : conversion d'un attribut avant envoi (``int``,
``float``, ``str``, ``bool``), ex. un booléen Keck3 vers un champ entier Open Prod.
``relations`` : attribut Keck3 → many2one Open Prod, résolu par un ``read`` sur le modèle
cible (``search_field`` = valeur de l'attribut) avant la création. Introuvable : refus
définitif si ``required``, sinon l'enregistrement est créé sans le lien, avec un avertissement
(un contrôle du banc ne doit jamais être perdu pour un OF mal saisi).
``dedupe_on`` : attributs (mappés) qui identifient un contrôle ; avant chaque création, un
``read`` vérifie qu'il n'existe pas déjà, ce qui rend le rejeu après timeout sûr. Chaque
voie de chauffe donne un enregistrement.
Les modèles ``x_electrical_control`` et ``x_heating_measurement`` ont été créés par Objectif-PI
(Florent Loirat) le 29/09/2026 sur la base ``qhse_test`` ; l'OF est ``mrp.manufacturingorder``.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from api.client import OpenProdAPIClient, OpenProdError, OpenProdUnavailable
from api.models import ControlData, ElectricalControlData, HeatControlData
from core.labels import load_json
from core.logger import setup_logger

logger = setup_logger(__name__)

Frame = Sequence[Sequence[str]]
DEFAULT_DEDUPE = {'electrical': ['serial_number', 'datetime'], 'heat': ['serial_number', 'datetime', 'way_number']}
CASTS = {'int': int, 'float': float, 'str': str, 'bool': bool}


@dataclass
class PublishResult:
    ok: bool
    ids: List[int] = field(default_factory=list)
    error: Optional[str] = None
    transient: bool = False   # True = panne passagère, la donnée doit être rejouée
    duplicate: bool = False   # True = déjà présent dans Open Prod, rien créé
    warning: Optional[str] = None  # créé, mais incomplet (ex. OF introuvable, lien non posé)


@dataclass
class Relation:
    """Many2one Open Prod résolu par recherche : ``search_field = <valeur de l'attribut Keck3>``."""
    field: str
    model: str
    search_field: str = 'name'
    required: bool = False

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> 'Relation':
        return cls(field=str(raw['field']), model=str(raw['model']),
                   search_field=str(raw.get('search_field', 'name')), required=bool(raw.get('required', False)))


@dataclass
class TargetMapping:
    model: str
    fields: Dict[str, str]
    constants: Dict[str, Any] = field(default_factory=dict)
    raw_frame_field: Optional[str] = None
    datetime_format: str = '%Y-%m-%d %H:%M:%S'
    dedupe_on: List[str] = field(default_factory=list)
    casts: Dict[str, str] = field(default_factory=dict)
    relations: Dict[str, Relation] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, kind: str, raw: Dict[str, Any]) -> 'TargetMapping':
        fields = {str(k): str(v) for k, v in raw.get('fields', {}).items()}
        dedupe_on = [str(a) for a in raw.get('dedupe_on', DEFAULT_DEDUPE.get(kind, []))]
        casts = {str(k): str(v) for k, v in raw.get('casts', {}).items()}
        unknown = [c for c in casts.values() if c not in CASTS]
        if unknown:
            raise ValueError(f"casts inconnus {unknown} (attendus : {', '.join(CASTS)})")
        relations = {str(k): Relation.from_dict(v) for k, v in raw.get('relations', {}).items()}
        return cls(
            model=str(raw['model']),
            fields=fields,
            constants=dict(raw.get('constants', {})),
            raw_frame_field=raw.get('raw_frame_field'),
            datetime_format=raw.get('datetime_format', '%Y-%m-%d %H:%M:%S'),
            dedupe_on=[a for a in dedupe_on if a in fields],
            casts=casts,
            relations=relations,
        )

    def _format(self, attribute: str, value: Any) -> Any:
        if hasattr(value, 'strftime'):
            value = value.strftime(self.datetime_format)
        cast = self.casts.get(attribute)
        return CASTS[cast](value) if cast else value

    @staticmethod
    def _attribute(control: ControlData, attribute: str) -> Any:
        available = control.as_dict()
        if attribute not in available:
            raise OpenProdError(f"Mapping invalide: attribut Keck3 inconnu '{attribute}'")
        return available[attribute]

    def values_for(self, control: ControlData, frame: Optional[Frame] = None) -> Dict[str, Any]:
        """Construit les valeurs Open Prod d'un contrôle selon le mapping (hors relations)."""
        values: Dict[str, Any] = dict(self.constants)
        for attribute, target in self.fields.items():
            values[target] = self._format(attribute, self._attribute(control, attribute))
        if self.raw_frame_field and frame is not None:
            values[self.raw_frame_field] = '\n'.join(' '.join(line) for line in frame)
        return values

    def relation_filters(self, control: ControlData) -> List[Tuple[str, Relation, List[List[Any]]]]:
        """Pour chaque relation : (attribut, relation, domaine de recherche de l'enregistrement lié)."""
        return [(attribute, relation, [[relation.search_field, '=', self._attribute(control, attribute)]])
                for attribute, relation in self.relations.items()]

    def dedupe_filters(self, control: ControlData) -> List[List[Any]]:
        """Domaine Odoo identifiant ce contrôle ; vide si le mapping ne permet pas de le reconnaître."""
        if len(self.dedupe_on) < 2:
            return []
        return [[self.fields[attr], '=', self._format(attr, self._attribute(control, attr))] for attr in self.dedupe_on]


def load_mappings(path: Path) -> Dict[str, TargetMapping]:
    """Charge le fichier de mapping ; absent ou invalide → aucun type configuré (avec log)."""
    raw = load_json(path, None)
    if raw is None:
        logger.warning(f"Mapping Open Prod absent ({path}) : aucune donnée ne sera envoyée")
        return {}
    if not isinstance(raw, dict):
        logger.error(f"{path}: un objet JSON {{electrical: ..., heat: ...}} est attendu")
        return {}
    mappings: Dict[str, TargetMapping] = {}
    for kind in ('electrical', 'heat'):
        item = raw.get(kind)
        if isinstance(item, dict) and item.get('model'):
            try:
                mappings[kind] = TargetMapping.from_dict(kind, item)
            except (TypeError, ValueError, AttributeError, KeyError) as e:
                logger.error(f"{path}: mapping '{kind}' ignoré ({e})")
                continue
            if not mappings[kind].dedupe_on:
                logger.warning(f"Mapping '{kind}': pas de dedupe_on exploitable, un rejeu après timeout peut créer un doublon")
    logger.info(f"Mapping Open Prod chargé: {', '.join(mappings) or 'aucun type'}")
    return mappings


class ControlPublisher:
    """Envoie les contrôles électriques et de chauffe à Open Prod selon le mapping."""

    def __init__(self, client: OpenProdAPIClient, mapping_path: Path):
        self.client = client
        self.mapping_path = Path(mapping_path)
        self.mappings: Dict[str, TargetMapping] = load_mappings(self.mapping_path)

    @property
    def is_configured(self) -> bool:
        return bool(self.mappings)

    def publish(self, kind: str, control: ControlData, frame: Optional[Frame] = None) -> PublishResult:
        """Crée l'enregistrement s'il n'existe pas déjà. Aucun rejeu HTTP interne : c'est la file qui rejoue."""
        mapping = self.mappings.get(kind)
        if mapping is None:
            return PublishResult(ok=False, error=f"Mapping Open Prod non configuré pour '{kind}'")
        try:
            filters = mapping.dedupe_filters(control)
            if filters:
                existing = self.client.read(mapping.model, filters, fields=['id'], limit=1, retry=False)
                if existing:
                    found = existing[0].get('id') if isinstance(existing[0], dict) else existing[0]
                    logger.info(f"{kind} {control.serial_number} déjà présent dans Open Prod (id {found})")
                    return PublishResult(ok=True, ids=[found], duplicate=True)
            values = mapping.values_for(control, frame)
            warnings = self._resolve_relations(mapping, control, values)
            ids = self.client.create(mapping.model, values, retry=False)
        except OpenProdUnavailable as e:
            return PublishResult(ok=False, error=str(e), transient=True)
        except OpenProdError as e:
            return PublishResult(ok=False, error=str(e))
        if not ids:
            return PublishResult(ok=False, error="Open Prod n'a renvoyé aucun identifiant")
        return PublishResult(ok=True, ids=ids, warning='; '.join(warnings) or None)

    def _resolve_relations(self, mapping: TargetMapping, control: ControlData, values: Dict[str, Any]) -> List[str]:
        """Renseigne les many2one par recherche ; renvoie les avertissements (liens optionnels non trouvés)."""
        warnings: List[str] = []
        for attribute, relation, filters in mapping.relation_filters(control):
            wanted = filters[0][2]
            found = self.client.read(relation.model, filters, fields=['id'], limit=1, retry=False)
            if found:
                values[relation.field] = found[0].get('id') if isinstance(found[0], dict) else found[0]
                continue
            message = f"{relation.model} '{wanted}' introuvable dans Open Prod ({attribute} → {relation.field})"
            if relation.required:
                raise OpenProdError(message)
            logger.warning(f"{control.serial_number}: {message}, enregistrement créé sans ce lien")
            warnings.append(message)
        return warnings

    def publish_electrical(self, control: ElectricalControlData, frame: Optional[Frame] = None) -> PublishResult:
        return self.publish('electrical', control, frame)

    def publish_heat(self, ways: Sequence[HeatControlData],
                     frame: Optional[Frame] = None) -> List[Tuple[HeatControlData, PublishResult]]:
        """Un enregistrement par voie ; chaque voie a son propre résultat."""
        return [(way, self.publish('heat', way, frame)) for way in ways]
