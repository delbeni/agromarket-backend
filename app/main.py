from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from models import (
    db, Producteur, Produit, Acheteur, Commande, Message, Avis, Favori, TicketSupport,
    Livreur, HistoriquePrix, AchatGroupe, ParticipationGroupe, BesoinFinancement,
    PromesseFinancement, Terrain, CodePremium, NotairePartenaire, Beneficiaire, TransfertArgent,
    AgentMarchand, RetraitAgent, RechargeAgent,
    Hotel, ChambreHotel, ReservationHotel, Restaurant, PlatMenu, CommandeNourriture,
    Commerce,
    OffreTroc, PropositionTroc, JourMarche, Tontine, MembreTontine, CotisationTontine,
    OffreEmploi, Candidature, OpportuniteInvestissement,
    CourseTaxi,
    TrajetPoint, RecolteFuture, ReservationRecolte, Cooperative, MembreCooperative, Invendu, Signalement,
    NumeroMobileMoney,
    LotTracabilite, EtapeTracabilite,
)
import os
import re
import json
import secrets
import urllib.request
import urllib.parse
import math
from datetime import datetime

# ---------- Configuration PayDunya ----------
# Ces clés sont à définir en variables d'environnement sur Render (Dashboard > Environment).
# En attendant d'avoir les vraies clés de production, utilise les clés TEST fournies par PayDunya.
PAYDUNYA_MASTER_KEY = os.environ.get("PAYDUNYA_MASTER_KEY", "")
PAYDUNYA_PRIVATE_KEY = os.environ.get("PAYDUNYA_PRIVATE_KEY", "")
PAYDUNYA_PUBLIC_KEY = os.environ.get("PAYDUNYA_PUBLIC_KEY", "")
PAYDUNYA_TOKEN = os.environ.get("PAYDUNYA_TOKEN", "")
PAYDUNYA_MODE = os.environ.get("PAYDUNYA_MODE", "test")  # "test" ou "live"
PAYDUNYA_API_BASE = "https://app.paydunya.com/api/v1"

app = Flask(__name__)
CORS(app)

basedir = os.path.abspath(os.path.dirname(__file__))
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL:
    # Render (et Heroku) fournissent parfois "postgres://" au lieu de "postgresql://",
    # que SQLAlchemy exige depuis ses versions récentes.
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
else:
    # Repli local (sur ton PC, sans variable d'environnement définie) : fichier SQLite comme avant.
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(basedir, 'agromarket.db')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

with app.app_context():
    db.create_all()

    # "Mini-migration" automatique : ajoute les colonnes créées après le premier lancement
    # de la base (db.create_all() ne modifie jamais les tables déjà existantes).
    # Sans danger : ADD COLUMN IF NOT EXISTS ne touche à rien si la colonne existe déjà.
    if DATABASE_URL:
        colonnes_a_ajouter = [
            "ALTER TABLE produits ADD COLUMN IF NOT EXISTS mis_en_avant BOOLEAN DEFAULT false",
            "ALTER TABLE produits ADD COLUMN IF NOT EXISTS mise_en_avant_expire TIMESTAMP",
            "ALTER TABLE producteurs ADD COLUMN IF NOT EXISTS premium_expire TIMESTAMP",
            "ALTER TABLE commandes ADD COLUMN IF NOT EXISTS paiement_statut VARCHAR(20) DEFAULT 'non_paye'",
            "ALTER TABLE commandes ADD COLUMN IF NOT EXISTS date_paiement TIMESTAMP",
            "ALTER TABLE commandes ADD COLUMN IF NOT EXISTS date_liberation_paiement TIMESTAMP",
            "ALTER TABLE commandes ADD COLUMN IF NOT EXISTS transporteur_externe VARCHAR(50)",
            "ALTER TABLE commandes ADD COLUMN IF NOT EXISTS numero_suivi_externe VARCHAR(100)",
            "ALTER TABLE livreurs ADD COLUMN IF NOT EXISTS numero_permis_conduire VARCHAR(50)",
            "ALTER TABLE livreurs ADD COLUMN IF NOT EXISTS permis_conduire_recto VARCHAR(255)",
            "ALTER TABLE livreurs ADD COLUMN IF NOT EXISTS permis_conduire_verso VARCHAR(255)",
            "ALTER TABLE cotisations_tontine ADD COLUMN IF NOT EXISTS commission_montant FLOAT DEFAULT 0",
            "ALTER TABLE cotisations_tontine ADD COLUMN IF NOT EXISTS montant_net FLOAT",
            "ALTER TABLE cotisations_tontine ALTER COLUMN statut SET DEFAULT 'en_attente'",
            "ALTER TABLE membres_tontine ADD COLUMN IF NOT EXISTS operateur_mobile_money VARCHAR(30)",
            "ALTER TABLE membres_tontine ADD COLUMN IF NOT EXISTS numero_mobile_money VARCHAR(30)",
            "ALTER TABLE membres_tontine ADD COLUMN IF NOT EXISTS nom_complet_mobile_money VARCHAR(150)",
            "ALTER TABLE messages ADD COLUMN IF NOT EXISTS audio_url VARCHAR(255)",
            "ALTER TABLE courses_taxi ADD COLUMN IF NOT EXISTS vehicule_souhaite VARCHAR(20) DEFAULT 'peu_importe'",
            "ALTER TABLE courses_taxi ADD COLUMN IF NOT EXISTS prix_contre_propose FLOAT",
            "ALTER TABLE courses_taxi ADD COLUMN IF NOT EXISTS latitude_livreur FLOAT",
            "ALTER TABLE courses_taxi ADD COLUMN IF NOT EXISTS longitude_livreur FLOAT",
            "ALTER TABLE courses_taxi ADD COLUMN IF NOT EXISTS position_livreur_maj TIMESTAMP",
            "ALTER TABLE commandes_nourriture ADD COLUMN IF NOT EXISTS latitude_livraison FLOAT",
            "ALTER TABLE commandes_nourriture ADD COLUMN IF NOT EXISTS longitude_livraison FLOAT",
        ]
        from sqlalchemy import text as _sql_text
        with db.engine.connect() as _conn:
            for _stmt in colonnes_a_ajouter:
                try:
                    _conn.execute(_sql_text(_stmt))
                    _conn.commit()
                except Exception:
                    _conn.rollback()

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
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
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


@app.route("/api/traduire-message", methods=["POST"])
def traduire_message():
    """Traduit un message de chat à la demande, dans la langue choisie par le lecteur."""
    if not ANTHROPIC_API_KEY:
        return jsonify({"erreur": "La traduction n'est pas encore configurée sur le serveur."}), 503

    data = request.get_json()
    texte = (data.get("texte") or "").strip()
    langue_cible = (data.get("langue_cible") or "fr").strip()
    noms_langues = {"fr": "français", "en": "anglais", "pt": "portugais", "zh": "chinois (mandarin)"}
    if not texte:
        return jsonify({"erreur": "Le texte à traduire est requis"}), 400

    consigne = (
        f"Traduis ce message en {noms_langues.get(langue_cible, 'français')}, sans rien ajouter ni expliquer, "
        f"juste la traduction directe, en gardant le ton naturel d'une conversation :\n\n« {texte} »"
    )
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 300,
        "messages": [{"role": "user", "content": consigne}],
    }
    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as res:
            reponse = json.loads(res.read().decode("utf-8"))
        traduction = "".join(bloc.get("text", "") for bloc in reponse.get("content", []) if bloc.get("type") == "text")
        if not traduction.strip():
            return jsonify({"erreur": "Traduction vide, réessaie."}), 500
        return jsonify({"texte_traduit": traduction.strip()})
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        return jsonify({"erreur": f"[DEBUG TEMPORAIRE] HTTP {e.code}: {detail}"}), 500
    except Exception as e:
        return jsonify({"erreur": f"[DEBUG TEMPORAIRE] {type(e).__name__}: {str(e)}"}), 500


@app.route("/api/aide-ia-texte", methods=["POST"])
def aide_ia_texte():
    """Améliore/réécrit un texte déjà rédigé par l'utilisateur (description produit, histoire,
    annonce d'emploi, description de terrain...). Réutilisable partout dans l'app."""
    if not ANTHROPIC_API_KEY:
        return jsonify({"erreur": "Le générateur IA n'est pas encore configuré sur le serveur."}), 503

    data = request.get_json()
    texte = (data.get("texte") or "").strip()
    contexte = (data.get("contexte") or "un texte pour une application agricole africaine").strip()
    if not texte:
        return jsonify({"erreur": "Le texte à améliorer est requis"}), 400

    consigne = (
        f"Voici {contexte}, écrit par un utilisateur d'AgriChange (marché agricole africain) :\n\n"
        f"« {texte} »\n\n"
        "Réécris-le en français correct, clair et bien organisé, en gardant toutes les informations "
        "d'origine et le même sens. Corrige l'orthographe et la grammaire, améliore la fluidité, "
        "mais reste concis (ne rallonge pas inutilement). Réponds uniquement avec le texte amélioré, "
        "sans aucun préambule ni guillemets."
    )

    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 400,
        "messages": [{"role": "user", "content": consigne}],
    }
    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=25) as res:
            reponse = json.loads(res.read().decode("utf-8"))
        texte_arrange = "".join(bloc.get("text", "") for bloc in reponse.get("content", []) if bloc.get("type") == "text")
        if not texte_arrange.strip():
            return jsonify({"erreur": "Réponse vide de l'IA, réessaie."}), 500
        return jsonify({"texte": texte_arrange.strip()})
    except Exception:
        return jsonify({"erreur": "Impossible d'améliorer le texte pour le moment. Réessaie dans un instant."}), 500


@app.route("/api/generateur-annonce-ia", methods=["POST"])
def generer_annonce_ia():
    """Génère un vrai texte d'annonce publicitaire via l'IA Claude (Anthropic).
    L'appel à cette route suppose que le crédit du producteur a déjà été vérifié/consommé
    côté app (même logique que le calculateur), donc pas de nouvelle vérification ici."""
    if not ANTHROPIC_API_KEY:
        return jsonify({"erreur": "Le générateur IA n'est pas encore configuré sur le serveur."}), 503

    data = request.get_json()
    produit = (data.get("produit") or "").strip()
    lieu = (data.get("lieu") or "").strip()
    details = (data.get("details") or "").strip()
    if not produit:
        return jsonify({"erreur": "Le nom du produit est requis"}), 400

    consigne = (
        "Écris une annonce de vente courte, chaleureuse et convaincante en français, pour un marché agricole "
        "africain en ligne (AgriChange). Maximum 4 phrases, ton direct et accessible, avec 1 à 2 emojis pertinents. "
        "Réponds uniquement avec le texte de l'annonce, sans aucun préambule ni guillemets.\n\n"
        f"Produit : {produit}\n"
        + (f"Lieu : {lieu}\n" if lieu else "")
        + (f"Détails : {details}\n" if details else "")
    )

    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 300,
        "messages": [{"role": "user", "content": consigne}],
    }
    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=25) as res:
            reponse = json.loads(res.read().decode("utf-8"))
        texte = "".join(bloc.get("text", "") for bloc in reponse.get("content", []) if bloc.get("type") == "text")
        if not texte.strip():
            return jsonify({"erreur": "Réponse vide de l'IA, réessaie."}), 500
        return jsonify({"texte": texte.strip()})
    except Exception:
        return jsonify({"erreur": "Impossible de générer l'annonce pour le moment. Réessaie dans un instant."}), 500


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
        numero_permis_conduire=data.get("numero_permis_conduire", ""),
        permis_conduire_recto=data.get("permis_conduire_recto", ""),
        permis_conduire_verso=data.get("permis_conduire_verso", ""),
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
    # Les produits avec une mise en avant active passent en premier
    resultats.sort(key=lambda d: not d["mis_en_avant_actif"])
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


# ---------- TRAÇABILITÉ PAR QR CODE (lots de production) ----------

def generer_code_lot(nom_produit):
    prefixe = re.sub(r"[^A-Z]", "", (nom_produit or "LOT").upper())[:4] or "LOT"
    annee = datetime.utcnow().year
    while True:
        suffixe = secrets.token_hex(2).upper()
        code = f"{prefixe}-{annee}-{suffixe}"
        if not LotTracabilite.query.filter_by(code_lot=code).first():
            return code


@app.route("/api/producteurs/<int:producteur_id>/lots-tracabilite", methods=["POST"])
def creer_lot_tracabilite(producteur_id):
    Producteur.query.get_or_404(producteur_id)
    data = request.get_json()
    champs_requis = ["nom_produit", "quantite"]
    manquants = [c for c in champs_requis if data.get(c) is None]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400

    date_recolte = None
    if data.get("date_recolte"):
        try:
            date_recolte = datetime.strptime(data["date_recolte"], "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"erreur": "Format de date invalide (AAAA-MM-JJ attendu)"}), 400

    lot = LotTracabilite(
        code_lot=generer_code_lot(data["nom_produit"]),
        producteur_id=producteur_id, produit_id=data.get("produit_id"),
        nom_produit=data["nom_produit"], quantite=data["quantite"], unite=data.get("unite", "kg"),
        origine_ville=data.get("origine_ville", ""), origine_pays=data.get("origine_pays", ""),
        date_recolte=date_recolte, description=data.get("description", ""),
    )
    db.session.add(lot)
    db.session.commit()
    return jsonify({"message": "Lot créé, QR code généré", "lot": lot.to_dict()}), 201


@app.route("/api/producteurs/<int:producteur_id>/lots-tracabilite", methods=["GET"])
def lister_lots_producteur(producteur_id):
    Producteur.query.get_or_404(producteur_id)
    lots = LotTracabilite.query.filter_by(producteur_id=producteur_id).order_by(LotTracabilite.date_creation.desc()).all()
    return jsonify([l.to_dict() for l in lots])


@app.route("/api/lots-tracabilite/<string:code_lot>", methods=["GET"])
def consulter_lot_tracabilite(code_lot):
    """Consultation publique d'un lot en scannant son QR code (aucun compte requis).
    Incrémente le compteur de scans et signale un scan suspect si le lot est déjà 'reçu'
    mais continue d'être scanné de façon inhabituelle (indice possible de contrefaçon)."""
    lot = LotTracabilite.query.filter_by(code_lot=code_lot).first()
    if not lot:
        return jsonify({"erreur": "Code de traçabilité introuvable. Ce produit n'est peut-être pas authentique."}), 404

    lot.nombre_scans = (lot.nombre_scans or 0) + 1
    db.session.commit()

    resultat = lot.to_dict()
    resultat["etapes"] = [e.to_dict() for e in lot.etapes]

    deja_recu = any(e.type_etape == "reception" for e in lot.etapes)
    if deja_recu and lot.nombre_scans > 20:
        resultat["alerte_fraude"] = (
            "⚠️ Ce code a déjà été vérifié un très grand nombre de fois après réception. "
            "Vérifie l'authenticité du produit auprès du vendeur."
        )

    return jsonify(resultat)


@app.route("/api/lots-tracabilite/<string:code_lot>/etapes", methods=["POST"])
def ajouter_etape_tracabilite(code_lot):
    lot = LotTracabilite.query.filter_by(code_lot=code_lot).first()
    if not lot:
        return jsonify({"erreur": "Code de traçabilité introuvable"}), 404

    data = request.get_json()
    type_etape = data.get("type_etape")
    if type_etape not in EtapeTracabilite.TYPES_VALIDES:
        return jsonify({"erreur": f"type_etape invalide. Options: {', '.join(EtapeTracabilite.TYPES_VALIDES)}"}), 400

    etape = EtapeTracabilite(
        lot_id=lot.id, type_etape=type_etape,
        agent_nom=data.get("agent_nom", ""), agent_telephone=data.get("agent_telephone", ""),
        latitude=data.get("latitude"), longitude=data.get("longitude"),
        details=data.get("details", ""),
    )
    db.session.add(etape)
    db.session.commit()

    if lot.producteur:
        envoyer_notification_push(
            lot.producteur.push_token, "Nouvelle étape de traçabilité",
            f"Ton lot {lot.code_lot} ({lot.nom_produit}) vient de passer l'étape : {type_etape}.",
        )

    return jsonify({"message": "Étape enregistrée", "etape": etape.to_dict()}), 201


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
        type_piece_identite=data.get("type_piece_identite", ""),
        numero_piece_identite=data.get("numero_piece_identite", ""),
        piece_identite_recto=data.get("piece_identite_recto", ""),
        piece_identite_verso=data.get("piece_identite_verso", ""),
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


@app.route("/api/agents/<int:agent_id>/piece-identite", methods=["PUT"])
def enregistrer_piece_identite_agent(agent_id):
    """L'agent doit fournir sa pièce d'identité avant de pouvoir traiter des transferts pour des clients."""
    agent = AgentMarchand.query.get_or_404(agent_id)
    data = request.get_json() or {}
    if data.get("piece_identite_recto"):
        agent.piece_identite_recto = data["piece_identite_recto"]
    if data.get("piece_identite_verso"):
        agent.piece_identite_verso = data["piece_identite_verso"]
    db.session.commit()
    return jsonify({"message": "Pièce d'identité enregistrée, en attente de vérification", "agent": agent.to_dict()})


@app.route("/api/admin/agents/<int:agent_id>/verifier-identite", methods=["POST"])
def admin_verifier_identite_agent(agent_id):
    if not cle_admin_valide(request):
        return jsonify({"erreur": "Accès non autorisé"}), 401
    agent = AgentMarchand.query.get_or_404(agent_id)
    agent.identite_verifiee = True
    db.session.commit()
    return jsonify({"message": "Identité de l'agent vérifiée", "agent": agent.to_dict()})


# ---------- RECHARGE DU SOLDE AGENT (dépôt bancaire / mobile money fait par l'agent lui-même) ----------

@app.route("/api/agents/<int:agent_id>/recharge", methods=["POST"])
def demander_recharge_agent(agent_id):
    """L'agent déclare avoir fait un dépôt (banque ou mobile money) vers AgriChange pour créditer
    son solde de trésorerie. La demande reste en attente jusqu'à validation admin."""
    agent = AgentMarchand.query.get_or_404(agent_id)
    if not agent.identite_verifiee:
        return jsonify({"erreur": "Ton identité doit d'abord être vérifiée avant de pouvoir recharger ton solde."}), 403
    data = request.get_json() or {}
    montant = data.get("montant")
    if not isinstance(montant, (int, float)) or montant <= 0:
        return jsonify({"erreur": "Montant invalide"}), 400
    if not data.get("methode"):
        return jsonify({"erreur": "Précise la méthode de dépôt (banque ou mobile money)"}), 400

    recharge = RechargeAgent(
        agent_id=agent_id, montant=montant,
        methode=data["methode"], reference=data.get("reference", ""),
    )
    db.session.add(recharge)
    db.session.commit()
    return jsonify({"message": "Demande de recharge enregistrée, en attente de validation", "recharge": recharge.to_dict()}), 201


@app.route("/api/agents/<int:agent_id>/recharges", methods=["GET"])
def historique_recharges_agent(agent_id):
    AgentMarchand.query.get_or_404(agent_id)
    recharges = RechargeAgent.query.filter_by(agent_id=agent_id).order_by(RechargeAgent.date_demande.desc()).all()
    return jsonify([r.to_dict() for r in recharges])


@app.route("/api/admin/recharges", methods=["GET"])
def admin_lister_recharges():
    if not cle_admin_valide(request):
        return jsonify({"erreur": "Accès non autorisé"}), 401
    recharges = RechargeAgent.query.order_by(RechargeAgent.date_demande.desc()).all()
    return jsonify([r.to_dict() for r in recharges])


@app.route("/api/admin/recharges/<int:recharge_id>/valider", methods=["POST"])
def admin_valider_recharge(recharge_id):
    """Action admin : après vérification que le dépôt bancaire/mobile money a bien été reçu,
    crédite le solde de trésorerie de l'agent."""
    if not cle_admin_valide(request):
        return jsonify({"erreur": "Accès non autorisé"}), 401
    recharge = RechargeAgent.query.get_or_404(recharge_id)
    if recharge.statut != "demande":
        return jsonify({"erreur": "Cette recharge a déjà été traitée."}), 400
    agent = AgentMarchand.query.get(recharge.agent_id)
    agent.solde_disponible = (agent.solde_disponible or 0) + recharge.montant
    recharge.statut = "validee"
    recharge.date_validation = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "Recharge validée et créditée", "recharge": recharge.to_dict(), "agent": agent.to_dict()})


@app.route("/api/admin/recharges/<int:recharge_id>/rejeter", methods=["POST"])
def admin_rejeter_recharge(recharge_id):
    if not cle_admin_valide(request):
        return jsonify({"erreur": "Accès non autorisé"}), 401
    recharge = RechargeAgent.query.get_or_404(recharge_id)
    if recharge.statut != "demande":
        return jsonify({"erreur": "Cette recharge a déjà été traitée."}), 400
    recharge.statut = "rejetee"
    db.session.commit()
    return jsonify({"message": "Recharge rejetée", "recharge": recharge.to_dict()})


# ---------- TRANSFERT DIRECT PAR L'AGENT (modèle kiosque : client paie cash à l'agent) ----------

@app.route("/api/agents/<int:agent_id>/transferts-clients", methods=["POST"])
def creer_transfert_par_agent(agent_id):
    """L'agent réalise lui-même un transfert pour un client qui lui a remis du cash.
    Le montant net envoyé au bénéficiaire est débité du solde de trésorerie de l'agent (solde_disponible).
    Les frais de service que le client a payés en cash restent directement dans la poche de l'agent
    (pas de mouvement électronique nécessaire pour cette part)."""
    agent = AgentMarchand.query.get_or_404(agent_id)
    if not agent.identite_verifiee:
        return jsonify({"erreur": "Ton identité doit d'abord être vérifiée avant de traiter des transferts."}), 403

    data = request.get_json()
    champs_requis = ["destinataire_id", "expediteur_nom", "montant"]
    manquants = [c for c in champs_requis if data.get(c) is None]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400

    beneficiaire = Beneficiaire.query.get_or_404(data["destinataire_id"])
    montant = data["montant"]
    if not isinstance(montant, (int, float)) or montant <= 0:
        return jsonify({"erreur": "Montant invalide"}), 400
    if montant > (agent.solde_disponible or 0):
        return jsonify({"erreur": "Solde de trésorerie insuffisant. Recharge ton compte avant de traiter ce transfert."}), 400

    frais_service = float(data.get("frais_service") or 0)

    transfert = TransfertArgent(
        destinataire_id=data["destinataire_id"], expediteur_nom=data["expediteur_nom"],
        expediteur_telephone=data.get("expediteur_telephone", ""), expediteur_pays=data.get("expediteur_pays", agent.pays),
        montant=montant, message=data.get("message", ""),
        agent_id=agent.id, origine="agent_kiosque",
        frais_service=frais_service, commission_agent=0.0,  # déjà en cash dans la poche de l'agent
        statut="verse", date_versement=datetime.utcnow(),  # l'agent a déjà versé le cash lui-même
    )
    agent.solde_disponible = (agent.solde_disponible or 0) - montant
    db.session.add(transfert)
    db.session.commit()

    envoyer_notification_push(
        beneficiaire.push_token, "Transfert d'argent reçu",
        f"{data['expediteur_nom']} t'envoie {montant} FCFA via un agent AgriChange.",
    )
    envoyer_sms(
        beneficiaire.telephone, beneficiaire.pays,
        f"AgriChange : {data['expediteur_nom']} t'a envoyé {montant} FCFA via un agent partenaire. Ouvre l'app pour voir le détail.",
    )

    return jsonify({"message": "Transfert traité", "transfert": transfert.to_dict(), "agent": agent.to_dict()}), 201


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
    champs_requis = ["acheteur_id", "producteur_id", "expediteur_type"]
    manquants = [c for c in champs_requis if not data.get(c)]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400
    if not data.get("contenu") and not data.get("audio_url"):
        return jsonify({"erreur": "contenu ou audio_url requis"}), 400
    if data["expediteur_type"] not in ("acheteur", "producteur"):
        return jsonify({"erreur": "expediteur_type doit être 'acheteur' ou 'producteur'"}), 400
    acheteur = Acheteur.query.get_or_404(data["acheteur_id"])
    producteur = Producteur.query.get_or_404(data["producteur_id"])

    audio_url = data.get("audio_url", "")
    if audio_url:
        # Message vocal : pas de filtrage de texte à appliquer (rien à masquer dans un fichier audio).
        contenu_original = "[Message vocal]"
        contenu_filtre = "[Message vocal]"
        contient_infraction = False
    else:
        contenu_filtre, contient_infraction = filtrer_message(data["contenu"])
        contenu_original = data["contenu"]

    message = Message(
        acheteur_id=data["acheteur_id"], producteur_id=data["producteur_id"], produit_id=data.get("produit_id"),
        expediteur_type=data["expediteur_type"], contenu_original=contenu_original,
        contenu_filtre=contenu_filtre, contient_infraction=contient_infraction, audio_url=audio_url,
    )
    db.session.add(message)
    db.session.commit()
    apercu = "🎤 Message vocal" if audio_url else contenu_filtre[:80]
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


@app.route("/api/producteurs/<int:producteur_id>/conversations", methods=["GET"])
def lister_conversations_producteur(producteur_id):
    """Liste toutes les conversations (un acheteur = une conversation) reçues par ce producteur,
    avec le dernier message de chacune — l'équivalent d'une boîte de réception."""
    Producteur.query.get_or_404(producteur_id)
    messages = Message.query.filter_by(producteur_id=producteur_id).order_by(Message.date_envoi.desc()).all()
    conversations = {}
    for m in messages:
        if m.acheteur_id not in conversations:
            conversations[m.acheteur_id] = {
                "acheteur_id": m.acheteur_id,
                "acheteur_nom": m.acheteur.nom if m.acheteur else "Acheteur",
                "dernier_message": "🎤 Message vocal" if m.audio_url else m.contenu_filtre,
                "date_dernier_message": m.date_envoi.isoformat(),
                "produit_id": m.produit_id,
            }
    return jsonify(sorted(conversations.values(), key=lambda c: c["date_dernier_message"], reverse=True))


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
    producteur.credits_outils = int(request.get_json().get("credits", 5))
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


def paydunya_headers():
    return {
        "PAYDUNYA-MASTER-KEY": PAYDUNYA_MASTER_KEY,
        "PAYDUNYA-PRIVATE-KEY": PAYDUNYA_PRIVATE_KEY,
        "PAYDUNYA-PUBLIC-KEY": PAYDUNYA_PUBLIC_KEY,
        "PAYDUNYA-TOKEN": PAYDUNYA_TOKEN,
        "Content-Type": "application/json",
    }


def paydunya_appel_api(chemin, donnees):
    """Envoie une requête POST à l'API PayDunya et retourne la réponse JSON."""
    url = f"{PAYDUNYA_API_BASE}/{chemin}"
    body = json.dumps(donnees).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=paydunya_headers(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            return json.loads(res.read().decode("utf-8")), res.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode("utf-8")), e.code
    except Exception as e:
        return {"response_text": str(e)}, 500


def paydunya_verifier_facture(token):
    """Vérifie le statut réel d'une facture auprès de PayDunya (ne jamais faire confiance à l'IPN seul)."""
    url = f"{PAYDUNYA_API_BASE}/checkout-invoice/confirm/{token}"
    req = urllib.request.Request(url, headers=paydunya_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            return json.loads(res.read().decode("utf-8"))
    except Exception as e:
        return {"status": "erreur", "erreur": str(e)}


# ---------- Types de commande pris en charge par le paiement PayDunya ----------
PAYDUNYA_MODELES = {
    "commande": Commande,
    "commande_nourriture": CommandeNourriture,
    "reservation_hotel": ReservationHotel,
}


@app.route("/api/paiement/paydunya/initier", methods=["POST"])
def paydunya_initier_paiement():
    """Crée une facture PayDunya pour une commande/réservation existante et renvoie l'URL de paiement."""
    data = request.get_json()
    type_commande = data.get("type_commande")
    commande_id = data.get("commande_id")
    if type_commande not in PAYDUNYA_MODELES:
        return jsonify({"erreur": "type_commande invalide"}), 400

    modele = PAYDUNYA_MODELES[type_commande]
    objet = modele.query.get_or_404(commande_id)

    montant = getattr(objet, "prix_total", None) or getattr(objet, "montant_total", None)
    if not montant:
        return jsonify({"erreur": "Impossible de déterminer le montant à payer."}), 400

    payload = {
        "invoice": {
            "total_amount": int(montant),
            "description": f"AgriChange — {type_commande} #{commande_id}",
        },
        "store": {"name": "AgriChange"},
        "actions": {
            "cancel_url": data.get("cancel_url", ""),
            "return_url": data.get("return_url", ""),
            "callback_url": f"{request.url_root.rstrip('/')}/api/paiement/paydunya/ipn",
        },
        "custom_data": {"type_commande": type_commande, "commande_id": commande_id},
    }

    reponse, statut = paydunya_appel_api("checkout-invoice/create", payload)
    if reponse.get("response_code") == "00":
        return jsonify({
            "message": "Facture créée",
            "url_paiement": reponse.get("response_text"),
            "token": reponse.get("token"),
        }), 201
    return jsonify({"erreur": "Échec de la création de la facture PayDunya", "detail": reponse}), 400


@app.route("/api/paiement/paydunya/ipn", methods=["POST"])
def paydunya_ipn():
    """Reçoit la notification de paiement de PayDunya (IPN) et met à jour la commande correspondante.
    Ne fait jamais confiance aux données reçues directement : revérifie toujours le token auprès de PayDunya."""
    donnees_recues = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    token = donnees_recues.get("data[token]") or donnees_recues.get("token")
    if not token:
        return jsonify({"erreur": "Token manquant"}), 400

    verification = paydunya_verifier_facture(token)
    if verification.get("status") != "completed":
        return jsonify({"message": "Paiement non confirmé, aucune action effectuée."}), 200

    custom_data = verification.get("custom_data", {})
    type_commande = custom_data.get("type_commande")
    commande_id = custom_data.get("commande_id")
    modele = PAYDUNYA_MODELES.get(type_commande)
    if not modele or not commande_id:
        return jsonify({"erreur": "custom_data invalide, commande non identifiée"}), 400

    objet = modele.query.get(commande_id)
    if not objet:
        return jsonify({"erreur": "Commande introuvable"}), 404

    if hasattr(objet, "statut"):
        if type_commande == "commande":
            objet.statut = "confirmee_producteur"
            # Escrow : l'argent est payé mais reste bloqué tant que l'acheteur n'a pas confirmé la réception.
            objet.paiement_statut = "paye_bloque"
            objet.date_paiement = datetime.utcnow()
        elif type_commande == "commande_nourriture":
            objet.statut = "en_preparation"
        elif type_commande == "reservation_hotel":
            objet.statut = "payee"
    db.session.commit()

    return jsonify({"message": "Paiement confirmé et commande mise à jour"}), 200


@app.route("/api/commandes/<int:commande_id>/confirmer-reception", methods=["PUT"])
def confirmer_reception_commande(commande_id):
    """L'acheteur confirme avoir bien reçu son produit : le paiement bloqué (escrow) est alors
    libéré, ce qui signifie qu'il est officiellement dû au producteur (le vrai virement reste
    manuel tant que le paiement automatique vers les producteurs n'est pas actif)."""
    commande = Commande.query.get_or_404(commande_id)
    if commande.paiement_statut != "paye_bloque":
        return jsonify({"erreur": "Aucun paiement en attente de libération pour cette commande."}), 400

    commande.paiement_statut = "libere"
    commande.date_liberation_paiement = datetime.utcnow()
    commande.statut = "terminee"
    db.session.commit()

    if commande.produit and commande.produit.producteur:
        envoyer_notification_push(
            commande.produit.producteur.push_token, "Paiement libéré",
            f"L'acheteur a confirmé la réception de « {commande.produit.nom} ». "
            f"{commande.montant_producteur} FCFA te sont dus, versement à venir.",
        )

    return jsonify({"message": "Réception confirmée, paiement libéré", "commande": commande.to_dict()})


@app.route("/api/admin/paiements-bloques", methods=["GET"])
def admin_lister_paiements_bloques():
    """Liste des commandes payées mais dont l'argent reste bloqué (escrow), pour suivi admin."""
    if not cle_admin_valide(request):
        return jsonify({"erreur": "Accès non autorisé"}), 401
    commandes = Commande.query.filter_by(paiement_statut="paye_bloque").order_by(Commande.date_paiement.desc()).all()
    return jsonify([c.to_dict() for c in commandes])


@app.route("/api/commandes/<int:commande_id>/suivi-transporteur", methods=["PUT"])
def enregistrer_suivi_transporteur(commande_id):
    """Le producteur (ou l'admin) enregistre le numéro de suivi d'un transporteur externe
    (DHL, FedEx, La Poste...) pour une commande d'export international. AgriChange n'interroge
    pas leur API en direct (coûteux, réservé aux comptes professionnels) : le client reçoit
    juste le numéro et le nom du transporteur pour vérifier lui-même sur leur site."""
    commande = Commande.query.get_or_404(commande_id)
    data = request.get_json()
    if not data.get("transporteur_externe") or not data.get("numero_suivi_externe"):
        return jsonify({"erreur": "transporteur_externe et numero_suivi_externe requis"}), 400
    commande.transporteur_externe = data["transporteur_externe"]
    commande.numero_suivi_externe = data["numero_suivi_externe"]
    db.session.commit()
    if commande.acheteur:
        envoyer_notification_push(
            commande.acheteur.push_token, "Numéro de suivi disponible",
            f"Ta commande a été confiée à {data['transporteur_externe']}, numéro : {data['numero_suivi_externe']}.",
        )
    return jsonify({"message": "Numéro de suivi enregistré", "commande": commande.to_dict()})


# ---------- MISE EN AVANT DES ANNONCES (payant) ----------

DUREE_MISE_EN_AVANT_JOURS = {"7_jours": 7, "30_jours": 30}
PRIX_MISE_EN_AVANT = {"7_jours": 1000, "30_jours": 3000}  # FCFA, à ajuster selon ta politique de prix


@app.route("/api/produits/<int:produit_id>/mise-en-avant/initier", methods=["POST"])
def initier_mise_en_avant(produit_id):
    """Crée une facture PayDunya pour booster un produit (mise en avant payante)."""
    produit = Produit.query.get_or_404(produit_id)
    data = request.get_json()
    duree = data.get("duree", "7_jours")
    if duree not in DUREE_MISE_EN_AVANT_JOURS:
        return jsonify({"erreur": f"duree invalide. Options: {', '.join(DUREE_MISE_EN_AVANT_JOURS.keys())}"}), 400

    montant = PRIX_MISE_EN_AVANT[duree]
    payload = {
        "invoice": {"total_amount": montant, "description": f"AgriChange — Mise en avant produit #{produit_id} ({duree})"},
        "store": {"name": "AgriChange"},
        "actions": {
            "cancel_url": data.get("cancel_url", ""), "return_url": data.get("return_url", ""),
            "callback_url": f"{request.url_root.rstrip('/')}/api/paiement/paydunya/ipn-mise-en-avant",
        },
        "custom_data": {"produit_id": produit_id, "duree": duree},
    }
    reponse, statut = paydunya_appel_api("checkout-invoice/create", payload)
    if reponse.get("response_code") == "00":
        return jsonify({"message": "Facture créée", "url_paiement": reponse.get("response_text"), "token": reponse.get("token")}), 201
    return jsonify({"erreur": "Échec de la création de la facture PayDunya", "detail": reponse}), 400


@app.route("/api/paiement/paydunya/ipn-mise-en-avant", methods=["POST"])
def paydunya_ipn_mise_en_avant():
    """IPN dédié à la mise en avant de produit : active le boost après paiement confirmé."""
    donnees_recues = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    token = donnees_recues.get("data[token]") or donnees_recues.get("token")
    if not token:
        return jsonify({"erreur": "Token manquant"}), 400

    verification = paydunya_verifier_facture(token)
    if verification.get("status") != "completed":
        return jsonify({"message": "Paiement non confirmé, aucune action effectuée."}), 200

    custom_data = verification.get("custom_data", {})
    produit_id = custom_data.get("produit_id")
    duree = custom_data.get("duree", "7_jours")
    produit = Produit.query.get(produit_id)
    if not produit:
        return jsonify({"erreur": "Produit introuvable"}), 404

    jours = DUREE_MISE_EN_AVANT_JOURS.get(duree, 7)
    from datetime import timedelta
    base = produit.mise_en_avant_expire if (produit.mise_en_avant_expire and produit.mise_en_avant_expire > datetime.utcnow()) else datetime.utcnow()
    produit.mis_en_avant = True
    produit.mise_en_avant_expire = base + timedelta(days=jours)
    db.session.commit()

    return jsonify({"message": "Mise en avant activée"}), 200


# ---------- ABONNEMENT VENDEUR PREMIUM (payant) ----------

PRIX_ABONNEMENT_PREMIUM = 2000  # FCFA / mois, à ajuster selon ta politique de prix
TONTINE_COMMISSION_TAUX = 0.03  # 3% prélevés automatiquement sur chaque cotisation de tontine


@app.route("/api/producteurs/<int:producteur_id>/abonnement/initier", methods=["POST"])
def initier_abonnement_premium(producteur_id):
    """Crée une facture PayDunya pour un abonnement premium producteur (1 mois)."""
    Producteur.query.get_or_404(producteur_id)
    data = request.get_json() or {}
    payload = {
        "invoice": {"total_amount": PRIX_ABONNEMENT_PREMIUM, "description": f"AgriChange — Abonnement premium producteur #{producteur_id} (1 mois)"},
        "store": {"name": "AgriChange"},
        "actions": {
            "cancel_url": data.get("cancel_url", ""), "return_url": data.get("return_url", ""),
            "callback_url": f"{request.url_root.rstrip('/')}/api/paiement/paydunya/ipn-abonnement",
        },
        "custom_data": {"producteur_id": producteur_id},
    }
    reponse, statut = paydunya_appel_api("checkout-invoice/create", payload)
    if reponse.get("response_code") == "00":
        return jsonify({"message": "Facture créée", "url_paiement": reponse.get("response_text"), "token": reponse.get("token")}), 201
    return jsonify({"erreur": "Échec de la création de la facture PayDunya", "detail": reponse}), 400


@app.route("/api/paiement/paydunya/ipn-abonnement", methods=["POST"])
def paydunya_ipn_abonnement():
    """IPN dédié à l'abonnement premium : active/prolonge le premium après paiement confirmé."""
    donnees_recues = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    token = donnees_recues.get("data[token]") or donnees_recues.get("token")
    if not token:
        return jsonify({"erreur": "Token manquant"}), 400

    verification = paydunya_verifier_facture(token)
    if verification.get("status") != "completed":
        return jsonify({"message": "Paiement non confirmé, aucune action effectuée."}), 200

    custom_data = verification.get("custom_data", {})
    producteur_id = custom_data.get("producteur_id")
    producteur = Producteur.query.get(producteur_id)
    if not producteur:
        return jsonify({"erreur": "Producteur introuvable"}), 404

    from datetime import timedelta
    base = producteur.premium_expire if (producteur.premium_expire and producteur.premium_expire > datetime.utcnow()) else datetime.utcnow()
    producteur.premium = True
    producteur.premium_expire = base + timedelta(days=30)
    db.session.commit()

    return jsonify({"message": "Abonnement premium activé"}), 200


@app.route("/api/producteurs/<int:producteur_id>/offres-troc", methods=["POST"])
def creer_offre_troc(producteur_id):
    Producteur.query.get_or_404(producteur_id)
    data = request.get_json()
    champs_requis = ["produit_propose", "quantite_proposee", "produit_recherche"]
    manquants = [c for c in champs_requis if not data.get(c)]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400

    offre = OffreTroc(
        producteur_id=producteur_id, produit_propose=data["produit_propose"],
        quantite_proposee=data["quantite_proposee"], unite=data.get("unite", "kg"),
        produit_recherche=data["produit_recherche"], description=data.get("description", ""),
    )
    db.session.add(offre)
    db.session.commit()
    return jsonify({"message": "Offre de troc publiée", "offre": offre.to_dict()}), 201


@app.route("/api/offres-troc", methods=["GET"])
def lister_offres_troc():
    query = OffreTroc.query.filter_by(statut="ouverte")
    if request.args.get("pays"):
        query = query.join(Producteur).filter(Producteur.pays == request.args["pays"])
    offres = query.order_by(OffreTroc.date_creation.desc()).all()
    return jsonify([o.to_dict() for o in offres])


@app.route("/api/offres-troc/<int:offre_id>", methods=["GET"])
def detail_offre_troc(offre_id):
    offre = OffreTroc.query.get_or_404(offre_id)
    data = offre.to_dict()
    data["propositions"] = [p.to_dict() for p in offre.propositions]
    return jsonify(data)


@app.route("/api/offres-troc/<int:offre_id>/proposer", methods=["POST"])
def proposer_troc(offre_id):
    offre = OffreTroc.query.get_or_404(offre_id)
    if offre.statut != "ouverte":
        return jsonify({"erreur": "Cette offre n'est plus ouverte."}), 400
    data = request.get_json()
    champs_requis = ["producteur_id", "produit_offert_en_retour", "quantite"]
    manquants = [c for c in champs_requis if data.get(c) is None]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400

    proposition = PropositionTroc(
        offre_troc_id=offre_id, producteur_id=data["producteur_id"],
        produit_offert_en_retour=data["produit_offert_en_retour"], quantite=data["quantite"],
        unite=data.get("unite", "kg"), message=data.get("message", ""),
    )
    db.session.add(proposition)
    db.session.commit()
    return jsonify({"message": "Proposition envoyée", "proposition": proposition.to_dict()}), 201


@app.route("/api/propositions-troc/<int:proposition_id>/accepter", methods=["PUT"])
def accepter_proposition_troc(proposition_id):
    proposition = PropositionTroc.query.get_or_404(proposition_id)
    proposition.statut = "acceptee"
    proposition.offre.statut = "conclue"
    db.session.commit()
    return jsonify({"message": "Échange conclu ! Mettez-vous en contact pour organiser la remise.", "proposition": proposition.to_dict()})


@app.route("/api/propositions-troc/<int:proposition_id>/refuser", methods=["PUT"])
def refuser_proposition_troc(proposition_id):
    proposition = PropositionTroc.query.get_or_404(proposition_id)
    proposition.statut = "refusee"
    db.session.commit()
    return jsonify({"message": "Proposition refusée", "proposition": proposition.to_dict()})


# ---------- Jours de marché (calendrier communautaire) ----------

@app.route("/api/jours-marche", methods=["POST"])
def ajouter_jour_marche():
    data = request.get_json()
    champs_requis = ["ville", "pays", "jour_semaine"]
    manquants = [c for c in champs_requis if data.get(c) is None]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400
    if not (0 <= int(data["jour_semaine"]) <= 6):
        return jsonify({"erreur": "jour_semaine doit être entre 0 (lundi) et 6 (dimanche)"}), 400

    jour = JourMarche(
        ville=data["ville"], pays=data["pays"], jour_semaine=int(data["jour_semaine"]),
        nom_marche=data.get("nom_marche", ""), description=data.get("description", ""),
        ajoute_par_producteur_id=data.get("producteur_id"),
    )
    db.session.add(jour)
    db.session.commit()
    return jsonify({"message": "Jour de marché ajouté", "jour_marche": jour.to_dict()}), 201


@app.route("/api/jours-marche", methods=["GET"])
def lister_jours_marche():
    query = JourMarche.query
    if request.args.get("pays"):
        query = query.filter_by(pays=request.args["pays"])
    if request.args.get("ville"):
        query = query.filter(JourMarche.ville.ilike(f"%{request.args['ville']}%"))
    jours = query.order_by(JourMarche.jour_semaine).all()
    return jsonify([j.to_dict() for j in jours])


@app.route("/api/jours-marche/aujourdhui", methods=["GET"])
def jours_marche_aujourdhui():
    jour_semaine_auj = datetime.utcnow().weekday()  # 0 = lundi
    query = JourMarche.query.filter_by(jour_semaine=jour_semaine_auj)
    if request.args.get("pays"):
        query = query.filter_by(pays=request.args["pays"])
    jours = query.all()
    return jsonify([j.to_dict() for j in jours])


# ---------- Tontine digitale (épargne tournante) ----------

@app.route("/api/producteurs/<int:producteur_id>/tontines", methods=["POST"])
def creer_tontine(producteur_id):
    Producteur.query.get_or_404(producteur_id)
    data = request.get_json()
    champs_requis = ["nom", "pays", "ville", "montant_cotisation", "nombre_membres_max"]
    manquants = [c for c in champs_requis if data.get(c) is None]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400
    if not data.get("numero_mobile_money"):
        return jsonify({"erreur": "Indique le numéro Mobile Money sur lequel tu recevras le pot commun le jour de ton tour."}), 400
    if not data.get("nom_complet_mobile_money"):
        return jsonify({"erreur": "Indique le nom complet enregistré sur ce compte Mobile Money."}), 400

    tontine = Tontine(
        nom=data["nom"], createur_id=producteur_id, pays=data["pays"], ville=data["ville"],
        montant_cotisation=data["montant_cotisation"], frequence=data.get("frequence", "mensuelle"),
        nombre_membres_max=data["nombre_membres_max"],
    )
    db.session.add(tontine)
    db.session.flush()

    # le créateur rejoint automatiquement en premier
    premier_membre = MembreTontine(
        tontine_id=tontine.id, producteur_id=producteur_id, ordre_tour=1,
        operateur_mobile_money=data.get("operateur_mobile_money", ""), numero_mobile_money=data["numero_mobile_money"],
        nom_complet_mobile_money=data["nom_complet_mobile_money"],
    )
    db.session.add(premier_membre)
    db.session.commit()
    return jsonify({"message": "Tontine créée", "tontine": tontine.to_dict()}), 201


@app.route("/api/tontines", methods=["GET"])
def lister_tontines():
    query = Tontine.query
    if request.args.get("pays"):
        query = query.filter_by(pays=request.args["pays"])
    if request.args.get("statut"):
        query = query.filter_by(statut=request.args["statut"])
    tontines = query.order_by(Tontine.date_creation.desc()).all()
    return jsonify([t.to_dict() for t in tontines])


@app.route("/api/tontines/<int:tontine_id>", methods=["GET"])
def detail_tontine(tontine_id):
    tontine = Tontine.query.get_or_404(tontine_id)
    data = tontine.to_dict()
    data["membres"] = [m.to_dict() for m in tontine.membres]
    data["cotisations_cycle_actuel"] = [c.to_dict() for c in tontine.cotisations if c.cycle_numero == tontine.cycle_actuel]
    return jsonify(data)


@app.route("/api/tontines/<int:tontine_id>/rejoindre", methods=["POST"])
def rejoindre_tontine(tontine_id):
    tontine = Tontine.query.get_or_404(tontine_id)
    if tontine.statut != "ouverte":
        return jsonify({"erreur": "Cette tontine n'accepte plus de nouveaux membres."}), 400
    if len(tontine.membres) >= tontine.nombre_membres_max:
        return jsonify({"erreur": "Cette tontine est déjà complète."}), 400
    data = request.get_json()
    producteur_id = data.get("producteur_id")
    if not producteur_id:
        return jsonify({"erreur": "producteur_id requis"}), 400
    if not data.get("numero_mobile_money"):
        return jsonify({"erreur": "Indique le numéro Mobile Money sur lequel tu recevras le pot commun le jour de ton tour."}), 400
    if not data.get("nom_complet_mobile_money"):
        return jsonify({"erreur": "Indique le nom complet enregistré sur ce compte Mobile Money."}), 400
    if any(m.producteur_id == producteur_id for m in tontine.membres):
        return jsonify({"erreur": "Tu es déjà membre de cette tontine."}), 409

    ordre = len(tontine.membres) + 1
    membre = MembreTontine(
        tontine_id=tontine_id, producteur_id=producteur_id, ordre_tour=ordre,
        operateur_mobile_money=data.get("operateur_mobile_money", ""), numero_mobile_money=data["numero_mobile_money"],
        nom_complet_mobile_money=data["nom_complet_mobile_money"],
    )
    db.session.add(membre)
    if ordre == tontine.nombre_membres_max:
        tontine.statut = "en_cours"
    db.session.commit()
    return jsonify({"message": f"Tu as rejoint la tontine, ton tour arrivera au cycle {ordre}.", "membre": membre.to_dict(), "tontine": tontine.to_dict()}), 201


@app.route("/api/tontines/<int:tontine_id>/cotiser", methods=["POST"])
def declarer_cotisation_tontine(tontine_id):
    """Crée une facture PayDunya pour que le membre paie sa cotisation en ligne.
    Dès que le paiement est confirmé (IPN), la cotisation est validée automatiquement —
    aucune intervention d'un admin n'est nécessaire."""
    tontine = Tontine.query.get_or_404(tontine_id)
    data = request.get_json()
    membre_id = data.get("membre_id")
    if not membre_id:
        return jsonify({"erreur": "membre_id requis"}), 400
    membre = MembreTontine.query.get_or_404(membre_id)

    montant = data.get("montant", tontine.montant_cotisation)
    cotisation = CotisationTontine(
        tontine_id=tontine_id, membre_id=membre_id, cycle_numero=tontine.cycle_actuel,
        montant=montant, statut="en_attente",
    )
    db.session.add(cotisation)
    db.session.commit()

    payload = {
        "invoice": {"total_amount": int(montant), "description": f"AgriChange — Cotisation tontine « {tontine.nom} » (cycle {tontine.cycle_actuel})"},
        "store": {"name": "AgriChange"},
        "actions": {
            "cancel_url": data.get("cancel_url", ""), "return_url": data.get("return_url", ""),
            "callback_url": f"{request.url_root.rstrip('/')}/api/paiement/paydunya/ipn-cotisation-tontine",
        },
        "custom_data": {"cotisation_id": cotisation.id},
    }
    reponse, statut = paydunya_appel_api("checkout-invoice/create", payload)
    if reponse.get("response_code") == "00":
        return jsonify({
            "message": "Facture créée, en attente de paiement", "cotisation": cotisation.to_dict(),
            "url_paiement": reponse.get("response_text"), "token": reponse.get("token"),
        }), 201
    return jsonify({"erreur": "Échec de la création de la facture PayDunya", "detail": reponse}), 400


@app.route("/api/paiement/paydunya/ipn-cotisation-tontine", methods=["POST"])
def paydunya_ipn_cotisation_tontine():
    """IPN dédié aux cotisations de tontine : valide automatiquement la cotisation dès
    que le paiement est confirmé, et prélève la commission AgriChange sur le montant."""
    donnees_recues = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    token = donnees_recues.get("data[token]") or donnees_recues.get("token")
    if not token:
        return jsonify({"erreur": "Token manquant"}), 400

    verification = paydunya_verifier_facture(token)
    if verification.get("status") != "completed":
        return jsonify({"message": "Paiement non confirmé, aucune action effectuée."}), 200

    custom_data = verification.get("custom_data", {})
    cotisation = CotisationTontine.query.get(custom_data.get("cotisation_id"))
    if not cotisation:
        return jsonify({"erreur": "Cotisation introuvable"}), 404

    cotisation.commission_montant = round(cotisation.montant * TONTINE_COMMISSION_TAUX, 2)
    cotisation.montant_net = round(cotisation.montant - cotisation.commission_montant, 2)
    cotisation.statut = "validee"
    cotisation.date_validation = datetime.utcnow()
    db.session.commit()

    if cotisation.membre and cotisation.membre.tontine and cotisation.membre.tontine.createur:
        envoyer_notification_push(
            cotisation.membre.tontine.createur.push_token, "Cotisation reçue",
            f"{cotisation.membre.producteur.nom if cotisation.membre.producteur else 'Un membre'} a payé sa cotisation pour « {cotisation.membre.tontine.nom} ».",
        )

    return jsonify({"message": "Cotisation validée automatiquement"}), 200


@app.route("/api/tontines/<int:tontine_id>/cycle-suivant", methods=["POST"])
def passer_cycle_suivant_tontine(tontine_id):
    """Une fois que toutes les cotisations du cycle sont validées et le pot versé au bénéficiaire,
    on passe au cycle suivant (le tour passe au membre suivant dans la rotation)."""
    tontine = Tontine.query.get_or_404(tontine_id)
    tontine.cycle_actuel += 1
    if tontine.cycle_actuel > len(tontine.membres):
        tontine.statut = "terminee"
    db.session.commit()
    return jsonify({"message": "Cycle suivant démarré", "tontine": tontine.to_dict()})


@app.route("/api/courses-taxi", methods=["POST"])
@app.route("/api/taxi/multiplicateur-demande", methods=["GET"])
def multiplicateur_demande_taxi():
    """Calcule un multiplicateur de prix selon l'offre/demande en direct (comme InDrive/Uber) :
    plus il y a de courses en attente par rapport aux chauffeurs disponibles, plus le prix monte."""
    vehicule = request.args.get("vehicule", "peu_importe")
    nombre_chauffeurs = Livreur.query.filter_by(en_service=True, actif=True).count()
    query_attente = CourseTaxi.query.filter_by(statut="en_attente")
    nombre_demandes = query_attente.count()

    if nombre_chauffeurs == 0:
        multiplicateur = 1.3  # aucun chauffeur en service : prix légèrement majoré pour inciter à commander quand même
    else:
        ratio = nombre_demandes / nombre_chauffeurs
        if ratio >= 2:
            multiplicateur = 1.6
        elif ratio >= 1:
            multiplicateur = 1.3
        elif ratio >= 0.5:
            multiplicateur = 1.0
        else:
            multiplicateur = 0.9  # peu de demande : petit prix réduit pour encourager les commandes

    return jsonify({
        "multiplicateur": multiplicateur,
        "nombre_chauffeurs_disponibles": nombre_chauffeurs,
        "nombre_demandes_en_attente": nombre_demandes,
        "forte_demande": multiplicateur > 1.2,
    })


@app.route("/api/messages/<int:message_id>", methods=["DELETE"])
def supprimer_message(message_id):
    """Supprime un message envoyé (par erreur, ou pour toute autre raison)."""
    message = Message.query.get_or_404(message_id)
    db.session.delete(message)
    db.session.commit()
    return jsonify({"message": "Message supprimé"})


def creer_course_taxi():
    data = request.get_json()
    champs_requis = ["client_nom", "client_telephone", "latitude_depart", "longitude_depart", "adresse_arrivee"]
    manquants = [c for c in champs_requis if data.get(c) is None]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400

    course = CourseTaxi(
        client_nom=data["client_nom"], client_telephone=data["client_telephone"],
        latitude_depart=data["latitude_depart"], longitude_depart=data["longitude_depart"],
        adresse_depart=data.get("adresse_depart", ""),
        latitude_arrivee=data.get("latitude_arrivee"), longitude_arrivee=data.get("longitude_arrivee"),
        adresse_arrivee=data["adresse_arrivee"], prix_propose=data.get("prix_propose"),
        vehicule_souhaite=data.get("vehicule_souhaite", "peu_importe"),
    )
    db.session.add(course)
    db.session.commit()
    return jsonify({"message": "Course demandée, en attente d'un chauffeur", "course": course.to_dict()}), 201


@app.route("/api/courses-taxi-disponibles", methods=["GET"])
def lister_courses_taxi_disponibles():
    livreur_id = request.args.get("livreur_id", type=int)
    query = CourseTaxi.query.filter_by(statut="en_attente")
    courses = query.order_by(CourseTaxi.date_creation.desc()).all()

    if livreur_id:
        livreur = Livreur.query.get(livreur_id)
        vehicule_livreur = (livreur.vehicule or "").strip().lower() if livreur else ""
        courses = [
            c for c in courses
            if c.vehicule_souhaite == "peu_importe"
            or not vehicule_livreur
            or c.vehicule_souhaite.lower() in vehicule_livreur
            or vehicule_livreur in c.vehicule_souhaite.lower()
        ]

    return jsonify([c.to_dict() for c in courses])


@app.route("/api/courses-taxi/<int:course_id>", methods=["GET"])
def detail_course_taxi(course_id):
    course = CourseTaxi.query.get_or_404(course_id)
    return jsonify(course.to_dict())


@app.route("/api/courses-taxi/<int:course_id>/accepter", methods=["PUT"])
def accepter_course_taxi(course_id):
    course = CourseTaxi.query.get_or_404(course_id)
    if course.statut != "en_attente":
        return jsonify({"erreur": "Cette course n'est plus disponible."}), 400
    data = request.get_json()
    if not data.get("livreur_id"):
        return jsonify({"erreur": "livreur_id requis"}), 400
    course.livreur_id = data["livreur_id"]
    course.statut = "acceptee"
    if data.get("prix_contre_propose") is not None:
        course.prix_contre_propose = data["prix_contre_propose"]
    db.session.commit()
    return jsonify({"message": "Course acceptée", "course": course.to_dict()})


@app.route("/api/courses-taxi/<int:course_id>/position", methods=["PUT"])
def mettre_a_jour_position_course_taxi(course_id):
    """Le chauffeur envoie sa position en direct pendant la course, pour que le client le suive sur la carte."""
    course = CourseTaxi.query.get_or_404(course_id)
    data = request.get_json()
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    if latitude is None or longitude is None:
        return jsonify({"erreur": "latitude et longitude requis"}), 400
    course.latitude_livreur = latitude
    course.longitude_livreur = longitude
    course.position_livreur_maj = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "Position mise à jour"})


@app.route("/api/courses-taxi/<int:course_id>/statut", methods=["PUT"])
def changer_statut_course_taxi(course_id):
    course = CourseTaxi.query.get_or_404(course_id)
    data = request.get_json() or {}
    if data.get("statut") not in ["en_attente", "acceptee", "en_cours", "terminee", "annulee"]:
        return jsonify({"erreur": "Statut invalide"}), 400
    course.statut = data["statut"]
    db.session.commit()
    return jsonify({"message": "Statut mis à jour", "course": course.to_dict()})


@app.route("/api/livreurs/<int:livreur_id>/courses-taxi", methods=["GET"])
def lister_courses_taxi_livreur(livreur_id):
    Livreur.query.get_or_404(livreur_id)
    courses = CourseTaxi.query.filter_by(livreur_id=livreur_id).order_by(CourseTaxi.date_creation.desc()).all()
    return jsonify([c.to_dict() for c in courses])


@app.route("/api/offres-emploi", methods=["POST"])
def creer_offre_emploi():
    data = request.get_json()
    champs_requis = ["entreprise_nom", "titre_poste", "description_poste", "pays", "ville", "telephone_contact"]
    manquants = [c for c in champs_requis if not data.get(c)]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400

    offre = OffreEmploi(
        entreprise_nom=data["entreprise_nom"], titre_poste=data["titre_poste"],
        description_poste=data["description_poste"], type_contrat=data.get("type_contrat", "CDI"),
        salaire_propose=data.get("salaire_propose", ""), pays=data["pays"], ville=data["ville"],
        telephone_contact=data["telephone_contact"],
    )
    db.session.add(offre)
    db.session.commit()
    return jsonify({"message": "Offre d'emploi publiée", "offre": offre.to_dict()}), 201


@app.route("/api/offres-emploi", methods=["GET"])
def lister_offres_emploi():
    query = OffreEmploi.query.filter_by(statut="ouverte")
    if request.args.get("pays"):
        query = query.filter_by(pays=request.args["pays"])
    if request.args.get("ville"):
        query = query.filter(OffreEmploi.ville.ilike(f"%{request.args['ville']}%"))
    offres = query.order_by(OffreEmploi.date_publication.desc()).all()
    return jsonify([o.to_dict() for o in offres])


@app.route("/api/offres-emploi/<int:offre_id>", methods=["GET"])
def detail_offre_emploi(offre_id):
    offre = OffreEmploi.query.get_or_404(offre_id)
    data = offre.to_dict()
    data["candidatures"] = [c.to_dict() for c in offre.candidatures]
    return jsonify(data)


@app.route("/api/offres-emploi/<int:offre_id>/candidater", methods=["POST"])
def candidater_offre_emploi(offre_id):
    OffreEmploi.query.get_or_404(offre_id)
    data = request.get_json()
    champs_requis = ["nom", "telephone"]
    manquants = [c for c in champs_requis if not data.get(c)]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400

    candidature = Candidature(offre_emploi_id=offre_id, nom=data["nom"], telephone=data["telephone"], message=data.get("message", ""))
    db.session.add(candidature)
    db.session.commit()
    return jsonify({"message": "Candidature envoyée", "candidature": candidature.to_dict()}), 201


@app.route("/api/offres-emploi/<int:offre_id>/statut", methods=["PUT"])
def changer_statut_offre_emploi(offre_id):
    offre = OffreEmploi.query.get_or_404(offre_id)
    data = request.get_json() or {}
    if data.get("statut") not in ["ouverte", "fermee"]:
        return jsonify({"erreur": "Statut invalide"}), 400
    offre.statut = data["statut"]
    db.session.commit()
    return jsonify({"message": "Statut mis à jour", "offre": offre.to_dict()})


# ---------- Opportunités d'investissement (mise en relation uniquement, aucune transaction) ----------

@app.route("/api/opportunites-investissement", methods=["POST"])
def creer_opportunite_investissement():
    data = request.get_json()
    champs_requis = ["nom_projet", "entreprise_porteuse", "description", "pays", "ville", "contact_nom", "contact_telephone"]
    manquants = [c for c in champs_requis if not data.get(c)]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400

    opportunite = OpportuniteInvestissement(
        nom_projet=data["nom_projet"], entreprise_porteuse=data["entreprise_porteuse"],
        description=data["description"], secteur=data.get("secteur", ""),
        montant_recherche=data.get("montant_recherche", ""), pays=data["pays"], ville=data["ville"],
        contact_nom=data["contact_nom"], contact_telephone=data["contact_telephone"],
    )
    db.session.add(opportunite)
    db.session.commit()
    return jsonify({"message": "Opportunité publiée", "opportunite": opportunite.to_dict()}), 201


@app.route("/api/opportunites-investissement", methods=["GET"])
def lister_opportunites_investissement():
    query = OpportuniteInvestissement.query.filter_by(statut="ouverte")
    if request.args.get("pays"):
        query = query.filter_by(pays=request.args["pays"])
    opportunites = query.order_by(OpportuniteInvestissement.date_publication.desc()).all()
    return jsonify([o.to_dict() for o in opportunites])


@app.route("/api/opportunites-investissement/<int:opportunite_id>", methods=["GET"])
def detail_opportunite_investissement(opportunite_id):
    opportunite = OpportuniteInvestissement.query.get_or_404(opportunite_id)
    return jsonify(opportunite.to_dict())


@app.route("/api/commerces/inscription", methods=["POST"])
def inscrire_commerce():
    """Inscription universelle : accepte n'importe quel type d'activité, même hors des catégories connues.
    Vérification d'identité (pièce + GPS) obligatoire, plusieurs photos publicitaires possibles."""
    data = request.get_json()
    champs_requis = ["nom", "description_activite", "pays", "ville", "telephone"]
    manquants = [c for c in champs_requis if not data.get(c)]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400
    if not data.get("numero_piece_identite") or not data.get("piece_identite_recto") or not data.get("piece_identite_verso"):
        return jsonify({"erreur": "Pièce d'identité (numéro + recto + verso) obligatoire."}), 400
    if data.get("latitude") is None or data.get("longitude") is None:
        return jsonify({"erreur": "Position GPS requise."}), 400

    photos = data.get("photos", [])
    if not isinstance(photos, list):
        photos = []

    commerce = Commerce(
        nom=data["nom"], categorie=data.get("categorie", "autre"),
        description_activite=data["description_activite"],
        pays=data["pays"], ville=data["ville"], telephone=data["telephone"],
        photos=json.dumps(photos[:6]),
        mot_de_passe_hash=generate_password_hash(data["mot_de_passe"]) if data.get("mot_de_passe") else None,
        latitude=data["latitude"], longitude=data["longitude"],
        type_piece_identite=data.get("type_piece_identite", "CNI"),
        numero_piece_identite=data["numero_piece_identite"],
        piece_identite_recto=data["piece_identite_recto"],
        piece_identite_verso=data["piece_identite_verso"],
    )
    db.session.add(commerce)
    db.session.commit()
    return jsonify({"message": "Commerce inscrit, en attente de vérification", "commerce": commerce.to_dict()}), 201


@app.route("/api/commerces", methods=["GET"])
def lister_commerces():
    """Recherche dans l'annuaire, par catégorie, pays, ville, ou mot-clé dans la description."""
    query = Commerce.query.filter_by(actif=True)
    if request.args.get("categorie"):
        query = query.filter_by(categorie=request.args["categorie"])
    if request.args.get("pays"):
        query = query.filter_by(pays=request.args["pays"])
    if request.args.get("ville"):
        query = query.filter(Commerce.ville.ilike(f"%{request.args['ville']}%"))
    if request.args.get("q"):
        mot = f"%{request.args['q']}%"
        query = query.filter(db.or_(Commerce.nom.ilike(mot), Commerce.description_activite.ilike(mot)))
    commerces = query.order_by(Commerce.date_inscription.desc()).all()
    return jsonify([c.to_dict() for c in commerces])


@app.route("/api/commerces/<int:commerce_id>", methods=["GET"])
def detail_commerce(commerce_id):
    commerce = Commerce.query.get_or_404(commerce_id)
    return jsonify(commerce.to_dict())


@app.route("/api/hotels/inscription", methods=["POST"])
def inscrire_hotel():
    """Inscription d'un hôtel. Vérification d'identité (pièce + GPS) obligatoire,
    plusieurs photos publicitaires possibles."""
    data = request.get_json()
    champs_requis = ["nom", "pays", "ville", "telephone", "mot_de_passe"]
    manquants = [c for c in champs_requis if not data.get(c)]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400
    if not data.get("numero_piece_identite") or not data.get("piece_identite_recto") or not data.get("piece_identite_verso"):
        return jsonify({"erreur": "Pièce d'identité (numéro + recto + verso) obligatoire."}), 400
    if data.get("latitude") is None or data.get("longitude") is None:
        return jsonify({"erreur": "Position GPS requise."}), 400
    if Hotel.query.filter_by(telephone=data["telephone"]).first():
        return jsonify({"erreur": "Un hôtel est déjà inscrit avec ce numéro."}), 409

    photos = data.get("photos", [])
    if not isinstance(photos, list):
        photos = []

    hotel = Hotel(
        nom=data["nom"], description=data.get("description", ""),
        pays=data["pays"], ville=data["ville"], adresse=data.get("adresse", ""),
        telephone=data["telephone"], email=data.get("email", ""),
        photos=json.dumps(photos[:6]),
        mot_de_passe_hash=generate_password_hash(data["mot_de_passe"]),
        latitude=data["latitude"], longitude=data["longitude"],
        type_piece_identite=data.get("type_piece_identite", "CNI"),
        numero_piece_identite=data["numero_piece_identite"],
        piece_identite_recto=data["piece_identite_recto"],
        piece_identite_verso=data["piece_identite_verso"],
    )
    db.session.add(hotel)
    db.session.commit()
    return jsonify({"message": "Hôtel inscrit, en attente de vérification", "hotel": hotel.to_dict()}), 201


@app.route("/api/hotels/connexion", methods=["POST"])
def connexion_hotel():
    data = request.get_json()
    hotel = Hotel.query.filter_by(telephone=data.get("telephone")).first()
    if not hotel or not check_password_hash(hotel.mot_de_passe_hash, data.get("mot_de_passe", "")):
        return jsonify({"erreur": "Téléphone ou mot de passe incorrect"}), 401
    return jsonify({"message": "Connexion réussie", "hotel": hotel.to_dict()})


@app.route("/api/hotels", methods=["GET"])
def lister_hotels():
    """Recherche d'hôtels, par pays et/ou ville (le client peut être n'importe où dans le monde)."""
    query = Hotel.query.filter_by(actif=True)
    if request.args.get("pays"):
        query = query.filter_by(pays=request.args["pays"])
    if request.args.get("ville"):
        query = query.filter(Hotel.ville.ilike(f"%{request.args['ville']}%"))
    hotels = query.order_by(Hotel.nom).all()
    return jsonify([h.to_dict() for h in hotels])


@app.route("/api/hotels/<int:hotel_id>", methods=["GET"])
def detail_hotel(hotel_id):
    hotel = Hotel.query.get_or_404(hotel_id)
    data = hotel.to_dict()
    data["chambres"] = [c.to_dict() for c in ChambreHotel.query.filter_by(hotel_id=hotel_id, disponible=True).all()]
    return jsonify(data)


@app.route("/api/hotels/<int:hotel_id>/chambres", methods=["POST"])
def ajouter_chambre(hotel_id):
    Hotel.query.get_or_404(hotel_id)
    data = request.get_json()
    champs_requis = ["nom", "prix_nuit"]
    manquants = [c for c in champs_requis if data.get(c) is None]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400

    chambre = ChambreHotel(
        hotel_id=hotel_id, nom=data["nom"], description=data.get("description", ""),
        prix_nuit=data["prix_nuit"], capacite=data.get("capacite", 2), photo=data.get("photo", ""),
    )
    db.session.add(chambre)
    db.session.commit()
    return jsonify({"message": "Chambre ajoutée", "chambre": chambre.to_dict()}), 201


@app.route("/api/chambres/<int:chambre_id>", methods=["PUT"])
def modifier_chambre(chambre_id):
    chambre = ChambreHotel.query.get_or_404(chambre_id)
    data = request.get_json() or {}
    for champ in ["nom", "description", "prix_nuit", "capacite", "photo", "disponible"]:
        if champ in data:
            setattr(chambre, champ, data[champ])
    db.session.commit()
    return jsonify({"message": "Chambre mise à jour", "chambre": chambre.to_dict()})


@app.route("/api/reservations-hotel", methods=["POST"])
def creer_reservation_hotel():
    data = request.get_json()
    champs_requis = ["hotel_id", "chambre_id", "client_nom", "client_telephone", "date_arrivee", "date_depart"]
    manquants = [c for c in champs_requis if not data.get(c)]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400

    chambre = ChambreHotel.query.get_or_404(data["chambre_id"])
    try:
        date_arrivee = datetime.strptime(data["date_arrivee"], "%Y-%m-%d").date()
        date_depart = datetime.strptime(data["date_depart"], "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"erreur": "Format de date invalide (attendu AAAA-MM-JJ)"}), 400

    nombre_nuits = (date_depart - date_arrivee).days
    if nombre_nuits <= 0:
        return jsonify({"erreur": "La date de départ doit être après la date d'arrivée."}), 400

    reservation = ReservationHotel(
        hotel_id=data["hotel_id"], chambre_id=data["chambre_id"],
        client_nom=data["client_nom"], client_telephone=data["client_telephone"],
        client_pays=data.get("client_pays", ""),
        date_arrivee=date_arrivee, date_depart=date_depart, nombre_nuits=nombre_nuits,
        nombre_personnes=data.get("nombre_personnes", 1),
        montant_total=chambre.prix_nuit * nombre_nuits,
        message=data.get("message", ""),
    )
    db.session.add(reservation)
    db.session.commit()
    return jsonify({"message": "Réservation créée, en attente de confirmation de l'hôtel", "reservation": reservation.to_dict()}), 201


@app.route("/api/hotels/<int:hotel_id>/reservations", methods=["GET"])
def lister_reservations_hotel(hotel_id):
    Hotel.query.get_or_404(hotel_id)
    reservations = ReservationHotel.query.filter_by(hotel_id=hotel_id).order_by(ReservationHotel.date_creation.desc()).all()
    return jsonify([r.to_dict() for r in reservations])


@app.route("/api/reservations-hotel/<int:reservation_id>/statut", methods=["PUT"])
def changer_statut_reservation(reservation_id):
    reservation = ReservationHotel.query.get_or_404(reservation_id)
    data = request.get_json() or {}
    nouveau_statut = data.get("statut")
    if nouveau_statut not in ["initiee", "payee", "confirmee", "annulee"]:
        return jsonify({"erreur": "Statut invalide"}), 400
    reservation.statut = nouveau_statut
    db.session.commit()
    return jsonify({"message": "Statut mis à jour", "reservation": reservation.to_dict()})


@app.route("/api/restaurants/inscription", methods=["POST"])
def inscrire_restaurant():
    """Inscription d'un restaurant/cuisinière. Vérification d'identité (pièce + GPS) obligatoire,
    plusieurs photos publicitaires possibles."""
    data = request.get_json()
    champs_requis = ["nom", "pays", "ville", "telephone", "mot_de_passe"]
    manquants = [c for c in champs_requis if not data.get(c)]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400
    if not data.get("numero_piece_identite") or not data.get("piece_identite_recto") or not data.get("piece_identite_verso"):
        return jsonify({"erreur": "Pièce d'identité (numéro + recto + verso) obligatoire."}), 400
    if data.get("latitude") is None or data.get("longitude") is None:
        return jsonify({"erreur": "Position GPS requise."}), 400
    if Restaurant.query.filter_by(telephone=data["telephone"]).first():
        return jsonify({"erreur": "Un établissement est déjà inscrit avec ce numéro."}), 409

    photos = data.get("photos", [])
    if not isinstance(photos, list):
        photos = []

    restaurant = Restaurant(
        nom=data["nom"], type_etablissement=data.get("type_etablissement", "restaurant"),
        description=data.get("description", ""), pays=data["pays"], ville=data["ville"],
        quartier=data.get("quartier", ""), telephone=data["telephone"],
        photos=json.dumps(photos[:6]),
        mot_de_passe_hash=generate_password_hash(data["mot_de_passe"]),
        latitude=data["latitude"], longitude=data["longitude"],
        type_piece_identite=data.get("type_piece_identite", "CNI"),
        numero_piece_identite=data["numero_piece_identite"],
        piece_identite_recto=data["piece_identite_recto"],
        piece_identite_verso=data["piece_identite_verso"],
    )
    db.session.add(restaurant)
    db.session.commit()
    return jsonify({"message": "Établissement inscrit, en attente de vérification", "restaurant": restaurant.to_dict()}), 201


@app.route("/api/restaurants/connexion", methods=["POST"])
def connexion_restaurant():
    data = request.get_json()
    restaurant = Restaurant.query.filter_by(telephone=data.get("telephone")).first()
    if not restaurant or not check_password_hash(restaurant.mot_de_passe_hash, data.get("mot_de_passe", "")):
        return jsonify({"erreur": "Téléphone ou mot de passe incorrect"}), 401
    return jsonify({"message": "Connexion réussie", "restaurant": restaurant.to_dict()})


@app.route("/api/restaurants", methods=["GET"])
def lister_restaurants():
    query = Restaurant.query.filter_by(actif=True)
    if request.args.get("pays"):
        query = query.filter_by(pays=request.args["pays"])
    if request.args.get("ville"):
        query = query.filter(Restaurant.ville.ilike(f"%{request.args['ville']}%"))
    restaurants = query.order_by(Restaurant.nom).all()
    return jsonify([r.to_dict() for r in restaurants])


@app.route("/api/restaurants/<int:restaurant_id>", methods=["GET"])
def detail_restaurant(restaurant_id):
    restaurant = Restaurant.query.get_or_404(restaurant_id)
    data = restaurant.to_dict()
    data["plats"] = [p.to_dict() for p in PlatMenu.query.filter_by(restaurant_id=restaurant_id, disponible=True).all()]
    return jsonify(data)


@app.route("/api/restaurants/<int:restaurant_id>/plats", methods=["POST"])
def ajouter_plat(restaurant_id):
    Restaurant.query.get_or_404(restaurant_id)
    data = request.get_json()
    champs_requis = ["nom", "prix"]
    manquants = [c for c in champs_requis if data.get(c) is None]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400

    plat = PlatMenu(
        restaurant_id=restaurant_id, nom=data["nom"], description=data.get("description", ""),
        prix=data["prix"], photo=data.get("photo", ""),
    )
    db.session.add(plat)
    db.session.commit()
    return jsonify({"message": "Plat ajouté", "plat": plat.to_dict()}), 201


@app.route("/api/plats/<int:plat_id>", methods=["PUT"])
def modifier_plat(plat_id):
    plat = PlatMenu.query.get_or_404(plat_id)
    data = request.get_json() or {}
    for champ in ["nom", "description", "prix", "photo", "disponible"]:
        if champ in data:
            setattr(plat, champ, data[champ])
    db.session.commit()
    return jsonify({"message": "Plat mis à jour", "plat": plat.to_dict()})


@app.route("/api/commandes-nourriture", methods=["POST"])
def creer_commande_nourriture():
    data = request.get_json()
    champs_requis = ["restaurant_id", "client_nom", "client_telephone", "adresse_livraison", "items"]
    manquants = [c for c in champs_requis if not data.get(c)]
    if manquants:
        return jsonify({"erreur": f"Champs manquants: {', '.join(manquants)}"}), 400
    if not isinstance(data["items"], list) or len(data["items"]) == 0:
        return jsonify({"erreur": "La commande doit contenir au moins un plat."}), 400

    montant_total = sum(item.get("prix", 0) * item.get("quantite", 1) for item in data["items"])

    commande = CommandeNourriture(
        restaurant_id=data["restaurant_id"],
        client_nom=data["client_nom"], client_telephone=data["client_telephone"],
        adresse_livraison=data["adresse_livraison"],
        latitude_livraison=data.get("latitude_livraison"), longitude_livraison=data.get("longitude_livraison"),
        items=json.dumps(data["items"]), montant_total=montant_total,
        message=data.get("message", ""),
    )
    db.session.add(commande)
    db.session.commit()
    return jsonify({"message": "Commande envoyée au restaurant", "commande": commande.to_dict()}), 201


@app.route("/api/restaurants/<int:restaurant_id>/commandes", methods=["GET"])
def lister_commandes_restaurant(restaurant_id):
    Restaurant.query.get_or_404(restaurant_id)
    commandes = CommandeNourriture.query.filter_by(restaurant_id=restaurant_id).order_by(CommandeNourriture.date_creation.desc()).all()
    return jsonify([c.to_dict() for c in commandes])


@app.route("/api/commandes-nourriture/<int:commande_id>/statut", methods=["PUT"])
def changer_statut_commande_nourriture(commande_id):
    commande = CommandeNourriture.query.get_or_404(commande_id)
    data = request.get_json() or {}
    nouveau_statut = data.get("statut")
    if nouveau_statut not in ["initiee", "en_preparation", "en_livraison", "livree", "annulee"]:
        return jsonify({"erreur": "Statut invalide"}), 400
    commande.statut = nouveau_statut
    if data.get("livreur_id"):
        commande.livreur_id = data["livreur_id"]
    db.session.commit()
    return jsonify({"message": "Statut mis à jour", "commande": commande.to_dict()})


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    port = int(os.environ.get("PORT", 5050))
    app.run(debug=True, host="0.0.0.0", port=port, use_reloader=False)
