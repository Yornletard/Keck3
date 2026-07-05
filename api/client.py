import requests
from typing import Dict, Any, Optional
from core.logger import setup_logger
from config import OPEN_PROD_BASE_URL, OPEN_PROD_API_KEY, MAX_RETRIES, RETRY_DELAY
import time

logger = setup_logger(__name__)

class OpenProdAPIClient:
    """Client pour communiquer avec l'API Open Prod."""

    def __init__(self, base_url: str = OPEN_PROD_BASE_URL, api_key: str = OPEN_PROD_API_KEY):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        })

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None,
                     attempt: int = 1) -> Optional[Dict[str, Any]]:
        """Effectue une requête HTTP avec retry automatique."""
        url = f"{self.base_url}{endpoint}"

        try:
            logger.debug(f"Requête {method} vers {url}")

            if method.upper() == 'POST':
                response = self.session.post(url, json=data, timeout=10)
            elif method.upper() == 'GET':
                response = self.session.get(url, timeout=10)
            else:
                logger.error(f"Méthode non supportée: {method}")
                return None

            if response.status_code in [200, 201, 202]:
                logger.info(f"Requête {method} {endpoint} réussie")
                try:
                    return response.json()
                except:
                    return {'status': 'success', 'statusCode': response.status_code}

            elif response.status_code == 401:
                logger.error("Authentification échouée - clé API invalide")
                return None

            elif response.status_code == 404:
                logger.warning(f"Ressource non trouvée: {endpoint}")
                return None

            else:
                logger.warning(f"Statut HTTP {response.status_code}: {response.text}")
                if attempt < MAX_RETRIES:
                    logger.info(f"Nouvelle tentative ({attempt + 1}/{MAX_RETRIES}) dans {RETRY_DELAY}s...")
                    time.sleep(RETRY_DELAY)
                    return self._make_request(method, endpoint, data, attempt + 1)
                return None

        except requests.Timeout:
            logger.error(f"Timeout lors de la requête vers {url}")
            if attempt < MAX_RETRIES:
                logger.info(f"Nouvelle tentative ({attempt + 1}/{MAX_RETRIES}) dans {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                return self._make_request(method, endpoint, data, attempt + 1)
            return None

        except requests.ConnectionError as e:
            logger.error(f"Erreur de connexion vers {url}: {e}")
            if attempt < MAX_RETRIES:
                logger.info(f"Nouvelle tentative ({attempt + 1}/{MAX_RETRIES}) dans {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                return self._make_request(method, endpoint, data, attempt + 1)
            return None

        except Exception as e:
            logger.error(f"Erreur lors de la requête: {e}")
            return None

    def post_electrical_control(self, data: Dict[str, Any]) -> Optional[Dict]:
        """Envoie des données de contrôle électrique."""
        return self._make_request('POST', '/api/machinedata/electricalcontrol', data)

    def post_heat_control(self, data: Dict[str, Any]) -> Optional[Dict]:
        """Envoie des données de contrôle thermique."""
        return self._make_request('POST', '/api/machinedata/heatcontrol', data)

    def get_machine(self, machine_id: str) -> Optional[Dict]:
        """Récupère les infos d'une machine."""
        return self._make_request('GET', f'/api/machines/{machine_id}')

    def create_machine(self, machine_data: Dict[str, Any]) -> Optional[Dict]:
        """Crée une nouvelle machine."""
        return self._make_request('POST', '/api/machines', machine_data)

    def close(self):
        """Ferme la session."""
        self.session.close()
        logger.info("Session API fermée")
