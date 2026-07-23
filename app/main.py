from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, Producteur, Produit, Acheteur, Commande, Message, Avis, Favori, TicketSupport, Livreur
import os
import re
import json
import secrets
import urllib.request
from datetime import datetime

app = Flask(__name__)
CORS(app)

basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(basedir, 'agromarket.db')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

with app.app_context():
    db.create_all()

PAYS_AUTORISES = ["Côte d'Ivoire", "Mali", "Burkina Faso", "Sénégal"]
CATEGORIES = ["cereales", "elevage", "maraichage", "transforme", "restaurant", "autre"]
STATUTS_COMMANDE = ["en_attente", "confirmee_producteur", "livree", "terminee", "annulee"]

LABELS_STATUT_COMMANDE = {
    "en_attente": "En attente",
    "confirmee_producteur": "Confirmée par le vendeur",
    "livree": "Livrée",
    "terminee": "Terminée",
    "annulee": "Annulée",
}

# Clé secrète d'accès au dashboard admin.
# IMPORTANT : change cette valeur par défaut via une variable d'environnement
# ADMIN_KEY sur Render (Settings > Environment), pour ne pas garder la valeur devinable.
ADMIN_KEY = os.environ.get("ADMIN_KEY", "agromarket_admin_2026")


def cle_admin_valide(req):
    return req.headers.get("X-Admin-Key") == ADMIN_KEY


def generer_code_parrainage():
    """Génère un code de parrainage court et unique."""
    while True:
        code = secrets.token_hex(3).upper()  # 6 caractères
        if not Producteur.query.filter_by(code_parrainage=code).first():
            return code


def envoyer_notification_push(token, titre, corps, donnees=None):
    """Envoie une notification push via le service Expo. Échoue silencieusement
    pour ne jamais bloquer la requête principale si le token est absent/invalide."""
    if not token:
        return
    payload = {
        "to": token,
        "title": titre,
        "body": corps,
        "data": donnees or {},
    }
    try:
        req = urllib.request.Request(
            "https://exp.host/--/api/v2/push/send",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


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

    code_saisi = (data.get("code_parrain_utilise") or "").strip().upper()
    parrain = Producteur.query.filter_by(code_parrainage=code_saisi).first() if code_saisi else None

    producteur = Producteur(
        nom=data["nom"],
        telephone=data["telephone"],
        mot_de_passe_hash=generate_password_hash(data["mot_de_passe"]),
        pays=data["pays"],
        ville=data["ville"],
        zone_livraison=data.get("zone_livraison", ""),
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        type_production=data.get("type_production", ""),
        description=data.get("description", ""),
        photo_url=data.get("photo_url", ""),
        histoire=data.get("histoire", ""),
        code_parrainage=generer_code_parrainage(),
        code_parrain_utilise=code_saisi if parrain else None,
    )
    db.session.add(producteur)
    db.session.commit()

    if parrain:
        parrain.nombre_filleuls = (parrain.nombre_filleuls or 0) + 1
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

    for champ in ["nom", "pays", "ville", "zone_livraison", "type_production", "description",
                  "photo_url", "histoire", "latitude", "longitude"]:
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


@app.route("/api/producteurs/<int:producteur_id>/push-token", methods=["PUT"])
def enregistrer_push_token_producteur(producteur_id):
    producteur = Producteur.query.get_or_404(producteur_id)
    data = request.get_json()
    producteur.push_token = data.get("push_token", "")
    db.session.commit()
    return jsonify({"message": "Jeton enregistré"})


# ---------- LIVREURS / TRANSPORTEURS ----------

@app.route("/api/livreurs/inscription", methods=["POST"])
def inscription_livreur():
    data = request.get_json()

    champs_requis = ["nom", "telephone", "mot_de_passe", "pays", "ville"]
    manquants = [c for c in champs_requis if not data.get(c)]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400

    if Livreur.query.filter_by(telephone=data["telephone"]).first():
        return jsonify({"erreur": "Ce numéro de téléphone est déjà enregistré"}), 409

    livreur = Livreur(
        nom=data["nom"],
        telephone=data["telephone"],
        mot_de_passe_hash=generate_password_hash(data["mot_de_passe"]),
        pays=data["pays"],
        ville=data["ville"],
        vehicule=data.get("vehicule", ""),
    )
    db.session.add(livreur)
    db.session.commit()

    return jsonify({"message": "Compte livreur créé", "livreur": livreur.to_dict()}), 201


@app.route("/api/livreurs/connexion", methods=["POST"])
def connexion_livreur():
    data = request.get_json()
    livreur = Livreur.query.filter_by(telephone=data.get("telephone")).first()

    if not livreur or not check_password_hash(livreur.mot_de_passe_hash, data.get("mot_de_passe", "")):
        return jsonify({"erreur": "Téléphone ou mot de passe incorrect"}), 401

    return jsonify({"message": "Connexion réussie", "livreur": livreur.to_dict()}), 200


@app.route("/api/livreurs/<int:livreur_id>", methods=["GET"])
def obtenir_livreur(livreur_id):
    livreur = Livreur.query.get_or_404(livreur_id)
    return jsonify(livreur.to_dict())


@app.route("/api/livreurs/<int:livreur_id>/push-token", methods=["PUT"])
def enregistrer_push_token_livreur(livreur_id):
    livreur = Livreur.query.get_or_404(livreur_id)
    data = request.get_json()
    livreur.push_token = data.get("push_token", "")
    db.session.commit()
    return jsonify({"message": "Jeton enregistré"})


@app.route("/api/livraisons-disponibles", methods=["GET"])
def livraisons_disponibles():
    """Commandes confirmées par le vendeur, pas encore prises en charge par un livreur."""
    commandes = (
        Commande.query.filter_by(statut="confirmee_producteur", livreur_id=None)
        .order_by(Commande.date_commande.asc())
        .all()
    )
    return jsonify([c.to_dict() for c in commandes])


@app.route("/api/livreurs/<int:livreur_id>/livraisons", methods=["GET"])
def livraisons_du_livreur(livreur_id):
    Livreur.query.get_or_404(livreur_id)
    commandes = (
        Commande.query.filter_by(livreur_id=livreur_id)
        .order_by(Commande.date_commande.desc())
        .all()
    )
    return jsonify([c.to_dict() for c in commandes])


@app.route("/api/commandes/<int:commande_id>/accepter-livraison", methods=["PUT"])
def accepter_livraison(commande_id):
    commande = Commande.query.get_or_404(commande_id)
    data = request.get_json()
    livreur_id = data.get("livreur_id")
    if not livreur_id:
        return jsonify({"erreur": "livreur_id requis"}), 400
    if commande.livreur_id:
        return jsonify({"erreur": "Cette livraison a déjà été prise en charge"}), 409

    Livreur.query.get_or_404(livreur_id)
    commande.livreur_id = livreur_id
    db.session.commit()

    if commande.acheteur:
        envoyer_notification_push(
            commande.acheteur.push_token,
            "Livreur en route",
            f"Un livreur a pris en charge ta commande « {commande.produit.nom if commande.produit else ''} ».",
        )

    return jsonify({"message": "Livraison acceptée", "commande": commande.to_dict()})


# ---------- AVIS ET NOTES VENDEURS ----------

@app.route("/api/producteurs/<int:producteur_id>/avis", methods=["POST"])
def ajouter_avis(producteur_id):
    Producteur.query.get_or_404(producteur_id)
    data = request.get_json()

    champs_requis = ["acheteur_id", "note"]
    manquants = [c for c in champs_requis if data.get(c) is None]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400

    note = data["note"]
    if not isinstance(note, int) or note < 1 or note > 5:
        return jsonify({"erreur": "La note doit être un entier entre 1 et 5"}), 400

    Acheteur.query.get_or_404(data["acheteur_id"])

    avis = Avis(
        producteur_id=producteur_id,
        acheteur_id=data["acheteur_id"],
        note=note,
        commentaire=data.get("commentaire", ""),
    )
    db.session.add(avis)
    db.session.commit()

    return jsonify({"message": "Avis publié", "avis": avis.to_dict()}), 201


@app.route("/api/producteurs/<int:producteur_id>/avis", methods=["GET"])
def lister_avis(producteur_id):
    Producteur.query.get_or_404(producteur_id)
    avis = Avis.query.filter_by(producteur_id=producteur_id).order_by(Avis.date_avis.desc()).all()
    return jsonify([a.to_dict() for a in avis])


# ---------- FAVORIS ----------

@app.route("/api/acheteurs/<int:acheteur_id>/favoris", methods=["GET"])
def lister_favoris(acheteur_id):
    Acheteur.query.get_or_404(acheteur_id)
    favoris = Favori.query.filter_by(acheteur_id=acheteur_id).all()
    return jsonify([f.produit.to_dict() for f in favoris if f.produit])


@app.route("/api/acheteurs/<int:acheteur_id>/favoris", methods=["POST"])
def ajouter_favori(acheteur_id):
    Acheteur.query.get_or_404(acheteur_id)
    data = request.get_json()
    produit_id = data.get("produit_id")
    if not produit_id:
        return jsonify({"erreur": "produit_id requis"}), 400
    Produit.query.get_or_404(produit_id)

    existant = Favori.query.filter_by(acheteur_id=acheteur_id, produit_id=produit_id).first()
    if existant:
        return jsonify({"message": "Déjà en favoris"}), 200

    favori = Favori(acheteur_id=acheteur_id, produit_id=produit_id)
    db.session.add(favori)
    db.session.commit()
    return jsonify({"message": "Ajouté aux favoris"}), 201


@app.route("/api/acheteurs/<int:acheteur_id>/favoris/<int:produit_id>", methods=["DELETE"])
def retirer_favori(acheteur_id, produit_id):
    favori = Favori.query.filter_by(acheteur_id=acheteur_id, produit_id=produit_id).first()
    if favori:
        db.session.delete(favori)
        db.session.commit()
    return jsonify({"message": "Retiré des favoris"})


# ---------- SUPPORT CLIENT ----------

@app.route("/api/support", methods=["POST"])
def creer_ticket_support():
    data = request.get_json()

    champs_requis = ["nom", "telephone", "message"]
    manquants = [c for c in champs_requis if not data.get(c)]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400

    ticket = TicketSupport(
        nom=data["nom"],
        telephone=data["telephone"],
        sujet=data.get("sujet", ""),
        message=data["message"],
        type_compte=data.get("type_compte", "visiteur"),
    )
    db.session.add(ticket)
    db.session.commit()

    return jsonify({"message": "Ticket envoyé", "ticket": ticket.to_dict()}), 201


@app.route("/api/admin/support", methods=["GET"])
def admin_lister_support():
    if not cle_admin_valide(request):
        return jsonify({"erreur": "Accès non autorisé"}), 401
    tickets = TicketSupport.query.order_by(TicketSupport.date_creation.desc()).all()
    return jsonify([t.to_dict() for t in tickets])


@app.route("/api/admin/support/<int:ticket_id>/statut", methods=["PUT"])
def admin_modifier_statut_support(ticket_id):
    if not cle_admin_valide(request):
        return jsonify({"erreur": "Accès non autorisé"}), 401
    ticket = TicketSupport.query.get_or_404(ticket_id)
    data = request.get_json()
    ticket.statut = data.get("statut", "traite")
    db.session.commit()
    return jsonify({"message": "Statut mis à jour", "ticket": ticket.to_dict()})


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
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
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


@app.route("/api/acheteurs/<int:acheteur_id>/push-token", methods=["PUT"])
def enregistrer_push_token_acheteur(acheteur_id):
    acheteur = Acheteur.query.get_or_404(acheteur_id)
    data = request.get_json()
    acheteur.push_token = data.get("push_token", "")
    db.session.commit()
    return jsonify({"message": "Jeton enregistré"})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


# ---------- COMMANDES ET SUIVI ----------

@app.route("/api/commandes", methods=["POST"])
def creer_commande():
    data = request.get_json()

    champs_requis = ["acheteur_id", "produit_id", "quantite"]
    manquants = [c for c in champs_requis if data.get(c) is None]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400

    acheteur = Acheteur.query.get_or_404(data["acheteur_id"])
    produit = Produit.query.get_or_404(data["produit_id"])

    quantite = data["quantite"]
    if not isinstance(quantite, (int, float)) or quantite <= 0:
        return jsonify({"erreur": "Quantité invalide"}), 400
    if quantite > produit.quantite_disponible:
        return jsonify({"erreur": "Quantité demandée supérieure au stock disponible"}), 400

    prix_total = round(quantite * produit.prix_unitaire, 2)

    commande = Commande(
        acheteur_id=data["acheteur_id"],
        produit_id=data["produit_id"],
        quantite=quantite,
        prix_total=prix_total,
        statut="en_attente",
        latitude_livraison=data.get("latitude_livraison"),
        longitude_livraison=data.get("longitude_livraison"),
    )
    commande.calculer_montants()
    db.session.add(commande)
    db.session.commit()

    if produit.producteur:
        envoyer_notification_push(
            produit.producteur.push_token,
            "Nouvelle commande reçue",
            f"{acheteur.nom} a commandé {produit.nom}",
        )

    return jsonify({"message": "Commande créée", "commande": commande.to_dict()}), 201


@app.route("/api/paniers/commander", methods=["POST"])
def commander_panier():
    """Valide un panier multi-vendeurs : crée une commande par produit,
    toutes rattachées au même panier_id."""
    data = request.get_json()

    champs_requis = ["acheteur_id", "articles"]
    manquants = [c for c in champs_requis if not data.get(c)]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400

    articles = data["articles"]
    if not isinstance(articles, list) or not articles:
        return jsonify({"erreur": "Le panier est vide"}), 400

    acheteur = Acheteur.query.get_or_404(data["acheteur_id"])
    latitude_livraison = data.get("latitude_livraison")
    longitude_livraison = data.get("longitude_livraison")

    panier_id = secrets.token_hex(4)
    commandes_creees = []

    for article in articles:
        produit_id = article.get("produit_id")
        quantite = article.get("quantite")
        if not produit_id or not quantite:
            continue
        produit = Produit.query.get(produit_id)
        if not produit:
            continue
        if quantite > produit.quantite_disponible:
            return jsonify({"erreur": f"Quantité indisponible pour {produit.nom}"}), 400

        prix_total = round(quantite * produit.prix_unitaire, 2)
        commande = Commande(
            acheteur_id=data["acheteur_id"],
            produit_id=produit_id,
            quantite=quantite,
            prix_total=prix_total,
            statut="en_attente",
            panier_id=panier_id,
            latitude_livraison=latitude_livraison,
            longitude_livraison=longitude_livraison,
        )
        commande.calculer_montants()
        db.session.add(commande)
        commandes_creees.append(commande)

    if not commandes_creees:
        return jsonify({"erreur": "Aucun article valide dans le panier"}), 400

    db.session.commit()

    for commande in commandes_creees:
        if commande.produit and commande.produit.producteur:
            envoyer_notification_push(
                commande.produit.producteur.push_token,
                "Nouvelle commande reçue",
                f"{acheteur.nom} a commandé {commande.produit.nom}",
            )

    return jsonify({
        "message": "Panier validé",
        "panier_id": panier_id,
        "commandes": [c.to_dict() for c in commandes_creees],
    }), 201


@app.route("/api/commandes/<int:commande_id>", methods=["GET"])
def obtenir_commande(commande_id):
    commande = Commande.query.get_or_404(commande_id)
    return jsonify(commande.to_dict())


@app.route("/api/commandes/<int:commande_id>/position", methods=["PUT"])
def mettre_a_jour_position_livreur(commande_id):
    """Le producteur ou le livreur partage sa position en direct pendant la livraison."""
    commande = Commande.query.get_or_404(commande_id)
    data = request.get_json()

    latitude = data.get("latitude")
    longitude = data.get("longitude")
    if latitude is None or longitude is None:
        return jsonify({"erreur": "latitude et longitude requis"}), 400

    commande.latitude_livreur = latitude
    commande.longitude_livreur = longitude
    commande.position_livreur_maj = datetime.utcnow()
    db.session.commit()

    return jsonify({"message": "Position mise à jour", "commande": commande.to_dict()})


@app.route("/api/acheteurs/<int:acheteur_id>/commandes", methods=["GET"])
def commandes_de_lacheteur(acheteur_id):
    Acheteur.query.get_or_404(acheteur_id)
    commandes = (
        Commande.query.filter_by(acheteur_id=acheteur_id)
        .order_by(Commande.date_commande.desc())
        .all()
    )
    return jsonify([c.to_dict() for c in commandes])


@app.route("/api/producteurs/<int:producteur_id>/commandes", methods=["GET"])
def commandes_du_producteur(producteur_id):
    Producteur.query.get_or_404(producteur_id)
    commandes = (
        Commande.query.join(Produit)
        .filter(Produit.producteur_id == producteur_id)
        .order_by(Commande.date_commande.desc())
        .all()
    )
    return jsonify([c.to_dict() for c in commandes])


@app.route("/api/commandes/<int:commande_id>/statut", methods=["PUT"])
def modifier_statut_commande(commande_id):
    commande = Commande.query.get_or_404(commande_id)
    data = request.get_json()

    nouveau_statut = data.get("statut")
    if nouveau_statut not in STATUTS_COMMANDE:
        return jsonify({"erreur": f"Statut invalide. Options: {', '.join(STATUTS_COMMANDE)}"}), 400

    commande.statut = nouveau_statut
    db.session.commit()

    if commande.acheteur:
        label = LABELS_STATUT_COMMANDE.get(nouveau_statut, nouveau_statut)
        nom_produit = commande.produit.nom if commande.produit else "ta commande"
        envoyer_notification_push(
            commande.acheteur.push_token,
            "Mise à jour de ta commande",
            f"{nom_produit} : {label}",
        )

    return jsonify({"message": "Statut mis à jour", "commande": commande.to_dict()})


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

    acheteur = Acheteur.query.get_or_404(data["acheteur_id"])
    producteur = Producteur.query.get_or_404(data["producteur_id"])

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

    apercu = contenu_filtre[:80]
    if data["expediteur_type"] == "acheteur":
        envoyer_notification_push(producteur.push_token, f"Message de {acheteur.nom}", apercu)
    else:
        envoyer_notification_push(acheteur.push_token, f"Message de {producteur.nom}", apercu)

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


# ---------- ADMINISTRATION ----------

@app.route("/api/admin/producteurs", methods=["GET"])
def admin_lister_producteurs():
    if not cle_admin_valide(request):
        return jsonify({"erreur": "Accès non autorisé"}), 401
    producteurs = Producteur.query.order_by(Producteur.date_inscription.desc()).all()
    return jsonify([p.to_dict() for p in producteurs])


@app.route("/api/admin/producteurs/<int:producteur_id>/verifier", methods=["PUT"])
def admin_verifier_producteur(producteur_id):
    if not cle_admin_valide(request):
        return jsonify({"erreur": "Accès non autorisé"}), 401
    producteur = Producteur.query.get_or_404(producteur_id)
    data = request.get_json()
    producteur.verifie = bool(data.get("verifie", True))
    db.session.commit()
    return jsonify({"message": "Statut de vérification mis à jour", "producteur": producteur.to_dict()})


@app.route("/api/admin/producteurs/<int:producteur_id>/actif", methods=["PUT"])
def admin_toggle_actif_producteur(producteur_id):
    if not cle_admin_valide(request):
        return jsonify({"erreur": "Accès non autorisé"}), 401
    producteur = Producteur.query.get_or_404(producteur_id)
    data = request.get_json()
    producteur.actif = bool(data.get("actif", True))
    db.session.commit()
    return jsonify({"message": "Statut mis à jour", "producteur": producteur.to_dict()})


@app.route("/api/admin/commandes", methods=["GET"])
def admin_lister_commandes():
    if not cle_admin_valide(request):
        return jsonify({"erreur": "Accès non autorisé"}), 401
    commandes = Commande.query.order_by(Commande.date_commande.desc()).all()
    return jsonify([c.to_dict() for c in commandes])


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    port = int(os.environ.get("PORT", 5050))
    app.run(debug=True, host="0.0.0.0", port=port, use_reloader=False)
