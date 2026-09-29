"""Client de l'API Open Prod (ERP dérivé d'Odoo, éditeur Objectif-PI).

Protocole (doc ``web.controllers.openprod_api``) : API générique par modèle.

- ``POST /web/api/getToken``  ``{"db", "id_secret"}`` → ``result.data`` = jeton temporaire.
- ``POST /web/api/endpoint``  ``{"db", "token", "method", "model", ...}`` avec ``method`` parmi
  ``read``, ``create``, ``update``, ``delete``, ``read_fields``, ``read_model``, ``read_wkf``,
  ``wkf``, ``call_kw``, ``read_token``.
- ``create`` : ``"values": [["champ", valeur], ...]`` (un seul objet par appel) → ``result.data`` = ids.
- ``read`` : ``"filters": [["champ", "=", valeur], ...]`` (domaine Odoo), ``fields``, ``limit``, ``order``.
- Réponse JSON-RPC : ``{"jsonrpc": "2.0", "result": {"data": ...}}`` ou ``{"result": {"error": {"message": ...}}}``
  (HTTP 400 en cas d'erreur). La doc ne distingue pas un jeton expiré d'un autre refus.
"""

import time
from typing import Any, Dict, List, Optional, Sequence, Union

import requests

from core.logger import setup_logger
from config import (
    OPEN_PROD_BASE_URL, OPEN_PROD_DB, OPEN_PROD_API_KEY,
    OPEN_PROD_TOKEN_PATH, OPEN_PROD_ENDPOINT_PATH, OPEN_PROD_VERIFY_TLS,
    MAX_RETRIES, RETRY_DELAY, REQUEST_TIMEOUT,
)

logger = setup_logger(__name__)

RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}

Values = Union[Dict[str, Any], Sequence[Sequence[Any]]]


class OpenProdError(Exception):
    """Refus d'Open Prod (paramètre invalide, droits, modèle inconnu) : rejouer ne changera rien."""


class OpenProdUnavailable(Exception):
    """Panne passagère (réseau, timeout, 5xx) : la requête peut être rejouée."""


def values_to_pairs(values: Values) -> List[List[Any]]:
    """Convertit un dict en liste de paires ``[champ, valeur]`` attendue par ``create``/``update``."""
    if isinstance(values, dict):
        return [[key, value] for key, value in values.items()]
    return [list(pair) for pair in values]


def _as_list(data: Any) -> List[Any]:
    """``result.data`` normalisé en liste : ``None``/``False`` → vide, scalaire → ``[scalaire]``."""
    if data is None or data is False:
        return []
    if isinstance(data, (list, tuple)):
        return list(data)
    return [data]


class OpenProdAPIClient:
    """Client HTTP Open Prod avec jeton renouvelé automatiquement et retry sur pannes passagères.

    Les écritures non idempotentes (``create``) sont appelées avec ``retry=False`` par le
    publisher : c'est la file locale qui rejoue, après avoir vérifié l'absence de doublon.
    """

    def __init__(self, base_url: str = OPEN_PROD_BASE_URL, db: str = OPEN_PROD_DB,
                 id_secret: str = OPEN_PROD_API_KEY, verify_tls: bool = OPEN_PROD_VERIFY_TLS):
        self.base_url = base_url.rstrip('/')
        self.db = db
        self.id_secret = id_secret
        self.token: Optional[str] = None
        self.last_error: Optional[str] = None
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json', 'Accept': 'application/json'})
        self.session.verify = verify_tls
        if not verify_tls:
            requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

    # ------------------------------------------------------------------ HTTP
    def _post(self, path: str, payload: Dict[str, Any], retry: bool = True) -> Dict[str, Any]:
        """POST JSON ; renvoie ``result`` ou lève OpenProdError / OpenProdUnavailable.

        ``retry=False`` pour une écriture non idempotente : un timeout est signalé tout de
        suite plutôt que rejoué à l'aveugle (la file locale rejouera après vérification).
        """
        url = f"{self.base_url}{path}"
        last_failure = "panne inconnue"
        attempts = MAX_RETRIES if retry else 1

        for attempt in range(1, attempts + 1):
            try:
                logger.debug(f"POST {url} (tentative {attempt}/{attempts}) method={payload.get('method')} model={payload.get('model')}")
                response = self.session.post(url, json=payload, timeout=REQUEST_TIMEOUT)
            except requests.Timeout:
                last_failure = f"Timeout vers {url}"
            except requests.ConnectionError as e:
                last_failure = f"Connexion impossible vers {url}: {e}"
            except requests.RequestException as e:
                raise OpenProdUnavailable(f"Erreur HTTP: {e}") from e
            else:
                if response.status_code in RETRYABLE_STATUSES:
                    last_failure = f"HTTP {response.status_code}: {response.text[:200]}"
                else:
                    return self._parse(response)

            logger.warning(last_failure)
            if attempt < attempts:
                delay = RETRY_DELAY * attempt
                logger.info(f"Nouvelle tentative dans {delay}s...")
                time.sleep(delay)

        raise OpenProdUnavailable(last_failure)

    @staticmethod
    def _parse(response: requests.Response) -> Dict[str, Any]:
        try:
            body = response.json()
        except ValueError:
            raise OpenProdError(f"Réponse non JSON (HTTP {response.status_code}): {response.text[:200]}")

        result = body.get('result') if isinstance(body, dict) else None
        if isinstance(result, dict) and 'error' in result:
            error = result['error']
            message = error.get('message') if isinstance(error, dict) else str(error)
            raise OpenProdError(message or f"Erreur Open Prod (HTTP {response.status_code})")
        if isinstance(body, dict) and 'error' in body:  # erreur JSON-RPC standard Odoo (HTTP 200)
            error = body['error']
            message = error.get('message', '') if isinstance(error, dict) else str(error)
            data = error.get('data', {}) if isinstance(error, dict) else {}
            raise OpenProdError(f"{message}: {data.get('message', '')}".strip(': '))
        if response.status_code >= 400:
            raise OpenProdError(f"HTTP {response.status_code}: {response.text[:200]}")
        if not isinstance(result, dict):
            return {'data': result}
        return result

    # ----------------------------------------------------------------- token
    def get_token(self) -> str:
        """Obtient un nouveau jeton temporaire."""
        result = self._post(OPEN_PROD_TOKEN_PATH, {'db': self.db, 'id_secret': self.id_secret})
        token = result.get('data')
        if not token or not isinstance(token, str):
            raise OpenProdError("Jeton absent de la réponse getToken")
        self.token = token
        logger.info("Jeton Open Prod obtenu")
        return token

    def call(self, method: str, model: Optional[str] = None, retry: bool = True, **params) -> Any:
        """Appelle ``/web/api/endpoint`` et renvoie ``result.data``.

        Le message d'un jeton expiré n'étant pas documenté, tout refus est rejoué
        une fois avec un jeton neuf : un appel refusé n'a rien écrit, le rejeu est sûr.
        """
        self.last_error = None
        payload: Dict[str, Any] = {'db': self.db, 'method': method, **params}
        if model:
            payload['model'] = model

        try:
            if self.token is None:
                self.get_token()
            payload['token'] = self.token
            try:
                return self._post(OPEN_PROD_ENDPOINT_PATH, payload, retry).get('data')
            except OpenProdError as first_refusal:
                logger.info(f"Appel refusé ({first_refusal}), nouvel essai avec un jeton neuf")
                payload['token'] = self.get_token()
                return self._post(OPEN_PROD_ENDPOINT_PATH, payload, retry).get('data')
        except (OpenProdError, OpenProdUnavailable) as e:
            self.last_error = str(e)
            raise

    # --------------------------------------------------------------- helpers
    def create(self, model: str, values: Values, use_onchange: bool = True, retry: bool = True) -> List[int]:
        """Crée un enregistrement. ``use_onchange=True`` = onchanges NON appliqués (sens de la doc Open Prod)."""
        return _as_list(self.call('create', model, retry=retry, values=values_to_pairs(values), use_onchange=use_onchange))

    def read(self, model: str, filters: Optional[Sequence[Sequence[Any]]] = None,
             fields: Optional[Sequence[str]] = None, limit: Optional[int] = None,
             order: Optional[str] = None, retry: bool = True) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {'retry': retry, 'filters': [list(f) for f in (filters or [])]}
        if fields is not None:
            params['fields'] = list(fields)
        if limit is not None:
            params['limit'] = limit
        if order:
            params['order'] = order
        return _as_list(self.call('read', model, **params))

    def read_fields(self, model: str, fields: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
        """Liste les champs d'un modèle (pour valider un mapping avant la mise en prod)."""
        params: Dict[str, Any] = {}
        if fields is not None:
            params['fields'] = list(fields)
        return _as_list(self.call('read_fields', model, **params))

    def check_connection(self) -> bool:
        """Vrai si un jeton peut être obtenu (URL, base et clé valides)."""
        try:
            self.get_token()
            return True
        except (OpenProdError, OpenProdUnavailable) as e:
            self.last_error = str(e)
            logger.error(f"Connexion Open Prod impossible: {e}")
            return False

    def close(self) -> None:
        self.session.close()
        logger.info("Session API fermée")
