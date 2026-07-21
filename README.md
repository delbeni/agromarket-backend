# AgroMarket - Backend Compte Producteur

## Installation locale
pip install -r requirements.txt --break-system-packages
cd app
python3 main.py

Le serveur démarre sur http://localhost:5050

## Endpoints disponibles

### Producteurs
- POST /api/producteurs/inscription  -> créer un compte producteur
- POST /api/producteurs/connexion    -> se connecter
- GET  /api/producteurs/<id>         -> voir un profil
- PUT  /api/producteurs/<id>         -> modifier un profil
- GET  /api/producteurs?pays=Mali    -> lister les producteurs (filtrable par pays)

### Produits
- POST /api/producteurs/<id>/produits -> ajouter un produit
- GET  /api/producteurs/<id>/produits -> produits d'un producteur
- PUT  /api/produits/<id>              -> modifier un produit
- GET  /api/produits                   -> catalogue public (filtres: pays, ville, categorie)

## Pays couverts actuellement
Côte d'Ivoire, Mali, Burkina Faso, Sénégal
(ajoutable facilement dans main.py -> PAYS_AUTORISES)

## Catégories de produits
cereales, elevage, maraichage, transforme
(ajoutable dans main.py -> CATEGORIES)

## Prochaines étapes
1. Compte acheteur ✅ fait
2. Système de messagerie avec filtre anti-contournement ✅ fait
3. Système de commande + calcul commission (modèle Commande déjà prêt)
4. Intégration paiement CinetPay/PayDunya
5. Déployer sur Render (voir ci-dessous)
6. Construire l'app mobile réelle (Expo/React Native) connectée à ce serveur

## Déploiement sur Render (comme ton projet tradecopier)

1. Crée un nouveau repo GitHub (ex: `delbeni/agromarket-backend`) et pousse ces fichiers dedans.
2. Sur Render.com : "New +" -> "Web Service" -> connecte ce repo.
3. Render détecte automatiquement le `Procfile`. Configure :
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: (déjà dans le Procfile, rien à changer)
4. Clique "Create Web Service". Render te donne une URL du type `agromarket-backend.onrender.com`.

⚠️ **Important** : sur le plan gratuit de Render, le système de fichiers est effacé à chaque redéploiement — donc la base SQLite (`agromarket.db`) sera réinitialisée. Pour un vrai lancement, il faudra migrer vers PostgreSQL (Render propose une base PostgreSQL gratuite séparée). On fera cette migration juste avant le vrai lancement commercial — pas la peine maintenant pendant qu'on teste.

