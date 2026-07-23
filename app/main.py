from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, Producteur, Produit, Acheteur, Commande, Message
import os
import re
import json

app = Flask(__name__)
CORS(app)

basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(basedir, 'agromarket.db')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

with app.app_context():
    db.create_all()

PAYS_AUTORISES = ["Côte d'Ivoire", "Mali", "Burkina Faso", "Sénégal"]
CATEGORIES = ["cereales", "elevage", "maraichage", "transforme"]

# ---------- FILTRE ANTI-CONTOURNEMENT ----------

# Détecte les numéros de téléphone même écrits avec espaces, points, tirets,
# ou en toutes lettres ("zéro sept"), et les mots-clés incitant à sortir de l'app.
REGEX_NUMERO = re.compile(r"(\d[\s.\-]?){8,}")
MOTS_CLES_CONTOURNEMENT = [
    "whatsapp", "whats app", "appelle moi", "appelle-moi", "mon numero",
    "mon numéro", "contact direct", "en dehors de l'app", "hors application",
    "virement direct", "paiement direct", "espece", "espèces directement",
]


def filtrer_message(texte):
    """Retourne (texte_filtré, contient_infraction)."""
    contient_infraction = False
    texte_filtre = texte

    if REGEX_NUMERO.search(texte):
        contient_infraction = True
        texte_filtre = REGEX_NUMERO.sub("[numéro masqué]", texte_filtre)

    texte_lower = texte_filtre.lower()
    for mot in MOTS_CLES_CONTOURNEMENT:
        if mot in texte_lower:
            contient_infraction = True
            texte_filtre = re.sub(re.escape(mot), "[message modéré]", texte_filtre, flags=re.IGNORECASE)

    return texte_filtre, contient_infraction


# ---------- PRODUCTEURS ----------

@app.route("/api/producteurs/inscription", methods=["POST"])
def inscription_producteur():
    data = request.get_json()

    champs_requis = ["nom", "telephone", "mot_de_passe", "pays", "ville"]
    manquants = [c for c in champs_requis if not data.get(c)]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400

    if data["pays"] not in PAYS_AUTORISES:
        return jsonify({"erreur": f"Pays non couvert. Pays disponibles: {', '.join(PAYS_AUTORISES)}"}), 400

    if Producteur.query.filter_by(telephone=data["telephone"]).first():
        return jsonify({"erreur": "Ce numéro de téléphone est déjà enregistré"}), 409

    producteur = Producteur(
        nom=data["nom"],
        telephone=data["telephone"],
        mot_de_passe_hash=generate_password_hash(data["mot_de_passe"]),
        pays=data["pays"],
        ville=data["ville"],
        zone_livraison=data.get("zone_livraison", ""),
        type_production=data.get("type_production", ""),
        description=data.get("description", ""),
        photo_url=data.get("photo_url", ""),
        histoire=data.get("histoire", ""),
    )
    db.session.add(producteur)
    db.session.commit()

    return jsonify({"message": "Compte producteur créé", "producteur": producteur.to_dict()}), 201


@app.route("/api/producteurs/connexion", methods=["POST"])
def connexion_producteur():
    data = request.get_json()
    producteur = Producteur.query.filter_by(telephone=data.get("telephone")).first()

    if not producteur or not check_password_hash(producteur.mot_de_passe_hash, data.get("mot_de_passe", "")):
        return jsonify({"erreur": "Téléphone ou mot de passe incorrect"}), 401

    return jsonify({"message": "Connexion réussie", "producteur": producteur.to_dict()}), 200


@app.route("/api/producteurs/<int:producteur_id>", methods=["GET"])
def obtenir_producteur(producteur_id):
    producteur = Producteur.query.get_or_404(producteur_id)
    return jsonify(producteur.to_dict())


@app.route("/api/producteurs/<int:producteur_id>", methods=["PUT"])
def modifier_producteur(producteur_id):
    producteur = Producteur.query.get_or_404(producteur_id)
    data = request.get_json()

    for champ in ["nom", "pays", "ville", "zone_livraison", "type_production", "description", "photo_url", "histoire"]:
        if champ in data:
            setattr(producteur, champ, data[champ])

    db.session.commit()
    return jsonify({"message": "Profil mis à jour", "producteur": producteur.to_dict()})


@app.route("/api/producteurs", methods=["GET"])
def lister_producteurs():
    pays = request.args.get("pays")
    query = Producteur.query.filter_by(actif=True)
    if pays:
        query = query.filter_by(pays=pays)
    producteurs = query.all()
    return jsonify([p.to_dict() for p in producteurs])


# ---------- PRODUITS ----------

@app.route("/api/producteurs/<int:producteur_id>/produits", methods=["POST"])
def ajouter_produit(producteur_id):
    Producteur.query.get_or_404(producteur_id)
    data = request.get_json()

    champs_requis = ["nom", "categorie", "prix_unitaire", "quantite_disponible"]
    manquants = [c for c in champs_requis if data.get(c) is None]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400

    if data["categorie"] not in CATEGORIES:
        return jsonify({"erreur": f"Catégorie invalide. Options: {', '.join(CATEGORIES)}"}), 400

    photos_urls = data.get("photos_urls", [])
    if not isinstance(photos_urls, list):
        photos_urls = []
    photos_urls = photos_urls[:4]  # limite à 4 photos
    photo_couverture = photos_urls[0] if photos_urls else data.get("photo_url", "")

    produit = Produit(
        producteur_id=producteur_id,
        nom=data["nom"],
        categorie=data["categorie"],
        prix_unitaire=data["prix_unitaire"],
        unite=data.get("unite", "unité"),
        quantite_disponible=data["quantite_disponible"],
        photo_url=photo_couverture,
        photos_urls=json.dumps(photos_urls),
        video_url=data.get("video_url", ""),
        description=data.get("description", ""),
    )
    db.session.add(produit)
    db.session.commit()

    return jsonify({"message": "Produit ajouté", "produit": produit.to_dict()}), 201


@app.route("/api/producteurs/<int:producteur_id>/produits", methods=["GET"])
def produits_du_producteur(producteur_id):
    Producteur.query.get_or_404(producteur_id)
    produits = Produit.query.filter_by(producteur_id=producteur_id).all()
    return jsonify([p.to_dict() for p in produits])


@app.route("/api/produits/<int:produit_id>", methods=["PUT"])
def modifier_produit(produit_id):
    produit = Produit.query.get_or_404(produit_id)
    data = request.get_json()

    if "photos_urls" in data:
        photos_urls = data["photos_urls"]
        if not isinstance(photos_urls, list):
            photos_urls = []
        photos_urls = photos_urls[:4]
        produit.photos_urls = json.dumps(photos_urls)
        if photos_urls:
            produit.photo_url = photos_urls[0]

    for champ in ["nom", "prix_unitaire", "unite", "quantite_disponible", "photo_url", "video_url", "description", "actif"]:
        if champ in data:
            setattr(produit, champ, data[champ])

    db.session.commit()
    return jsonify({"message": "Produit mis à jour", "produit": produit.to_dict()})


@app.route("/api/produits", methods=["GET"])
def lister_produits():
    """Catalogue public - pour les acheteurs. Filtrable par pays, catégorie, ville."""
    query = Produit.query.filter_by(actif=True)

    categorie = request.args.get("categorie")
    if categorie:
        query = query.filter_by(categorie=categorie)

    produits = query.all()

    pays = request.args.get("pays")
    ville = request.args.get("ville")
    resultats = []
    for p in produits:
        if pays and p.producteur.pays != pays:
            continue
        if ville and p.producteur.ville != ville:
            continue
        resultats.append(p.to_dict())

    return jsonify(resultats)


@app.route("/api/acheteurs/inscription", methods=["POST"])
def inscription_acheteur():
    data = request.get_json()

    champs_requis = ["nom", "telephone", "mot_de_passe", "pays", "ville"]
    manquants = [c for c in champs_requis if not data.get(c)]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400

    if Acheteur.query.filter_by(telephone=data["telephone"]).first():
        return jsonify({"erreur": "Ce numéro de téléphone est déjà enregistré"}), 409

    acheteur = Acheteur(
        nom=data["nom"],
        telephone=data["telephone"],
        mot_de_passe_hash=generate_password_hash(data["mot_de_passe"]),
        pays=data["pays"],
        ville=data["ville"],
        adresse_livraison=data.get("adresse_livraison", ""),
    )
    db.session.add(acheteur)
    db.session.commit()

    return jsonify({"message": "Compte acheteur créé", "acheteur": acheteur.to_dict()}), 201


@app.route("/api/acheteurs/connexion", methods=["POST"])
def connexion_acheteur():
    data = request.get_json()
    acheteur = Acheteur.query.filter_by(telephone=data.get("telephone")).first()

    if not acheteur or not check_password_hash(acheteur.mot_de_passe_hash, data.get("mot_de_passe", "")):
        return jsonify({"erreur": "Téléphone ou mot de passe incorrect"}), 401

    return jsonify({"message": "Connexion réussie", "acheteur": acheteur.to_dict()}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


# ---------- MESSAGERIE (avec filtre anti-contournement) ----------

@app.route("/api/messages", methods=["POST"])
def envoyer_message():
    data = request.get_json()

    champs_requis = ["acheteur_id", "producteur_id", "expediteur_type", "contenu"]
    manquants = [c for c in champs_requis if not data.get(c)]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400

    if data["expediteur_type"] not in ("acheteur", "producteur"):
        return jsonify({"erreur": "expediteur_type doit être 'acheteur' ou 'producteur'"}), 400

    Acheteur.query.get_or_404(data["acheteur_id"])
    Producteur.query.get_or_404(data["producteur_id"])

    contenu_filtre, contient_infraction = filtrer_message(data["contenu"])

    message = Message(
        acheteur_id=data["acheteur_id"],
        producteur_id=data["producteur_id"],
        produit_id=data.get("produit_id"),
        expediteur_type=data["expediteur_type"],
        contenu_original=data["contenu"],
        contenu_filtre=contenu_filtre,
        contient_infraction=contient_infraction,
    )
    db.session.add(message)
    db.session.commit()

    reponse = {"message": message.to_dict()}
    if contient_infraction:
        reponse["avertissement"] = (
            "Pour ta sécurité et pour garantir le suivi de la commande, "
            "les échanges de coordonnées ou de paiement en dehors de l'application ne sont pas autorisés."
        )

    return jsonify(reponse), 201


@app.route("/api/messages/conversation", methods=["GET"])
def obtenir_conversation():
    """Récupère l'historique entre un acheteur et un producteur (filtré, jamais brut)."""
    acheteur_id = request.args.get("acheteur_id", type=int)
    producteur_id = request.args.get("producteur_id", type=int)

    if not acheteur_id or not producteur_id:
        return jsonify({"erreur": "acheteur_id et producteur_id requis"}), 400

    messages = (
        Message.query.filter_by(acheteur_id=acheteur_id, producteur_id=producteur_id)
        .order_by(Message.date_envoi.asc())
        .all()
    )
    return jsonify([m.to_dict() for m in messages])


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    port = int(os.environ.get("PORT", 5050))
    app.run(debug=True, host="0.0.0.0", port=port, use_reloader=False)
