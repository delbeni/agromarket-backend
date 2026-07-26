from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from models import (
    db, Producteur, Produit, Acheteur, Commande, Message, Avis, Favori, TicketSupport,
    Livreur, HistoriquePrix, AchatGroupe, ParticipationGroupe, BesoinFinancement,
    PromesseFinancement, Terrain, CodePremium, NotairePartenaire, Beneficiaire, TransfertArgent,
    AgentMarchand, RetraitAgent,
    TrajetPoint, RecolteFuture, ReservationRecolte, Cooperative, MembreCooperative, Invendu, Signalement,
    NumeroMobileMoney,
)
import os
import re
import json
import secrets
import urllib.request
import urllib.parse
import math
from datetime import datetime

app = Flask(__name__)
CORS(app)

basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(basedir, 'agromarket.db')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

with app.app_context():
    db.create_all()

PAYS_AUTORISES = ["Côte d'Ivoire", "Mali", "Burkina Faso", "Sénégal", "Cameroun", "Togo", "Bénin", "Niger", "RDC", "Guinée"]
CATEGORIES = ["cereales", "elevage", "maraichage", "transforme", "restaurant", "autre"]
STATUTS_COMMANDE = ["en_attente", "confirmee_producteur", "livree", "terminee", "annulee"]

LABELS_STATUT_COMMANDE = {
    "en_attente": "En attente",
    "confirmee_producteur": "Confirmée par le vendeur",
    "livree": "Livrée",
    "terminee": "Terminée",
    "annulee": "Annulée",
}

ADMIN_KEY = os.environ.get("ADMIN_KEY", "agromarket_admin_2026")

# Africa's Talking (SMS pour les producteurs sans smartphone).
# IMPORTANT : déplace AT_API_KEY vers une variable d'environnement sur Render
# dès que possible, pour ne pas garder la clé en clair dans le code.
AT_USERNAME = os.environ.get("AT_USERNAME", "sandbox")
AT_API_KEY = os.environ.get("AT_API_KEY", "atsk_42cb47be1ad9ad1f1965f0fc6c9805ebc978840594879d9c0a36e98dd1b0440d66a93950")

INDICATIFS_PAYS = {
    "Côte d'Ivoire": "225",
    "Mali": "223",
    "Burkina Faso": "226",
    "Sénégal": "221",
}


def formater_numero_international(telephone, pays):
    chiffres = re.sub(r"\D", "", telephone or "")
    chiffres = chiffres.lstrip("0")
    indicatif = INDICATIFS_PAYS.get(pays, "225")
    return f"+{indicatif}{chiffres}"


def envoyer_sms(telephone, pays, message):
    """Envoie un SMS via Africa's Talking. Échoue silencieusement pour ne
    jamais bloquer la requête principale si le SMS ne part pas."""
    if not telephone:
        return
    try:
        numero = formater_numero_international(telephone, pays)
        base_url = (
            "https://api.sandbox.africastalking.com/version1/messaging"
            if AT_USERNAME == "sandbox"
            else "https://api.africastalking.com/version1/messaging"
        )
        data = urllib.parse.urlencode({
            "username": AT_USERNAME,
            "to": numero,
            "message": message,
        }).encode("utf-8")
        req = urllib.request.Request(
            base_url, data=data,
            headers={
                "apiKey": AT_API_KEY,
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def cle_admin_valide(req):
    return req.headers.get("X-Admin-Key") == ADMIN_KEY


def generer_code_parrainage():
    while True:
        code = secrets.token_hex(3).upper()
        if not Producteur.query.filter_by(code_parrainage=code).first():
            return code


def envoyer_notification_push(token, titre, corps, donnees=None):
    if not token:
        return
    payload = {"to": token, "title": titre, "body": corps, "data": donnees or {}}
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


def distance_km(lat1, lon1, lat2, lon2):
    """Distance à vol d'oiseau entre deux points GPS, en kilomètres (formule de haversine)."""
    if None in (lat1, lon1, lat2, lon2):
        return None
    rayon_terre = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(rayon_terre * c, 1)


REGEX_NUMERO = re.compile(r"(\d[\s.\-]?){8,}")
MOTS_CLES_CONTOURNEMENT = [
    "whatsapp", "whats app", "appelle moi", "appelle-moi", "mon numero",
    "mon numéro", "contact direct", "en dehors de l'app", "hors application",
    "virement direct", "paiement direct", "espece", "espèces directement",
]


def filtrer_message(texte):
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
        nom=data["nom"], telephone=data["telephone"],
        mot_de_passe_hash=generate_password_hash(data["mot_de_passe"]),
        pays=data["pays"], ville=data["ville"],
        zone_livraison=data.get("zone_livraison", ""),
        latitude=data.get("latitude"), longitude=data.get("longitude"),
        type_production=data.get("type_production", ""),
        description=data.get("description", ""),
        photo_url=data.get("photo_url", ""), histoire=data.get("histoire", ""),
        piece_identite_recto=data.get("piece_identite_recto", ""),
        piece_identite_verso=data.get("piece_identite_verso", ""),
        code_parrainage=generer_code_parrainage(),
        code_parrain_utilise=code_saisi if parrain else None,
    )
    db.session.add(producteur)
    db.session.commit()

    if parrain:
        parrain.nombre_filleuls = (parrain.nombre_filleuls or 0) + 1
        db.session.commit()

    envoyer_sms(
        producteur.telephone, producteur.pays,
        f"Bienvenue sur AgriChange, {producteur.nom} ! Ton compte producteur est créé. Ajoute tes produits pour commencer à vendre.",
    )

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
    return jsonify(Producteur.query.get_or_404(producteur_id).to_dict())


@app.route("/api/producteurs/<int:producteur_id>", methods=["PUT"])
def modifier_producteur(producteur_id):
    producteur = Producteur.query.get_or_404(producteur_id)
    data = request.get_json()
    for champ in ["nom", "pays", "ville", "zone_livraison", "type_production", "description",
                  "photo_url", "histoire", "latitude", "longitude",
                  "piece_identite_recto", "piece_identite_verso"]:
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
    return jsonify([p.to_dict() for p in query.all()])


@app.route("/api/producteurs/<int:producteur_id>/push-token", methods=["PUT"])
def enregistrer_push_token_producteur(producteur_id):
    producteur = Producteur.query.get_or_404(producteur_id)
    producteur.push_token = request.get_json().get("push_token", "")
    db.session.commit()
    return jsonify({"message": "Jeton enregistré"})


@app.route("/api/producteurs/<int:producteur_id>/consommer-credit", methods=["POST"])
def consommer_credit(producteur_id):
    """Vérifie et consomme un crédit d'utilisation des outils (calculateur, générateur d'annonce)."""
    producteur = Producteur.query.get_or_404(producteur_id)
    if producteur.premium:
        return jsonify({"autorise": True, "credits_restants": None, "premium": True})
    if (producteur.credits_outils or 0) > 0:
        producteur.credits_outils -= 1
        db.session.commit()
        return jsonify({"autorise": True, "credits_restants": producteur.credits_outils, "premium": False})
    return jsonify({
        "autorise": False,
        "erreur": "Tu as utilisé tous tes crédits gratuits ce mois-ci. Contacte le support pour la version premium.",
    }), 403


@app.route("/api/producteurs/<int:producteur_id>/utiliser-code-premium", methods=["POST"])
def utiliser_code_premium(producteur_id):
    producteur = Producteur.query.get_or_404(producteur_id)
    code_saisi = (request.get_json().get("code") or "").strip().upper()
    if not code_saisi:
        return jsonify({"erreur": "Code requis"}), 400

    code = CodePremium.query.filter_by(code=code_saisi).first()
    if not code:
        return jsonify({"erreur": "Code invalide"}), 404
    if code.utilise:
        return jsonify({"erreur": "Ce code a déjà été utilisé"}), 409

    code.utilise = True
    code.producteur_id = producteur_id
    code.date_utilisation = datetime.utcnow()
    producteur.premium = True
    db.session.commit()

    return jsonify({"message": "Premium débloqué !", "producteur": producteur.to_dict()})


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
        nom=data["nom"], telephone=data["telephone"],
        mot_de_passe_hash=generate_password_hash(data["mot_de_passe"]),
        pays=data["pays"], ville=data["ville"], vehicule=data.get("vehicule", ""),
        marque_vehicule=data.get("marque_vehicule", ""),
        plaque_immatriculation=data.get("plaque_immatriculation", ""),
        couleur_vehicule=data.get("couleur_vehicule", ""),
        piece_identite_recto=data.get("piece_identite_recto", ""),
        piece_identite_verso=data.get("piece_identite_verso", ""),
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
    return jsonify(Livreur.query.get_or_404(livreur_id).to_dict())


@app.route("/api/livreurs/<int:livreur_id>/push-token", methods=["PUT"])
def enregistrer_push_token_livreur(livreur_id):
    livreur = Livreur.query.get_or_404(livreur_id)
    livreur.push_token = request.get_json().get("push_token", "")
    db.session.commit()
    return jsonify({"message": "Jeton enregistré"})


@app.route("/api/livreurs/<int:livreur_id>/service", methods=["PUT"])
def toggle_service_livreur(livreur_id):
    """Le livreur se déclare disponible ('en service') ou non, visible par les acheteurs/vendeurs à proximité."""
    livreur = Livreur.query.get_or_404(livreur_id)
    livreur.en_service = bool(request.get_json().get("en_service", False))
    db.session.commit()
    return jsonify({"message": "Statut mis à jour", "livreur": livreur.to_dict()})


@app.route("/api/livreurs/<int:livreur_id>/position-direct", methods=["PUT"])
def mettre_a_jour_position_livreur_direct(livreur_id):
    """Position en continu du livreur pendant qu'il est 'en service' (indépendante d'une commande précise)."""
    livreur = Livreur.query.get_or_404(livreur_id)
    data = request.get_json()
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    if latitude is None or longitude is None:
        return jsonify({"erreur": "latitude et longitude requis"}), 400
    livreur.latitude = latitude
    livreur.longitude = longitude
    livreur.position_maj = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "Position mise à jour", "livreur": livreur.to_dict()})


@app.route("/api/livreurs-proches", methods=["GET"])
def livreurs_proches():
    """Liste des livreurs actuellement 'en service', triés par distance si une position est fournie."""
    latitude = request.args.get("latitude", type=float)
    longitude = request.args.get("longitude", type=float)

    livreurs = Livreur.query.filter_by(en_service=True, actif=True).all()
    resultats = []
    for l in livreurs:
        d = l.to_dict()
        d["distance_km"] = distance_km(latitude, longitude, l.latitude, l.longitude)
        resultats.append(d)

    if latitude is not None and longitude is not None:
        resultats.sort(key=lambda d: (d["distance_km"] is None, d["distance_km"]))

    return jsonify(resultats)


@app.route("/api/livraisons-disponibles", methods=["GET"])
def livraisons_disponibles():
    commandes = (
        Commande.query.filter_by(statut="confirmee_producteur", livreur_id=None)
        .order_by(Commande.date_commande.asc()).all()
    )
    return jsonify([c.to_dict() for c in commandes])


@app.route("/api/livreurs/<int:livreur_id>/livraisons", methods=["GET"])
def livraisons_du_livreur(livreur_id):
    Livreur.query.get_or_404(livreur_id)
    commandes = Commande.query.filter_by(livreur_id=livreur_id).order_by(Commande.date_commande.desc()).all()
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
            commande.acheteur.push_token, "Livreur en route",
            f"Un livreur a pris en charge ta commande « {commande.produit.nom if commande.produit else ''} ».",
        )
    return jsonify({"message": "Livraison acceptée", "commande": commande.to_dict()})


# ---------- AVIS ----------

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
    avis = Avis(producteur_id=producteur_id, acheteur_id=data["acheteur_id"], note=note,
                commentaire=data.get("commentaire", ""))
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
    produit_id = request.get_json().get("produit_id")
    if not produit_id:
        return jsonify({"erreur": "produit_id requis"}), 400
    Produit.query.get_or_404(produit_id)
    if Favori.query.filter_by(acheteur_id=acheteur_id, produit_id=produit_id).first():
        return jsonify({"message": "Déjà en favoris"}), 200
    db.session.add(Favori(acheteur_id=acheteur_id, produit_id=produit_id))
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
    ticket = TicketSupport(nom=data["nom"], telephone=data["telephone"], sujet=data.get("sujet", ""),
                            message=data["message"], type_compte=data.get("type_compte", "visiteur"))
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
    ticket.statut = request.get_json().get("statut", "traite")
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
    photos_urls = photos_urls[:4]
    photo_couverture = photos_urls[0] if photos_urls else data.get("photo_url", "")

    produit = Produit(
        producteur_id=producteur_id, nom=data["nom"], categorie=data["categorie"],
        prix_unitaire=data["prix_unitaire"], unite=data.get("unite", "unité"),
        quantite_disponible=data["quantite_disponible"], photo_url=photo_couverture,
        photos_urls=json.dumps(photos_urls), video_url=data.get("video_url", ""),
        description=data.get("description", ""),
        disponible_export=bool(data.get("disponible_export", False)),
    )
    db.session.add(produit)
    db.session.commit()
    db.session.add(HistoriquePrix(produit_id=produit.id, prix=produit.prix_unitaire))
    db.session.commit()

    reponse = {"message": "Produit ajouté", "produit": produit.to_dict()}
    autres_prix = [
        p.prix_unitaire for p in Produit.query.filter_by(categorie=data["categorie"], actif=True).all()
        if p.id != produit.id
    ]
    if len(autres_prix) >= 3:
        moyenne = sum(autres_prix) / len(autres_prix)
        if produit.prix_unitaire < moyenne * 0.7:
            pourcentage = round((1 - produit.prix_unitaire / moyenne) * 100)
            reponse["alerte_prix"] = (
                f"Ce prix est {pourcentage}% en dessous de la moyenne du marché pour cette catégorie "
                f"(environ {round(moyenne)} FCFA). Es-tu sûr de vouloir vendre à ce prix ?"
            )

    return jsonify(reponse), 201


@app.route("/api/producteurs/<int:producteur_id>/produits", methods=["GET"])
def produits_du_producteur(producteur_id):
    Producteur.query.get_or_404(producteur_id)
    return jsonify([p.to_dict() for p in Produit.query.filter_by(producteur_id=producteur_id).all()])


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

    if "prix_unitaire" in data and data["prix_unitaire"] != produit.prix_unitaire:
        db.session.add(HistoriquePrix(produit_id=produit.id, prix=data["prix_unitaire"]))

    for champ in ["nom", "prix_unitaire", "unite", "quantite_disponible", "photo_url", "video_url", "description", "actif", "disponible_export"]:
        if champ in data:
            setattr(produit, champ, data[champ])

    db.session.commit()
    return jsonify({"message": "Produit mis à jour", "produit": produit.to_dict()})


@app.route("/api/produits/<int:produit_id>/historique-prix", methods=["GET"])
def historique_prix_produit(produit_id):
    Produit.query.get_or_404(produit_id)
    historique = HistoriquePrix.query.filter_by(produit_id=produit_id).order_by(HistoriquePrix.date.desc()).limit(10).all()
    return jsonify([h.to_dict() for h in historique])


@app.route("/api/produits", methods=["GET"])
def lister_produits():
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


@app.route("/api/produits/export", methods=["GET"])
def lister_produits_export():
    """Produits signalés par leurs producteurs comme disponibles pour l'export international."""
    produits = Produit.query.filter_by(actif=True, disponible_export=True).all()
    return jsonify([p.to_dict() for p in produits])


# ---------- COOPÉRATIVES VIRTUELLES ----------

@app.route("/api/producteurs/<int:producteur_id>/cooperatives", methods=["POST"])
def creer_cooperative(producteur_id):
    createur = Producteur.query.get_or_404(producteur_id)
    data = request.get_json()
    if not data.get("nom"):
        return jsonify({"erreur": "Le nom de la coopérative est requis"}), 400
    cooperative = Cooperative(
        nom=data["nom"], description=data.get("description", ""),
        pays=createur.pays, ville=data.get("ville", createur.ville), createur_id=producteur_id,
    )
    db.session.add(cooperative)
    db.session.commit()
    db.session.add(MembreCooperative(cooperative_id=cooperative.id, producteur_id=producteur_id))
    db.session.commit()
    return jsonify({"message": "Coopérative créée", "cooperative": cooperative.to_dict()}), 201


@app.route("/api/cooperatives", methods=["GET"])
def lister_cooperatives():
    pays = request.args.get("pays")
    query = Cooperative.query
    if pays:
        query = query.filter_by(pays=pays)
    cooperatives = query.order_by(Cooperative.date_creation.desc()).all()
    return jsonify([c.to_dict() for c in cooperatives])


@app.route("/api/cooperatives/<int:cooperative_id>", methods=["GET"])
def obtenir_cooperative(cooperative_id):
    cooperative = Cooperative.query.get_or_404(cooperative_id)
    resultat = cooperative.to_dict()
    resultat["membres"] = [m.to_dict() for m in cooperative.membres]
    return jsonify(resultat)


@app.route("/api/cooperatives/<int:cooperative_id>/rejoindre", methods=["POST"])
def rejoindre_cooperative(cooperative_id):
    cooperative = Cooperative.query.get_or_404(cooperative_id)
    data = request.get_json()
    producteur_id = data.get("producteur_id")
    if not producteur_id:
        return jsonify({"erreur": "producteur_id requis"}), 400
    Producteur.query.get_or_404(producteur_id)
    if MembreCooperative.query.filter_by(cooperative_id=cooperative_id, producteur_id=producteur_id).first():
        return jsonify({"message": "Déjà membre"}), 200
    db.session.add(MembreCooperative(cooperative_id=cooperative_id, producteur_id=producteur_id))
    db.session.commit()
    return jsonify({"message": "Tu as rejoint la coopérative", "cooperative": cooperative.to_dict()}), 201


@app.route("/api/producteurs/<int:producteur_id>/cooperatives", methods=["GET"])
def cooperatives_du_producteur(producteur_id):
    Producteur.query.get_or_404(producteur_id)
    memberships = MembreCooperative.query.filter_by(producteur_id=producteur_id).all()
    return jsonify([m.cooperative.to_dict() for m in memberships if m.cooperative])


# ---------- BOURSE AUX INVENDUS / DONS ----------

@app.route("/api/producteurs/<int:producteur_id>/invendus", methods=["POST"])
def creer_invendu(producteur_id):
    Producteur.query.get_or_404(producteur_id)
    data = request.get_json()
    champs_requis = ["nom", "quantite"]
    manquants = [c for c in champs_requis if data.get(c) is None]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400
    invendu = Invendu(
        producteur_id=producteur_id, nom=data["nom"], quantite=data["quantite"],
        unite=data.get("unite", "kg"), prix_reduit=data.get("prix_reduit", 0),
        description=data.get("description", ""),
    )
    db.session.add(invendu)
    db.session.commit()
    return jsonify({"message": "Invendu publié", "invendu": invendu.to_dict()}), 201


@app.route("/api/invendus", methods=["GET"])
def lister_invendus():
    invendus = Invendu.query.filter_by(actif=True).order_by(Invendu.date_ajout.desc()).all()
    return jsonify([i.to_dict() for i in invendus])


@app.route("/api/invendus/<int:invendu_id>/reserver", methods=["PUT"])
def reserver_invendu(invendu_id):
    invendu = Invendu.query.get_or_404(invendu_id)
    if not invendu.actif:
        return jsonify({"erreur": "Cet invendu n'est plus disponible"}), 409
    data = request.get_json()
    acheteur_id = data.get("acheteur_id")
    if not acheteur_id:
        return jsonify({"erreur": "acheteur_id requis"}), 400
    acheteur = Acheteur.query.get_or_404(acheteur_id)
    invendu.actif = False
    db.session.commit()
    if invendu.producteur:
        envoyer_notification_push(
            invendu.producteur.push_token, "Invendu réservé",
            f"{acheteur.nom} a réservé « {invendu.nom} ». Contacte-le pour organiser la remise.",
        )
    return jsonify({"message": "Réservé", "invendu": invendu.to_dict()})


# ---------- SIGNALEMENTS COMMUNAUTAIRES (anti-arnaque) ----------

@app.route("/api/signalements", methods=["POST"])
def creer_signalement():
    data = request.get_json()
    champs_requis = ["signale_type", "signale_id", "motif"]
    manquants = [c for c in champs_requis if data.get(c) is None]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400
    signalement = Signalement(
        signale_type=data["signale_type"], signale_id=data["signale_id"], signale_nom=data.get("signale_nom", ""),
        signale_par_nom=data.get("signale_par_nom", ""), signale_par_telephone=data.get("signale_par_telephone", ""),
        motif=data["motif"], description=data.get("description", ""),
    )
    db.session.add(signalement)
    db.session.commit()
    return jsonify({"message": "Signalement enregistré, notre équipe va l'examiner", "signalement": signalement.to_dict()}), 201


@app.route("/api/admin/signalements", methods=["GET"])
def admin_lister_signalements():
    if not cle_admin_valide(request):
        return jsonify({"erreur": "Accès non autorisé"}), 401
    signalements = Signalement.query.order_by(Signalement.date_creation.desc()).all()
    return jsonify([s.to_dict() for s in signalements])


@app.route("/api/admin/signalements/<int:signalement_id>/statut", methods=["PUT"])
def admin_modifier_statut_signalement(signalement_id):
    if not cle_admin_valide(request):
        return jsonify({"erreur": "Accès non autorisé"}), 401
    signalement = Signalement.query.get_or_404(signalement_id)
    signalement.statut = request.get_json().get("statut", "traite")
    db.session.commit()
    return jsonify({"message": "Statut mis à jour", "signalement": signalement.to_dict()})


# ---------- RÉCOLTES FUTURES (pré-commande avant disponibilité) ----------

@app.route("/api/producteurs/<int:producteur_id>/recoltes-futures", methods=["POST"])
def creer_recolte_future(producteur_id):
    Producteur.query.get_or_404(producteur_id)
    data = request.get_json()
    champs_requis = ["nom", "categorie", "quantite_estimee", "prix_unitaire_prevu"]
    manquants = [c for c in champs_requis if data.get(c) is None]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400
    if data["categorie"] not in CATEGORIES:
        return jsonify({"erreur": f"Catégorie invalide. Options: {', '.join(CATEGORIES)}"}), 400

    date_recolte = None
    if data.get("date_recolte_prevue"):
        try:
            date_recolte = datetime.strptime(data["date_recolte_prevue"], "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"erreur": "Format de date invalide (AAAA-MM-JJ attendu)"}), 400

    recolte = RecolteFuture(
        producteur_id=producteur_id, nom=data["nom"], categorie=data["categorie"],
        quantite_estimee=data["quantite_estimee"], unite=data.get("unite", "sac"),
        prix_unitaire_prevu=data["prix_unitaire_prevu"], date_recolte_prevue=date_recolte,
        description=data.get("description", ""),
    )
    db.session.add(recolte)
    db.session.commit()
    return jsonify({"message": "Récolte future annoncée", "recolte": recolte.to_dict()}), 201


@app.route("/api/recoltes-futures", methods=["GET"])
def lister_recoltes_futures():
    recoltes = RecolteFuture.query.filter_by(statut="ouvert").order_by(RecolteFuture.date_creation.desc()).all()
    return jsonify([r.to_dict() for r in recoltes])


@app.route("/api/producteurs/<int:producteur_id>/recoltes-futures", methods=["GET"])
def recoltes_futures_du_producteur(producteur_id):
    Producteur.query.get_or_404(producteur_id)
    recoltes = RecolteFuture.query.filter_by(producteur_id=producteur_id).order_by(RecolteFuture.date_creation.desc()).all()
    return jsonify([r.to_dict() for r in recoltes])


@app.route("/api/recoltes-futures/<int:recolte_id>", methods=["GET"])
def obtenir_recolte_future(recolte_id):
    recolte = RecolteFuture.query.get_or_404(recolte_id)
    resultat = recolte.to_dict()
    resultat["reservations"] = [r.to_dict() for r in recolte.reservations]
    return jsonify(resultat)


@app.route("/api/recoltes-futures/<int:recolte_id>/reserver", methods=["POST"])
def reserver_recolte_future(recolte_id):
    recolte = RecolteFuture.query.get_or_404(recolte_id)
    if recolte.statut != "ouvert":
        return jsonify({"erreur": "Cette récolte future n'est plus ouverte aux réservations"}), 409
    data = request.get_json()
    champs_requis = ["acheteur_id", "quantite"]
    manquants = [c for c in champs_requis if data.get(c) is None]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400

    acheteur = Acheteur.query.get_or_404(data["acheteur_id"])
    quantite = data["quantite"]
    if not isinstance(quantite, (int, float)) or quantite <= 0:
        return jsonify({"erreur": "Quantité invalide"}), 400

    reservation = ReservationRecolte(recolte_id=recolte_id, acheteur_id=data["acheteur_id"], quantite=quantite)
    db.session.add(reservation)
    db.session.commit()

    if recolte.producteur:
        envoyer_notification_push(
            recolte.producteur.push_token, "Réservation de récolte future",
            f"{acheteur.nom} a réservé {quantite} {recolte.unite} de {recolte.nom}.",
        )
        envoyer_sms(
            recolte.producteur.telephone, recolte.producteur.pays,
            f"AgriChange : {acheteur.nom} a réservé {quantite} {recolte.unite} de ta future récolte de {recolte.nom}.",
        )

    return jsonify({"message": "Réservation enregistrée", "recolte": recolte.to_dict()}), 201


@app.route("/api/recoltes-futures/<int:recolte_id>/cloturer", methods=["PUT"])
def cloturer_recolte_future(recolte_id):
    recolte = RecolteFuture.query.get_or_404(recolte_id)
    recolte.statut = "clos"
    db.session.commit()
    return jsonify({"message": "Récolte future clôturée", "recolte": recolte.to_dict()})


# ---------- ACHATS GROUPÉS ----------

@app.route("/api/produits/<int:produit_id>/achats-groupes", methods=["POST"])
def creer_achat_groupe(produit_id):
    Produit.query.get_or_404(produit_id)
    data = request.get_json()
    champs_requis = ["prix_unitaire_groupe", "quantite_cible"]
    manquants = [c for c in champs_requis if data.get(c) is None]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400
    campagne = AchatGroupe(
        produit_id=produit_id, prix_unitaire_groupe=data["prix_unitaire_groupe"],
        quantite_cible=data["quantite_cible"],
    )
    db.session.add(campagne)
    db.session.commit()
    return jsonify({"message": "Achat groupé créé", "achat_groupe": campagne.to_dict()}), 201


@app.route("/api/achats-groupes", methods=["GET"])
def lister_achats_groupes():
    campagnes = AchatGroupe.query.filter_by(statut="ouvert").order_by(AchatGroupe.date_creation.desc()).all()
    return jsonify([c.to_dict() for c in campagnes])


@app.route("/api/achats-groupes/<int:achat_groupe_id>", methods=["GET"])
def obtenir_achat_groupe(achat_groupe_id):
    campagne = AchatGroupe.query.get_or_404(achat_groupe_id)
    resultat = campagne.to_dict()
    resultat["participants"] = [p.to_dict() for p in campagne.participations]
    return jsonify(resultat)


@app.route("/api/achats-groupes/<int:achat_groupe_id>/participer", methods=["POST"])
def participer_achat_groupe(achat_groupe_id):
    campagne = AchatGroupe.query.get_or_404(achat_groupe_id)
    if campagne.statut != "ouvert":
        return jsonify({"erreur": "Cet achat groupé n'est plus ouvert"}), 409
    data = request.get_json()
    champs_requis = ["acheteur_id", "quantite"]
    manquants = [c for c in champs_requis if data.get(c) is None]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400

    acheteur = Acheteur.query.get_or_404(data["acheteur_id"])
    quantite = data["quantite"]
    if not isinstance(quantite, (int, float)) or quantite <= 0:
        return jsonify({"erreur": "Quantité invalide"}), 400

    participation = ParticipationGroupe(achat_groupe_id=achat_groupe_id, acheteur_id=data["acheteur_id"], quantite=quantite)
    db.session.add(participation)
    campagne.quantite_actuelle = (campagne.quantite_actuelle or 0) + quantite
    db.session.commit()

    if campagne.quantite_actuelle >= campagne.quantite_cible:
        campagne.statut = "atteint"
        db.session.commit()
        for p in campagne.participations:
            prix_total = round(p.quantite * campagne.prix_unitaire_groupe, 2)
            commande = Commande(
                acheteur_id=p.acheteur_id, produit_id=campagne.produit_id,
                quantite=p.quantite, prix_total=prix_total, statut="en_attente",
            )
            commande.calculer_montants()
            db.session.add(commande)
        db.session.commit()
        if campagne.produit and campagne.produit.producteur:
            envoyer_notification_push(
                campagne.produit.producteur.push_token, "Achat groupé atteint !",
                f"L'achat groupé pour {campagne.produit.nom} a atteint son objectif.",
            )
            envoyer_sms(
                campagne.produit.producteur.telephone, campagne.produit.producteur.pays,
                f"AgriChange : ton achat groupé pour {campagne.produit.nom} a atteint son objectif ! Les commandes sont créées.",
            )

    return jsonify({"message": "Participation enregistrée", "achat_groupe": campagne.to_dict()}), 201


# ---------- PRÉ-FINANCEMENT DIASPORA ----------

@app.route("/api/producteurs/<int:producteur_id>/financements", methods=["POST"])
def creer_besoin_financement(producteur_id):
    Producteur.query.get_or_404(producteur_id)
    data = request.get_json()
    champs_requis = ["titre", "montant_cible"]
    manquants = [c for c in champs_requis if data.get(c) is None]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400
    besoin = BesoinFinancement(
        producteur_id=producteur_id, titre=data["titre"], description=data.get("description", ""),
        montant_cible=data["montant_cible"],
    )
    db.session.add(besoin)
    db.session.commit()
    return jsonify({"message": "Besoin de financement publié", "financement": besoin.to_dict()}), 201


@app.route("/api/financements", methods=["GET"])
def lister_financements():
    besoins = BesoinFinancement.query.filter_by(statut="ouvert").order_by(BesoinFinancement.date_creation.desc()).all()
    return jsonify([b.to_dict() for b in besoins])


@app.route("/api/producteurs/<int:producteur_id>/financements", methods=["GET"])
def financements_du_producteur(producteur_id):
    Producteur.query.get_or_404(producteur_id)
    besoins = BesoinFinancement.query.filter_by(producteur_id=producteur_id).order_by(BesoinFinancement.date_creation.desc()).all()
    return jsonify([b.to_dict() for b in besoins])


@app.route("/api/financements/<int:besoin_id>/promettre", methods=["POST"])
def promettre_financement(besoin_id):
    besoin = BesoinFinancement.query.get_or_404(besoin_id)
    if besoin.statut != "ouvert":
        return jsonify({"erreur": "Ce besoin de financement n'est plus ouvert"}), 409
    data = request.get_json()
    champs_requis = ["acheteur_id", "montant"]
    manquants = [c for c in champs_requis if data.get(c) is None]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400
    Acheteur.query.get_or_404(data["acheteur_id"])
    montant = data["montant"]
    if not isinstance(montant, (int, float)) or montant <= 0:
        return jsonify({"erreur": "Montant invalide"}), 400

    promesse = PromesseFinancement(besoin_id=besoin_id, acheteur_id=data["acheteur_id"], montant=montant)
    db.session.add(promesse)
    besoin.montant_leve = (besoin.montant_leve or 0) + montant
    if besoin.montant_leve >= besoin.montant_cible:
        besoin.statut = "atteint"
    db.session.commit()

    if besoin.producteur:
        envoyer_notification_push(
            besoin.producteur.push_token, "Nouveau soutien reçu",
            f"Quelqu'un s'est engagé à te soutenir pour « {besoin.titre} ».",
        )
        envoyer_sms(
            besoin.producteur.telephone, besoin.producteur.pays,
            f"AgriChange : quelqu'un s'est engagé à te soutenir pour « {besoin.titre} ». Ouvre l'app pour voir le détail.",
        )

    return jsonify({"message": "Promesse enregistrée", "financement": besoin.to_dict()}), 201


# ---------- TRANSFERT D'ARGENT LIBRE (diaspora -> Afrique) ----------

@app.route("/api/beneficiaires/inscription", methods=["POST"])
def inscription_beneficiaire():
    data = request.get_json()
    champs_requis = ["nom", "telephone", "mot_de_passe", "pays"]
    manquants = [c for c in champs_requis if not data.get(c)]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400
    if Beneficiaire.query.filter_by(telephone=data["telephone"]).first():
        return jsonify({"erreur": "Ce numéro de téléphone est déjà enregistré"}), 409

    beneficiaire = Beneficiaire(
        nom=data["nom"], telephone=data["telephone"],
        mot_de_passe_hash=generate_password_hash(data["mot_de_passe"]),
        pays=data["pays"], ville=data.get("ville", ""),
        operateur_mobile_money=data.get("operateur_mobile_money", ""),
        numero_mobile_money=data.get("numero_mobile_money", ""),
    )
    db.session.add(beneficiaire)
    db.session.commit()

    if data.get("operateur_mobile_money") and data.get("numero_mobile_money"):
        db.session.add(NumeroMobileMoney(
            beneficiaire_id=beneficiaire.id,
            operateur=data["operateur_mobile_money"], numero=data["numero_mobile_money"],
        ))
        db.session.commit()

    return jsonify({"message": "Compte bénéficiaire créé", "beneficiaire": beneficiaire.to_dict()}), 201


@app.route("/api/beneficiaires/<int:beneficiaire_id>/numeros", methods=["POST"])
def ajouter_numero_mobile_money(beneficiaire_id):
    Beneficiaire.query.get_or_404(beneficiaire_id)
    data = request.get_json()
    if not data.get("operateur") or not data.get("numero"):
        return jsonify({"erreur": "operateur et numero requis"}), 400
    numero = NumeroMobileMoney(beneficiaire_id=beneficiaire_id, operateur=data["operateur"], numero=data["numero"])
    db.session.add(numero)
    db.session.commit()
    return jsonify({"message": "Numéro ajouté", "numero": numero.to_dict()}), 201


@app.route("/api/beneficiaires/<int:beneficiaire_id>/numeros/<int:numero_id>", methods=["DELETE"])
def supprimer_numero_mobile_money(beneficiaire_id, numero_id):
    numero = NumeroMobileMoney.query.filter_by(id=numero_id, beneficiaire_id=beneficiaire_id).first_or_404()
    db.session.delete(numero)
    db.session.commit()
    return jsonify({"message": "Numéro supprimé"})


@app.route("/api/beneficiaires/connexion", methods=["POST"])
def connexion_beneficiaire():
    data = request.get_json()
    beneficiaire = Beneficiaire.query.filter_by(telephone=data.get("telephone")).first()
    if not beneficiaire or not check_password_hash(beneficiaire.mot_de_passe_hash, data.get("mot_de_passe", "")):
        return jsonify({"erreur": "Téléphone ou mot de passe incorrect"}), 401
    return jsonify({"message": "Connexion réussie", "beneficiaire": beneficiaire.to_dict()}), 200


@app.route("/api/beneficiaires/<int:beneficiaire_id>/push-token", methods=["PUT"])
def enregistrer_push_token_beneficiaire(beneficiaire_id):
    beneficiaire = Beneficiaire.query.get_or_404(beneficiaire_id)
    beneficiaire.push_token = request.get_json().get("push_token", "")
    db.session.commit()
    return jsonify({"message": "Jeton enregistré"})


@app.route("/api/beneficiaires/rechercher", methods=["GET"])
def rechercher_beneficiaire():
    pays = request.args.get("pays")
    telephone = request.args.get("telephone")
    if not pays or not telephone:
        return jsonify({"erreur": "pays et telephone requis"}), 400
    beneficiaire = Beneficiaire.query.filter_by(pays=pays, telephone=telephone, actif=True).first()
    if not beneficiaire:
        return jsonify({"erreur": "Aucun bénéficiaire trouvé avec ce numéro dans ce pays"}), 404
    return jsonify(beneficiaire.to_dict())


@app.route("/api/transferts", methods=["POST"])
def creer_transfert():
    data = request.get_json()
    champs_requis = ["destinataire_id", "expediteur_nom", "montant"]
    manquants = [c for c in champs_requis if data.get(c) is None]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400

    beneficiaire = Beneficiaire.query.get_or_404(data["destinataire_id"])
    montant = data["montant"]
    if not isinstance(montant, (int, float)) or montant <= 0:
        return jsonify({"erreur": "Montant invalide"}), 400

    # Transfert réalisé via un agent marchand (optionnel)
    agent = None
    frais_service = float(data.get("frais_service") or 0)
    commission_agent = float(data.get("commission_agent") or 0)
    code_agent = (data.get("code_agent") or "").strip().upper()
    if code_agent:
        agent = AgentMarchand.query.filter_by(code_agent=code_agent, actif=True).first()
        if not agent:
            return jsonify({"erreur": "Code agent introuvable ou inactif"}), 404
        if commission_agent > frais_service:
            return jsonify({"erreur": "La commission agent ne peut pas dépasser les frais de service"}), 400

    transfert = TransfertArgent(
        destinataire_id=data["destinataire_id"], expediteur_nom=data["expediteur_nom"],
        expediteur_telephone=data.get("expediteur_telephone", ""), expediteur_pays=data.get("expediteur_pays", ""),
        montant=montant, message=data.get("message", ""),
        agent_id=agent.id if agent else None,
        frais_service=frais_service, commission_agent=commission_agent if agent else 0.0,
    )
    db.session.add(transfert)
    db.session.commit()

    envoyer_notification_push(
        beneficiaire.push_token, "Transfert d'argent reçu",
        f"{data['expediteur_nom']} t'envoie {montant} FCFA sur AgriChange.",
    )
    envoyer_sms(
        beneficiaire.telephone, beneficiaire.pays,
        f"AgriChange : {data['expediteur_nom']} t'a envoyé {montant} FCFA. Le versement se fera dès l'activation du paiement en ligne. Ouvre l'app pour voir le détail.",
    )

    return jsonify({"message": "Transfert enregistré", "transfert": transfert.to_dict()}), 201


@app.route("/api/transferts/<int:transfert_id>/annuler", methods=["POST"])
def annuler_transfert(transfert_id):
    """Permet d'annuler un transfert tant qu'il n'a pas encore été réellement versé.
    Sert de filet de sécurité en cas d'erreur de numéro de destinataire."""
    transfert = TransfertArgent.query.get_or_404(transfert_id)
    if transfert.statut != "initie":
        return jsonify({"erreur": "Ce transfert ne peut plus être annulé (déjà versé ou déjà annulé)."}), 400
    data = request.get_json(silent=True) or {}
    transfert.statut = "annule"
    transfert.date_annulation = datetime.utcnow()
    transfert.motif_annulation = data.get("motif", "Annulé par l'expéditeur")
    db.session.commit()
    return jsonify({"message": "Transfert annulé", "transfert": transfert.to_dict()})


@app.route("/api/admin/transferts/<int:transfert_id>/confirmer-versement", methods=["POST"])
def confirmer_versement_transfert(transfert_id):
    """Action admin : confirme que l'argent a réellement été versé (une fois CinetPay actif).
    C'est à ce moment que la commission de l'agent, s'il y en a un, est créditée sur son solde."""
    if not cle_admin_valide(request):
        return jsonify({"erreur": "Accès non autorisé"}), 401
    transfert = TransfertArgent.query.get_or_404(transfert_id)
    if transfert.statut != "initie":
        return jsonify({"erreur": "Ce transfert n'est plus en attente de versement."}), 400

    transfert.statut = "verse"
    transfert.date_versement = datetime.utcnow()

    if transfert.agent_id and transfert.commission_agent > 0:
        agent = AgentMarchand.query.get(transfert.agent_id)
        if agent:
            agent.solde_commission = (agent.solde_commission or 0) + transfert.commission_agent
            agent.total_commission_gagnee = (agent.total_commission_gagnee or 0) + transfert.commission_agent

    db.session.commit()
    return jsonify({"message": "Versement confirmé", "transfert": transfert.to_dict()})


@app.route("/api/beneficiaires/<int:beneficiaire_id>/transferts", methods=["GET"])
def transferts_du_beneficiaire(beneficiaire_id):
    Beneficiaire.query.get_or_404(beneficiaire_id)
    transferts = TransfertArgent.query.filter_by(destinataire_id=beneficiaire_id).order_by(TransfertArgent.date_creation.desc()).all()
    return jsonify([t.to_dict() for t in transferts])


@app.route("/api/admin/transferts", methods=["GET"])
def admin_lister_transferts():
    if not cle_admin_valide(request):
        return jsonify({"erreur": "Accès non autorisé"}), 401
    transferts = TransfertArgent.query.order_by(TransfertArgent.date_creation.desc()).all()
    return jsonify([t.to_dict() for t in transferts])


# ---------- AGENTS MARCHANDS (points de transfert d'argent, façon Orange Money) ----------

def generer_code_agent():
    while True:
        code = "AG" + "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(4))
        if not AgentMarchand.query.filter_by(code_agent=code).first():
            return code


@app.route("/api/agents/inscription", methods=["POST"])
def inscription_agent():
    data = request.get_json()
    champs_requis = ["nom", "telephone", "mot_de_passe", "pays"]
    manquants = [c for c in champs_requis if not data.get(c)]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400
    if AgentMarchand.query.filter_by(telephone=data["telephone"]).first():
        return jsonify({"erreur": "Ce numéro de téléphone est déjà enregistré comme agent"}), 409

    agent = AgentMarchand(
        nom=data["nom"], telephone=data["telephone"],
        mot_de_passe_hash=generate_password_hash(data["mot_de_passe"]),
        code_agent=generer_code_agent(),
        pays=data["pays"], ville=data.get("ville", ""),
        operateur_mobile_money=data.get("operateur_mobile_money", ""),
        numero_mobile_money=data.get("numero_mobile_money", ""),
    )
    db.session.add(agent)
    db.session.commit()
    return jsonify({"message": "Compte agent créé", "agent": agent.to_dict()}), 201


@app.route("/api/agents/connexion", methods=["POST"])
def connexion_agent():
    data = request.get_json()
    agent = AgentMarchand.query.filter_by(telephone=data.get("telephone")).first()
    if not agent or not check_password_hash(agent.mot_de_passe_hash, data.get("mot_de_passe", "")):
        return jsonify({"erreur": "Téléphone ou mot de passe incorrect"}), 401
    return jsonify({"message": "Connexion réussie", "agent": agent.to_dict()}), 200


@app.route("/api/agents/<int:agent_id>", methods=["GET"])
def obtenir_agent(agent_id):
    agent = AgentMarchand.query.get_or_404(agent_id)
    return jsonify(agent.to_dict())


@app.route("/api/agents/<int:agent_id>/transferts", methods=["GET"])
def transferts_realises_par_agent(agent_id):
    AgentMarchand.query.get_or_404(agent_id)
    transferts = TransfertArgent.query.filter_by(agent_id=agent_id).order_by(TransfertArgent.date_creation.desc()).all()
    return jsonify([t.to_dict() for t in transferts])


@app.route("/api/agents/<int:agent_id>/retrait", methods=["POST"])
def demander_retrait_agent(agent_id):
    agent = AgentMarchand.query.get_or_404(agent_id)
    data = request.get_json() or {}
    montant = data.get("montant", agent.solde_commission)
    if not isinstance(montant, (int, float)) or montant <= 0:
        return jsonify({"erreur": "Montant invalide"}), 400
    if montant > (agent.solde_commission or 0):
        return jsonify({"erreur": "Le montant demandé dépasse ton solde disponible"}), 400

    retrait = RetraitAgent(agent_id=agent_id, montant=montant)
    agent.solde_commission = (agent.solde_commission or 0) - montant
    db.session.add(retrait)
    db.session.commit()
    return jsonify({"message": "Demande de retrait enregistrée", "retrait": retrait.to_dict(), "agent": agent.to_dict()}), 201


@app.route("/api/agents/<int:agent_id>/retraits", methods=["GET"])
def historique_retraits_agent(agent_id):
    AgentMarchand.query.get_or_404(agent_id)
    retraits = RetraitAgent.query.filter_by(agent_id=agent_id).order_by(RetraitAgent.date_demande.desc()).all()
    return jsonify([r.to_dict() for r in retraits])


@app.route("/api/admin/agents", methods=["GET"])
def admin_lister_agents():
    if not cle_admin_valide(request):
        return jsonify({"erreur": "Accès non autorisé"}), 401
    agents = AgentMarchand.query.order_by(AgentMarchand.date_inscription.desc()).all()
    return jsonify([a.to_dict() for a in agents])


@app.route("/api/admin/retraits", methods=["GET"])
def admin_lister_retraits():
    if not cle_admin_valide(request):
        return jsonify({"erreur": "Accès non autorisé"}), 401
    retraits = RetraitAgent.query.order_by(RetraitAgent.date_demande.desc()).all()
    return jsonify([r.to_dict() for r in retraits])


@app.route("/api/admin/retraits/<int:retrait_id>/valider", methods=["POST"])
def admin_valider_retrait(retrait_id):
    """Action admin : confirme qu'un retrait d'agent a bien été versé (par virement/mobile money manuel)."""
    if not cle_admin_valide(request):
        return jsonify({"erreur": "Accès non autorisé"}), 401
    retrait = RetraitAgent.query.get_or_404(retrait_id)
    if retrait.statut != "demande":
        return jsonify({"erreur": "Ce retrait a déjà été traité."}), 400
    retrait.statut = "verse"
    retrait.date_versement = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "Retrait validé", "retrait": retrait.to_dict()})


# ---------- NOTAIRES PARTENAIRES (terrains uniquement) ----------

@app.route("/api/notaires-partenaires", methods=["GET"])
def lister_notaires_partenaires():
    pays = request.args.get("pays")
    query = NotairePartenaire.query.filter_by(actif=True)
    if pays:
        query = query.filter_by(pays=pays)
    return jsonify([n.to_dict() for n in query.all()])


@app.route("/api/admin/notaires-partenaires", methods=["POST"])
def admin_ajouter_notaire():
    if not cle_admin_valide(request):
        return jsonify({"erreur": "Accès non autorisé"}), 401
    data = request.get_json()
    if not data.get("nom"):
        return jsonify({"erreur": "Le nom du notaire est requis"}), 400
    notaire = NotairePartenaire(
        nom=data["nom"], ville=data.get("ville", ""), pays=data.get("pays", ""),
        contact=data.get("contact", ""),
    )
    db.session.add(notaire)
    db.session.commit()
    return jsonify({"message": "Notaire ajouté", "notaire": notaire.to_dict()}), 201


@app.route("/api/admin/notaires-partenaires", methods=["GET"])
def admin_lister_notaires():
    if not cle_admin_valide(request):
        return jsonify({"erreur": "Accès non autorisé"}), 401
    notaires = NotairePartenaire.query.order_by(NotairePartenaire.date_ajout.desc()).all()
    return jsonify([n.to_dict() for n in notaires])


@app.route("/api/terrains/<int:terrain_id>/proposer-notaire", methods=["PUT"])
def proposer_notaire_acheteur(terrain_id):
    """L'acheteur propose son propre notaire pour la transaction du terrain."""
    terrain = Terrain.query.get_or_404(terrain_id)
    data = request.get_json()
    if not data.get("nom"):
        return jsonify({"erreur": "Le nom du notaire est requis"}), 400
    terrain.notaire_propose_acheteur_nom = data["nom"]
    terrain.notaire_propose_acheteur_contact = data.get("contact", "")
    db.session.commit()
    if terrain.producteur:
        envoyer_notification_push(
            terrain.producteur.push_token, "Notaire proposé",
            f"Un acheteur a proposé un notaire pour ton terrain « {terrain.titre} ».",
        )
    return jsonify({"message": "Notaire proposé", "terrain": terrain.to_dict()})


# ---------- TERRAINS VÉRIFIÉS ----------

@app.route("/api/producteurs/<int:producteur_id>/terrains", methods=["POST"])
def ajouter_terrain(producteur_id):
    Producteur.query.get_or_404(producteur_id)
    data = request.get_json()
    champs_requis = ["titre", "prix_total"]
    manquants = [c for c in champs_requis if data.get(c) is None]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400

    photos_urls = data.get("photos_urls", [])
    if not isinstance(photos_urls, list):
        photos_urls = []

    terrain = Terrain(
        producteur_id=producteur_id, titre=data["titre"], description=data.get("description", ""),
        superficie=data.get("superficie"), unite_superficie=data.get("unite_superficie", "m²"),
        prix_total=data["prix_total"], ville=data.get("ville", ""), pays=data.get("pays", ""),
        latitude=data.get("latitude"), longitude=data.get("longitude"),
        photos_urls=json.dumps(photos_urls[:4]),
        notaire_nom=data.get("notaire_nom", ""), notaire_contact=data.get("notaire_contact", ""),
    )
    db.session.add(terrain)
    db.session.commit()
    return jsonify({"message": "Terrain publié", "terrain": terrain.to_dict()}), 201


@app.route("/api/terrains", methods=["GET"])
def lister_terrains():
    terrains = Terrain.query.filter_by(actif=True).order_by(Terrain.date_ajout.desc()).all()
    return jsonify([t.to_dict() for t in terrains])


@app.route("/api/producteurs/<int:producteur_id>/terrains", methods=["GET"])
def terrains_du_producteur(producteur_id):
    Producteur.query.get_or_404(producteur_id)
    terrains = Terrain.query.filter_by(producteur_id=producteur_id).order_by(Terrain.date_ajout.desc()).all()
    return jsonify([t.to_dict() for t in terrains])


@app.route("/api/admin/terrains/<int:terrain_id>/verifier", methods=["PUT"])
def admin_verifier_terrain(terrain_id):
    if not cle_admin_valide(request):
        return jsonify({"erreur": "Accès non autorisé"}), 401
    terrain = Terrain.query.get_or_404(terrain_id)
    terrain.verifie_admin = bool(request.get_json().get("verifie_admin", True))
    db.session.commit()
    return jsonify({"message": "Statut de vérification mis à jour", "terrain": terrain.to_dict()})


@app.route("/api/admin/terrains", methods=["GET"])
def admin_lister_terrains():
    if not cle_admin_valide(request):
        return jsonify({"erreur": "Accès non autorisé"}), 401
    terrains = Terrain.query.order_by(Terrain.date_ajout.desc()).all()
    return jsonify([t.to_dict() for t in terrains])


# ---------- ACHETEURS ----------

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
        nom=data["nom"], telephone=data["telephone"],
        mot_de_passe_hash=generate_password_hash(data["mot_de_passe"]),
        pays=data["pays"], ville=data["ville"], adresse_livraison=data.get("adresse_livraison", ""),
        latitude=data.get("latitude"), longitude=data.get("longitude"),
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
    acheteur.push_token = request.get_json().get("push_token", "")
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
        acheteur_id=data["acheteur_id"], produit_id=data["produit_id"], quantite=quantite,
        prix_total=prix_total, statut="en_attente",
        latitude_livraison=data.get("latitude_livraison"), longitude_livraison=data.get("longitude_livraison"),
        frais_livraison=data.get("frais_livraison") or 0,
    )
    commande.calculer_montants()
    db.session.add(commande)
    db.session.commit()
    if produit.producteur:
        envoyer_notification_push(produit.producteur.push_token, "Nouvelle commande reçue",
                                   f"{acheteur.nom} a commandé {produit.nom}")
        envoyer_sms(produit.producteur.telephone, produit.producteur.pays,
                    f"AgriChange : nouvelle commande de {acheteur.nom} pour {produit.nom}. Ouvre l'app pour confirmer.")
    return jsonify({"message": "Commande créée", "commande": commande.to_dict()}), 201


@app.route("/api/paniers/commander", methods=["POST"])
def commander_panier():
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
    frais_livraison_total = data.get("frais_livraison") or 0
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
            acheteur_id=data["acheteur_id"], produit_id=produit_id, quantite=quantite,
            prix_total=prix_total, statut="en_attente", panier_id=panier_id,
            latitude_livraison=latitude_livraison, longitude_livraison=longitude_livraison,
        )
        commande.calculer_montants()
        db.session.add(commande)
        commandes_creees.append(commande)

    if not commandes_creees:
        return jsonify({"erreur": "Aucun article valide dans le panier"}), 400

    if frais_livraison_total:
        part = round(frais_livraison_total / len(commandes_creees), 2)
        for commande in commandes_creees:
            commande.frais_livraison = part

    db.session.commit()

    for commande in commandes_creees:
        if commande.produit and commande.produit.producteur:
            envoyer_notification_push(commande.produit.producteur.push_token, "Nouvelle commande reçue",
                                       f"{acheteur.nom} a commandé {commande.produit.nom}")
            envoyer_sms(commande.produit.producteur.telephone, commande.produit.producteur.pays,
                        f"AgriChange : nouvelle commande de {acheteur.nom} pour {commande.produit.nom}. Ouvre l'app pour confirmer.")

    return jsonify({
        "message": "Panier validé", "panier_id": panier_id,
        "commandes": [c.to_dict() for c in commandes_creees],
    }), 201


@app.route("/api/commandes/<int:commande_id>", methods=["GET"])
def obtenir_commande(commande_id):
    return jsonify(Commande.query.get_or_404(commande_id).to_dict())


@app.route("/api/commandes/<int:commande_id>/position", methods=["PUT"])
def mettre_a_jour_position_livreur(commande_id):
    commande = Commande.query.get_or_404(commande_id)
    data = request.get_json()
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    if latitude is None or longitude is None:
        return jsonify({"erreur": "latitude et longitude requis"}), 400
    commande.latitude_livreur = latitude
    commande.longitude_livreur = longitude
    commande.position_livreur_maj = datetime.utcnow()
    db.session.add(TrajetPoint(commande_id=commande_id, latitude=latitude, longitude=longitude))
    db.session.commit()
    return jsonify({"message": "Position mise à jour", "commande": commande.to_dict()})


@app.route("/api/commandes/<int:commande_id>/trajet", methods=["GET"])
def obtenir_trajet_livraison(commande_id):
    """Trace complète des positions GPS enregistrées pendant la livraison, pour la traçabilité."""
    Commande.query.get_or_404(commande_id)
    points = TrajetPoint.query.filter_by(commande_id=commande_id).order_by(TrajetPoint.horodatage.asc()).all()
    return jsonify([p.to_dict() for p in points])


@app.route("/api/acheteurs/<int:acheteur_id>/commandes", methods=["GET"])
def commandes_de_lacheteur(acheteur_id):
    Acheteur.query.get_or_404(acheteur_id)
    commandes = Commande.query.filter_by(acheteur_id=acheteur_id).order_by(Commande.date_commande.desc()).all()
    return jsonify([c.to_dict() for c in commandes])


@app.route("/api/producteurs/<int:producteur_id>/commandes", methods=["GET"])
def commandes_du_producteur(producteur_id):
    Producteur.query.get_or_404(producteur_id)
    commandes = Commande.query.join(Produit).filter(Produit.producteur_id == producteur_id).order_by(Commande.date_commande.desc()).all()
    return jsonify([c.to_dict() for c in commandes])


@app.route("/api/commandes/<int:commande_id>/statut", methods=["PUT"])
def modifier_statut_commande(commande_id):
    commande = Commande.query.get_or_404(commande_id)
    nouveau_statut = request.get_json().get("statut")
    if nouveau_statut not in STATUTS_COMMANDE:
        return jsonify({"erreur": f"Statut invalide. Options: {', '.join(STATUTS_COMMANDE)}"}), 400
    commande.statut = nouveau_statut
    db.session.commit()
    if commande.acheteur:
        label = LABELS_STATUT_COMMANDE.get(nouveau_statut, nouveau_statut)
        nom_produit = commande.produit.nom if commande.produit else "ta commande"
        envoyer_notification_push(commande.acheteur.push_token, "Mise à jour de ta commande", f"{nom_produit} : {label}")
    return jsonify({"message": "Statut mis à jour", "commande": commande.to_dict()})


@app.route("/api/commandes/<int:commande_id>/annuler", methods=["PUT"])
def annuler_commande(commande_id):
    """Annule une commande. Si un livreur avait déjà pris le colis en charge, il reste
    indemnisé une fois que le producteur confirme avoir récupéré le colis retourné."""
    commande = Commande.query.get_or_404(commande_id)
    if commande.statut in ("livree", "terminee", "annulee"):
        return jsonify({"erreur": "Cette commande ne peut plus être annulée"}), 409

    annule_par = request.get_json().get("annule_par", "inconnu") if request.get_json() else "inconnu"
    commande.statut = "annulee"
    db.session.commit()

    if commande.livreur and commande.produit and commande.produit.producteur:
        producteur = commande.produit.producteur
        envoyer_notification_push(
            producteur.push_token, "Commande annulée",
            f"La commande « {commande.produit.nom} » a été annulée. Merci de récupérer le colis auprès du livreur et de confirmer le retour dans l'app.",
        )
        envoyer_sms(
            producteur.telephone, producteur.pays,
            f"AgriChange : commande annulée pour {commande.produit.nom}. Récupère le colis auprès du livreur et confirme le retour dans l'app.",
        )
        envoyer_notification_push(
            commande.livreur.push_token, "Livraison annulée",
            "La commande a été annulée. Ramène le colis au vendeur ; tu seras indemnisé une fois le retour confirmé.",
        )

    return jsonify({"message": "Commande annulée", "commande": commande.to_dict()})


@app.route("/api/commandes/<int:commande_id>/confirmer-retour", methods=["PUT"])
def confirmer_retour_colis(commande_id):
    """Le producteur confirme avoir récupéré le colis retourné après annulation :
    le livreur reste indemnisé pour ses frais de livraison déjà engagés."""
    commande = Commande.query.get_or_404(commande_id)
    if commande.statut != "annulee":
        return jsonify({"erreur": "Cette commande n'est pas annulée"}), 409
    if not commande.livreur_id:
        return jsonify({"erreur": "Aucun livreur n'était assigné à cette commande"}), 400

    commande.retour_confirme = True
    if commande.frais_livraison and commande.frais_livraison > 0:
        commande.statut_paiement_livreur = "du"
    db.session.commit()

    if commande.livreur:
        envoyer_notification_push(
            commande.livreur.push_token, "Retour confirmé",
            f"Le vendeur a confirmé la récupération du colis. Tes frais de livraison ({commande.frais_livraison or 0} FCFA) te seront versés dès l'activation du paiement en ligne.",
        )
        envoyer_sms(
            commande.livreur.telephone, commande.livreur.pays,
            f"AgriChange : retour de colis confirmé. Tes frais de livraison ({commande.frais_livraison or 0} FCFA) sont dus et te seront versés dès l'activation du paiement en ligne.",
        )

    return jsonify({"message": "Retour confirmé, livreur indemnisé", "commande": commande.to_dict()})


# ---------- MESSAGERIE ----------

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
        acheteur_id=data["acheteur_id"], producteur_id=data["producteur_id"], produit_id=data.get("produit_id"),
        expediteur_type=data["expediteur_type"], contenu_original=data["contenu"],
        contenu_filtre=contenu_filtre, contient_infraction=contient_infraction,
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
    acheteur_id = request.args.get("acheteur_id", type=int)
    producteur_id = request.args.get("producteur_id", type=int)
    if not acheteur_id or not producteur_id:
        return jsonify({"erreur": "acheteur_id et producteur_id requis"}), 400
    messages = Message.query.filter_by(acheteur_id=acheteur_id, producteur_id=producteur_id).order_by(Message.date_envoi.asc()).all()
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
    producteur.verifie = bool(request.get_json().get("verifie", True))
    db.session.commit()
    return jsonify({"message": "Statut de vérification mis à jour", "producteur": producteur.to_dict()})


@app.route("/api/admin/producteurs/<int:producteur_id>/actif", methods=["PUT"])
def admin_toggle_actif_producteur(producteur_id):
    if not cle_admin_valide(request):
        return jsonify({"erreur": "Accès non autorisé"}), 401
    producteur = Producteur.query.get_or_404(producteur_id)
    producteur.actif = bool(request.get_json().get("actif", True))
    db.session.commit()
    return jsonify({"message": "Statut mis à jour", "producteur": producteur.to_dict()})


@app.route("/api/admin/producteurs/<int:producteur_id>/premium", methods=["PUT"])
def admin_toggle_premium_producteur(producteur_id):
    if not cle_admin_valide(request):
        return jsonify({"erreur": "Accès non autorisé"}), 401
    producteur = Producteur.query.get_or_404(producteur_id)
    producteur.premium = bool(request.get_json().get("premium", True))
    db.session.commit()
    return jsonify({"message": "Statut premium mis à jour", "producteur": producteur.to_dict()})


@app.route("/api/admin/producteurs/<int:producteur_id>/credits", methods=["PUT"])
def admin_reinitialiser_credits(producteur_id):
    if not cle_admin_valide(request):
        return jsonify({"erreur": "Accès non autorisé"}), 401
    producteur = Producteur.query.get_or_404(producteur_id)
    producteur.credits_outils = int(request.get_json().get("credits", 10))
    db.session.commit()
    return jsonify({"message": "Crédits mis à jour", "producteur": producteur.to_dict()})


@app.route("/api/admin/codes-premium", methods=["POST"])
def admin_generer_code_premium():
    if not cle_admin_valide(request):
        return jsonify({"erreur": "Accès non autorisé"}), 401
    while True:
        code_genere = secrets.token_hex(4).upper()
        if not CodePremium.query.filter_by(code=code_genere).first():
            break
    code = CodePremium(code=code_genere)
    db.session.add(code)
    db.session.commit()
    return jsonify({"message": "Code généré", "code_premium": code.to_dict()}), 201


@app.route("/api/admin/codes-premium", methods=["GET"])
def admin_lister_codes_premium():
    if not cle_admin_valide(request):
        return jsonify({"erreur": "Accès non autorisé"}), 401
    codes = CodePremium.query.order_by(CodePremium.date_creation.desc()).all()
    return jsonify([c.to_dict() for c in codes])


@app.route("/api/admin/statistiques", methods=["GET"])
def admin_statistiques():
    if not cle_admin_valide(request):
        return jsonify({"erreur": "Accès non autorisé"}), 401
    return jsonify({
        "nombre_producteurs": Producteur.query.count(),
        "nombre_acheteurs": Acheteur.query.count(),
        "nombre_livreurs": Livreur.query.count(),
        "nombre_produits": Produit.query.count(),
        "commandes_totales": Commande.query.count(),
        "livraisons_reussies": Commande.query.filter(Commande.statut.in_(["livree", "terminee"])).count(),
    })


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
