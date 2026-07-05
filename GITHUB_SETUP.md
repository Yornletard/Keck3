# Configuration GitHub pour Keck3

## Étape 1 : Créer le repo GitHub

1. Aller sur https://github.com/new
2. Nom du repo : `Keck3`
3. Description : `Test Control Data Acquisition System - Direct integration with Open Prod ERP`
4. Visibilité : **Public** (pour le déploiement facile)
5. Cliquer "Create repository"

Copier l'URL du repo (ex: `https://github.com/Yornletard/Keck3.git`)

## Étape 2 : Ajouter le remote et pousser

```bash
cd /Users/yornletard/Sites/Keck3

# Ajouter le remote
git remote add origin https://github.com/Yornletard/Keck3.git

# Vérifier
git remote -v

# Pousser la branche main
git branch -M main
git push -u origin main
```

Si demande d'authentification pour HTTPS :
- Utiliser votre GitHub username
- Utiliser un Personal Access Token comme mot de passe (Settings → Developer Settings → Personal Access Tokens)

## Étape 3 : Vérifier

Ouvrir https://github.com/Yornletard/Keck3 - le code devrait être là.

## Auto-update configuré

Une fois le repo GitHub configuré, Keck3 pourra :
1. Vérifier les mises à jour automatiquement (chaque 5 min)
2. Télécharger depuis le repo avec `git pull`
3. Réinstaller les dépendances si besoin
4. Redémarrer automatiquement

Aucune intervention de l'utilisateur n'est nécessaire !

## Secrets (à ne pas committer)

`.env` contient :
- `OPEN_PROD_API_KEY` → À configurer à la main
- Pas de tokens GitHub stockés

Ajouter à `.gitignore` si manquant :
```
.env
venv/
*.pyc
__pycache__/
logs/
```

C'est déjà fait ! ✓
