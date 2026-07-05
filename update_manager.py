#!/usr/bin/env python
"""
Gestionnaire de mises à jour Keck3
Utilise git pour télécharger les mises à jour depuis le repo GitHub
"""

import subprocess
import os
from pathlib import Path
from datetime import datetime
from typing import Tuple, Optional
from core.logger import setup_logger

logger = setup_logger(__name__)

class UpdateManager:
    """Gère les mises à jour via git pull."""

    def __init__(self, repo_dir: str = None):
        self.repo_dir = Path(repo_dir or os.getcwd())
        self.git_dir = self.repo_dir / '.git'

    def is_git_repo(self) -> bool:
        """Vérifie si c'est un repo git."""
        return self.git_dir.exists()

    def get_remote_url(self) -> Optional[str]:
        """Récupère l'URL du remote."""
        try:
            result = subprocess.run(
                ['git', '-C', str(self.repo_dir), 'config', '--get', 'remote.origin.url'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception as e:
            logger.error(f"Erreur récupération URL remote: {e}")
            return None

    def check_updates(self) -> bool:
        """Vérifie s'il y a des mises à jour disponibles."""
        if not self.is_git_repo():
            logger.warning("Pas un repo git, vérification des mises à jour désactivée")
            return False

        try:
            # Fetch depuis le remote (sans pulls)
            logger.debug("Vérification des mises à jour (git fetch)...")
            result = subprocess.run(
                ['git', '-C', str(self.repo_dir), 'fetch', '--quiet'],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                logger.warning(f"Erreur fetch: {result.stderr}")
                return False

            # Vérifier si il y a des commits en avance
            result = subprocess.run(
                ['git', '-C', str(self.repo_dir), 'rev-list', '--count', 'HEAD..origin/main'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                logger.debug("Impossible de comparer, probablement pas de remote")
                return False

            commits_behind = int(result.stdout.strip())
            if commits_behind > 0:
                logger.info(f"Mises à jour disponibles: {commits_behind} commit(s)")
                return True

            logger.debug("Déjà à jour")
            return False

        except subprocess.TimeoutExpired:
            logger.warning("Timeout lors de la vérification des mises à jour")
            return False
        except Exception as e:
            logger.error(f"Erreur vérification mises à jour: {e}")
            return False

    def apply_update(self, restart_callback=None) -> bool:
        """Applique les mises à jour (git pull)."""
        if not self.is_git_repo():
            logger.error("Pas un repo git, update impossible")
            return False

        try:
            logger.info("Téléchargement des mises à jour...")

            # Git pull
            result = subprocess.run(
                ['git', '-C', str(self.repo_dir), 'pull', '--quiet'],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                logger.error(f"Erreur git pull: {result.stderr}")
                return False

            logger.info("✓ Mises à jour appliquées avec succès")

            # Reinstaller les dépendances si besoin
            if (self.repo_dir / 'requirements.txt').exists():
                logger.info("Mise à jour des dépendances...")
                try:
                    subprocess.run(
                        ['pip', 'install', '--quiet', '-r', str(self.repo_dir / 'requirements.txt')],
                        capture_output=True,
                        timeout=60
                    )
                    logger.info("✓ Dépendances à jour")
                except Exception as e:
                    logger.warning(f"Erreur update dépendances: {e}")

            # Redémarrer si callback fourni
            if restart_callback:
                logger.info("Redémarrage de l'application...")
                restart_callback()

            return True

        except subprocess.TimeoutExpired:
            logger.error("Timeout lors du pull")
            return False
        except Exception as e:
            logger.error(f"Erreur apply_update: {e}")
            return False

    def get_current_version(self) -> Optional[str]:
        """Retourne le hash du commit courant."""
        try:
            result = subprocess.run(
                ['git', '-C', str(self.repo_dir), 'rev-parse', '--short', 'HEAD'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception as e:
            logger.error(f"Erreur get_current_version: {e}")
            return None

    def get_latest_version(self) -> Optional[str]:
        """Retourne le hash du latest commit du remote."""
        try:
            result = subprocess.run(
                ['git', '-C', str(self.repo_dir), 'rev-parse', '--short', 'origin/main'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            return None

    def get_version_info(self) -> dict:
        """Retourne les infos de version."""
        return {
            'current': self.get_current_version(),
            'latest': self.get_latest_version(),
            'remote': self.get_remote_url(),
            'is_git_repo': self.is_git_repo(),
            'has_updates': self.check_updates(),
            'timestamp': datetime.now().isoformat(),
        }

def check_and_update():
    """Fonction utilitaire pour vérifier et updater."""
    manager = UpdateManager()

    if not manager.is_git_repo():
        logger.warning("Pas un repo git, updates désactivées")
        return False

    if manager.check_updates():
        logger.info("Mises à jour disponibles, application...")
        return manager.apply_update()

    return False

if __name__ == '__main__':
    manager = UpdateManager()
    info = manager.get_version_info()

    print("Informations de version:")
    print(f"  Courant  : {info['current']}")
    print(f"  Remote   : {info['latest']}")
    print(f"  URL      : {info['remote']}")
    print(f"  Git repo : {info['is_git_repo']}")
    print(f"  Updates  : {'Oui' if info['has_updates'] else 'Non'}")
