from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()


class Producteur(db.Model):
    """Compte vendeur / producteur agro-pastoral."""
    __tablename__ = "producteurs"

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(120), nullable=False)
    telephone = db.Column(db.String(20), unique=True, nullable=False)
    mot_de_passe_hash = db.Column(db.String(255), nullable=False)

    pays = db.Column(db.String(50), nullable=False, default="Côte d'Ivoire")
    ville = db.Column(db.String(100), nullable=False)
    zone_livraison = db.Column(db.String(255))

    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

    type_production = db.Column(db.String(50))
    description = db.Column(db.Text)

    photo_url = db.Column(db.String(255))
    histoire = db.Column(db.Text)

    piece_identite_recto = db.Column(db.String(255))
    piece_identite_verso = db.Column(db.String(255))

    verifie = db.Column(db.Boolean, default=False)

    code_parrainage = db.Column(db.String(10), unique=True)
    code_parrain_utilise = db.Column(db.String(10))
    nombre_filleuls = db.Column(db.Integer, default=0)

    push_token = db.Column(db.String(255))

    premium = db.Column(db.Boolean, default=False)
    credits_outils = db.Column(db.Integer, default=10)

    actif = db.Column(db.Boolean, default=True)
    date_inscription = db.Column(db.DateTime, default=datetime.utcnow)

    produits = db.relationship("Produit", backref="producteur", lazy=True)
    avis = db.relationship("Avis", backref="producteur", lazy=True)

    def to_dict(self):
        notes = [a.note for a in self.avis]
        note_moyenne = round(sum(notes) / len(notes), 1) if notes else None

        toutes_commandes = [c for p in self.produits for c in p.commandes]
        total_commandes = len(toutes_commandes)
        commandes_reussies = len([c for c in toutes_commandes if c.statut in ("livree", "terminee")])
        taux_livraison = round(commandes_reussies / total_commandes * 100) if total_commandes > 0 else None

        anciennete_jours = (datetime.utcnow() - self.date_inscription).days
        composantes = []
        if taux_livraison is not None:
            composantes.append(taux_livraison)
        if note_moyenne is not None:
            composantes.append(min(100, note_moyenne * 20))
        composantes.append(min(100, anciennete_jours / 3))
        score_confiance = round(sum(composantes) / len(composantes)) if composantes else None

        return {
            "id": self.id,
            "nom": self.nom,
            "telephone": self.telephone,
            "pays": self.pays,
            "ville": self.ville,
            "zone_livraison": self.zone_livraison,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "type_production": self.type_production,
            "description": self.description,
            "photo_url": self.photo_url,
            "histoire": self.histoire,
            "piece_identite_recto": self.piece_identite_recto,
            "piece_identite_verso": self.piece_identite_verso,
            "verifie": self.verifie,
            "code_parrainage": self.code_parrainage,
            "nombre_filleuls": self.nombre_filleuls,
            "premium": self.premium,
            "credits_outils": self.credits_outils,
            "actif": self.actif,
            "date_inscription": self.date_inscription.isoformat(),
            "nombre_produits": len(self.produits),
            "note_moyenne": note_moyenne,
            "nombre_avis": len(notes),
            "score_confiance": score_confiance,
            "taux_livraison": taux_livraison,
        }


class Produit(db.Model):
    """Produit mis en vente par un producteur."""
    __tablename__ = "produits"

    id = db.Column(db.Integer, primary_key=True)
    producteur_id = db.Column(db.Integer, db.ForeignKey("producteurs.id"), nullable=False)

    nom = db.Column(db.String(150), nullable=False)
    categorie = db.Column(db.String(50), nullable=False)
    prix_unitaire = db.Column(db.Float, nullable=False)
    unite = db.Column(db.String(20), default="unité")
    quantite_disponible = db.Column(db.Float, nullable=False, default=0)
    photo_url = db.Column(db.String(255))
    photos_urls = db.Column(db.Text)
    video_url = db.Column(db.String(500))
    description = db.Column(db.Text)

    disponible_export = db.Column(db.Boolean, default=False)  # signalé par le producteur pour l'export international

    actif = db.Column(db.Boolean, default=True)
    date_ajout = db.Column(db.DateTime, default=datetime.utcnow)

    historique_prix = db.relationship("HistoriquePrix", backref="produit", lazy=True)

    def to_dict(self):
        import json
        try:
            photos = json.loads(self.photos_urls) if self.photos_urls else []
        except (ValueError, TypeError):
            photos = []
        notes = [a.note for a in self.producteur.avis] if self.producteur else []
        note_moyenne = round(sum(notes) / len(notes), 1) if notes else None
        return {
            "id": self.id,
            "producteur_id": self.producteur_id,
            "producteur_nom": self.producteur.nom if self.producteur else None,
            "producteur_ville": self.producteur.ville if self.producteur else None,
            "producteur_pays": self.producteur.pays if self.producteur else None,
            "producteur_photo_url": self.producteur.photo_url if self.producteur else None,
            "producteur_histoire": self.producteur.histoire if self.producteur else None,
            "producteur_verifie": self.producteur.verifie if self.producteur else False,
            "producteur_score_confiance": self.producteur.to_dict()["score_confiance"] if self.producteur else None,
            "producteur_note_moyenne": note_moyenne,
            "producteur_nombre_avis": len(notes),
            "producteur_latitude": self.producteur.latitude if self.producteur else None,
            "producteur_longitude": self.producteur.longitude if self.producteur else None,
            "nom": self.nom,
            "categorie": self.categorie,
            "prix_unitaire": self.prix_unitaire,
            "unite": self.unite,
            "quantite_disponible": self.quantite_disponible,
            "photo_url": self.photo_url,
            "photos_urls": photos,
            "video_url": self.video_url,
            "description": self.description,
            "disponible_export": self.disponible_export,
            "actif": self.actif,
        }


class HistoriquePrix(db.Model):
    """Trace l'évolution du prix d'un produit dans le temps."""
    __tablename__ = "historique_prix"

    id = db.Column(db.Integer, primary_key=True)
    produit_id = db.Column(db.Integer, db.ForeignKey("produits.id"), nullable=False)
    prix = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"prix": self.prix, "date": self.date.isoformat()}


class RecolteFuture(db.Model):
    """Annonce d'une récolte pas encore disponible, que les acheteurs peuvent réserver à l'avance."""
    __tablename__ = "recoltes_futures"

    id = db.Column(db.Integer, primary_key=True)
    producteur_id = db.Column(db.Integer, db.ForeignKey("producteurs.id"), nullable=False)

    nom = db.Column(db.String(150), nullable=False)
    categorie = db.Column(db.String(50), nullable=False)
    quantite_estimee = db.Column(db.Float, nullable=False)
    unite = db.Column(db.String(20), default="sac")
    prix_unitaire_prevu = db.Column(db.Float, nullable=False)
    date_recolte_prevue = db.Column(db.Date)
    description = db.Column(db.Text)

    statut = db.Column(db.String(20), default="ouvert")  # ouvert / clos
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

    producteur = db.relationship("Producteur")
    reservations = db.relationship("ReservationRecolte", backref="recolte", lazy=True)

    def to_dict(self):
        quantite_reservee = sum(r.quantite for r in self.reservations)
        return {
            "id": self.id,
            "producteur_id": self.producteur_id,
            "producteur_nom": self.producteur.nom if self.producteur else None,
            "producteur_ville": self.producteur.ville if self.producteur else None,
            "producteur_pays": self.producteur.pays if self.producteur else None,
            "producteur_verifie": self.producteur.verifie if self.producteur else False,
            "nom": self.nom,
            "categorie": self.categorie,
            "quantite_estimee": self.quantite_estimee,
            "quantite_reservee": quantite_reservee,
            "unite": self.unite,
            "prix_unitaire_prevu": self.prix_unitaire_prevu,
            "date_recolte_prevue": self.date_recolte_prevue.isoformat() if self.date_recolte_prevue else None,
            "description": self.description,
            "statut": self.statut,
            "nombre_reservations": len(self.reservations),
            "date_creation": self.date_creation.isoformat(),
        }


class ReservationRecolte(db.Model):
    """Réservation d'une quantité sur une récolte future, par un acheteur."""
    __tablename__ = "reservations_recolte"

    id = db.Column(db.Integer, primary_key=True)
    recolte_id = db.Column(db.Integer, db.ForeignKey("recoltes_futures.id"), nullable=False)
    acheteur_id = db.Column(db.Integer, db.ForeignKey("acheteurs.id"), nullable=False)
    quantite = db.Column(db.Float, nullable=False)
    date_reservation = db.Column(db.DateTime, default=datetime.utcnow)

    acheteur = db.relationship("Acheteur")

    def to_dict(self):
        return {
            "id": self.id,
            "acheteur_id": self.acheteur_id,
            "acheteur_nom": self.acheteur.nom if self.acheteur else None,
            "quantite": self.quantite,
            "date_reservation": self.date_reservation.isoformat(),
        }


class AchatGroupe(db.Model):
    """Campagne d'achat groupé : prix réduit débloqué une fois la quantité cible atteinte."""
    __tablename__ = "achats_groupes"

    id = db.Column(db.Integer, primary_key=True)
    produit_id = db.Column(db.Integer, db.ForeignKey("produits.id"), nullable=False)

    prix_unitaire_groupe = db.Column(db.Float, nullable=False)
    quantite_cible = db.Column(db.Float, nullable=False)
    quantite_actuelle = db.Column(db.Float, default=0)

    statut = db.Column(db.String(20), default="ouvert")
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

    produit = db.relationship("Produit")
    participations = db.relationship("ParticipationGroupe", backref="achat_groupe", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "produit_id": self.produit_id,
            "produit_nom": self.produit.nom if self.produit else None,
            "producteur_nom": self.produit.producteur.nom if self.produit and self.produit.producteur else None,
            "prix_unitaire_normal": self.produit.prix_unitaire if self.produit else None,
            "prix_unitaire_groupe": self.prix_unitaire_groupe,
            "quantite_cible": self.quantite_cible,
            "quantite_actuelle": self.quantite_actuelle,
            "nombre_participants": len(self.participations),
            "statut": self.statut,
            "date_creation": self.date_creation.isoformat(),
        }


class ParticipationGroupe(db.Model):
    """Engagement d'un acheteur dans un achat groupé."""
    __tablename__ = "participations_groupe"

    id = db.Column(db.Integer, primary_key=True)
    achat_groupe_id = db.Column(db.Integer, db.ForeignKey("achats_groupes.id"), nullable=False)
    acheteur_id = db.Column(db.Integer, db.ForeignKey("acheteurs.id"), nullable=False)
    quantite = db.Column(db.Float, nullable=False)
    date_participation = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "acheteur_id": self.acheteur_id,
            "acheteur_nom": self.acheteur.nom if self.acheteur else None,
            "quantite": self.quantite,
            "date_participation": self.date_participation.isoformat(),
        }


class BesoinFinancement(db.Model):
    """Besoin de financement publié par un producteur (pré-financement diaspora)."""
    __tablename__ = "besoins_financement"

    id = db.Column(db.Integer, primary_key=True)
    producteur_id = db.Column(db.Integer, db.ForeignKey("producteurs.id"), nullable=False)

    titre = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    montant_cible = db.Column(db.Float, nullable=False)
    montant_leve = db.Column(db.Float, default=0)

    statut = db.Column(db.String(20), default="ouvert")
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

    producteur = db.relationship("Producteur")
    promesses = db.relationship("PromesseFinancement", backref="besoin", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "producteur_id": self.producteur_id,
            "producteur_nom": self.producteur.nom if self.producteur else None,
            "producteur_ville": self.producteur.ville if self.producteur else None,
            "producteur_verifie": self.producteur.verifie if self.producteur else False,
            "titre": self.titre,
            "description": self.description,
            "montant_cible": self.montant_cible,
            "montant_leve": self.montant_leve,
            "nombre_soutiens": len(self.promesses),
            "statut": self.statut,
            "date_creation": self.date_creation.isoformat(),
        }


class PromesseFinancement(db.Model):
    """Engagement de soutien financier (promesse, pas un vrai transfert d'argent tant que le paiement réel n'est pas actif)."""
    __tablename__ = "promesses_financement"

    id = db.Column(db.Integer, primary_key=True)
    besoin_id = db.Column(db.Integer, db.ForeignKey("besoins_financement.id"), nullable=False)
    acheteur_id = db.Column(db.Integer, db.ForeignKey("acheteurs.id"), nullable=False)
    montant = db.Column(db.Float, nullable=False)
    date_promesse = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "acheteur_id": self.acheteur_id,
            "acheteur_nom": self.acheteur.nom if self.acheteur else None,
            "montant": self.montant,
            "date_promesse": self.date_promesse.isoformat(),
        }


class NotairePartenaire(db.Model):
    """Notaire proposé par l'administration pour sécuriser les transactions de terrains."""
    __tablename__ = "notaires_partenaires"

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(150), nullable=False)
    ville = db.Column(db.String(100))
    pays = db.Column(db.String(50))
    contact = db.Column(db.String(50))
    actif = db.Column(db.Boolean, default=True)
    date_ajout = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "nom": self.nom, "ville": self.ville, "pays": self.pays,
            "contact": self.contact, "actif": self.actif,
        }


class Terrain(db.Model):
    """Annonce de terrain vérifié. Mise en relation uniquement : le paiement se fait
    obligatoirement chez un notaire partenaire vérifié, jamais dans l'application."""
    __tablename__ = "terrains"

    id = db.Column(db.Integer, primary_key=True)
    producteur_id = db.Column(db.Integer, db.ForeignKey("producteurs.id"), nullable=False)

    titre = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    superficie = db.Column(db.Float)
    unite_superficie = db.Column(db.String(20), default="m²")
    prix_total = db.Column(db.Float, nullable=False)

    ville = db.Column(db.String(100))
    pays = db.Column(db.String(50))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

    photos_urls = db.Column(db.Text)

    notaire_nom = db.Column(db.String(150))
    notaire_contact = db.Column(db.String(50))
    notaire_propose_acheteur_nom = db.Column(db.String(150))
    notaire_propose_acheteur_contact = db.Column(db.String(50))

    verifie_admin = db.Column(db.Boolean, default=False)
    actif = db.Column(db.Boolean, default=True)
    date_ajout = db.Column(db.DateTime, default=datetime.utcnow)

    producteur = db.relationship("Producteur")

    def to_dict(self):
        import json
        try:
            photos = json.loads(self.photos_urls) if self.photos_urls else []
        except (ValueError, TypeError):
            photos = []
        return {
            "id": self.id,
            "producteur_id": self.producteur_id,
            "producteur_nom": self.producteur.nom if self.producteur else None,
            "titre": self.titre,
            "description": self.description,
            "superficie": self.superficie,
            "unite_superficie": self.unite_superficie,
            "prix_total": self.prix_total,
            "ville": self.ville,
            "pays": self.pays,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "photos_urls": photos,
            "notaire_nom": self.notaire_nom,
            "notaire_contact": self.notaire_contact,
            "notaire_propose_acheteur_nom": self.notaire_propose_acheteur_nom,
            "notaire_propose_acheteur_contact": self.notaire_propose_acheteur_contact,
            "verifie_admin": self.verifie_admin,
            "actif": self.actif,
            "date_ajout": self.date_ajout.isoformat(),
        }


class CodePremium(db.Model):
    """Code à usage unique permettant de débloquer le premium sans passer par le paiement en ligne."""
    __tablename__ = "codes_premium"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    utilise = db.Column(db.Boolean, default=False)
    producteur_id = db.Column(db.Integer, db.ForeignKey("producteurs.id"))
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)
    date_utilisation = db.Column(db.DateTime)

    producteur = db.relationship("Producteur")

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "utilise": self.utilise,
            "producteur_nom": self.producteur.nom if self.producteur else None,
            "date_creation": self.date_creation.isoformat(),
            "date_utilisation": self.date_utilisation.isoformat() if self.date_utilisation else None,
        }


class Acheteur(db.Model):
    """Compte acheteur/client."""
    __tablename__ = "acheteurs"

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(120), nullable=False)
    telephone = db.Column(db.String(20), unique=True, nullable=False)
    mot_de_passe_hash = db.Column(db.String(255), nullable=False)

    pays = db.Column(db.String(50), nullable=False)
    ville = db.Column(db.String(100), nullable=False)
    adresse_livraison = db.Column(db.String(255))

    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

    push_token = db.Column(db.String(255))

    date_inscription = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "nom": self.nom,
            "telephone": self.telephone,
            "pays": self.pays,
            "ville": self.ville,
            "adresse_livraison": self.adresse_livraison,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }


class Livreur(db.Model):
    """Compte transporteur / coursier."""
    __tablename__ = "livreurs"

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(120), nullable=False)
    telephone = db.Column(db.String(20), unique=True, nullable=False)
    mot_de_passe_hash = db.Column(db.String(255), nullable=False)

    pays = db.Column(db.String(50), nullable=False, default="Côte d'Ivoire")
    ville = db.Column(db.String(100), nullable=False)
    vehicule = db.Column(db.String(50))
    marque_vehicule = db.Column(db.String(50))
    plaque_immatriculation = db.Column(db.String(30))
    couleur_vehicule = db.Column(db.String(30))

    piece_identite_recto = db.Column(db.String(255))
    piece_identite_verso = db.Column(db.String(255))

    en_service = db.Column(db.Boolean, default=False)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    position_maj = db.Column(db.DateTime)

    push_token = db.Column(db.String(255))

    actif = db.Column(db.Boolean, default=True)
    date_inscription = db.Column(db.DateTime, default=datetime.utcnow)

    livraisons = db.relationship("Commande", backref="livreur", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "nom": self.nom,
            "telephone": self.telephone,
            "pays": self.pays,
            "ville": self.ville,
            "vehicule": self.vehicule,
            "marque_vehicule": self.marque_vehicule,
            "plaque_immatriculation": self.plaque_immatriculation,
            "couleur_vehicule": self.couleur_vehicule,
            "piece_identite_recto": self.piece_identite_recto,
            "piece_identite_verso": self.piece_identite_verso,
            "en_service": self.en_service,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "position_maj": self.position_maj.isoformat() if self.position_maj else None,
            "actif": self.actif,
            "date_inscription": self.date_inscription.isoformat(),
            "nombre_livraisons": len([c for c in self.livraisons if c.statut in ("livree", "terminee")]),
        }


class Message(db.Model):
    """Message échangé entre un acheteur et un producteur au sujet d'un produit."""
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    acheteur_id = db.Column(db.Integer, db.ForeignKey("acheteurs.id"), nullable=False)
    producteur_id = db.Column(db.Integer, db.ForeignKey("producteurs.id"), nullable=False)
    produit_id = db.Column(db.Integer, db.ForeignKey("produits.id"))

    expediteur_type = db.Column(db.String(20), nullable=False)
    contenu_original = db.Column(db.Text, nullable=False)
    contenu_filtre = db.Column(db.Text, nullable=False)
    contient_infraction = db.Column(db.Boolean, default=False)

    date_envoi = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "acheteur_id": self.acheteur_id,
            "producteur_id": self.producteur_id,
            "produit_id": self.produit_id,
            "expediteur_type": self.expediteur_type,
            "contenu": self.contenu_filtre,
            "contient_infraction": self.contient_infraction,
            "date_envoi": self.date_envoi.isoformat(),
        }


class Avis(db.Model):
    """Avis et note laissés par un acheteur sur un producteur."""
    __tablename__ = "avis"

    id = db.Column(db.Integer, primary_key=True)
    producteur_id = db.Column(db.Integer, db.ForeignKey("producteurs.id"), nullable=False)
    acheteur_id = db.Column(db.Integer, db.ForeignKey("acheteurs.id"), nullable=False)

    note = db.Column(db.Integer, nullable=False)
    commentaire = db.Column(db.Text)

    date_avis = db.Column(db.DateTime, default=datetime.utcnow)

    acheteur = db.relationship("Acheteur", backref="avis_donnes")

    def to_dict(self):
        return {
            "id": self.id,
            "producteur_id": self.producteur_id,
            "acheteur_id": self.acheteur_id,
            "acheteur_nom": self.acheteur.nom if self.acheteur else "Anonyme",
            "note": self.note,
            "commentaire": self.commentaire,
            "date_avis": self.date_avis.isoformat(),
        }


class Favori(db.Model):
    """Produit ajouté aux favoris par un acheteur."""
    __tablename__ = "favoris"

    id = db.Column(db.Integer, primary_key=True)
    acheteur_id = db.Column(db.Integer, db.ForeignKey("acheteurs.id"), nullable=False)
    produit_id = db.Column(db.Integer, db.ForeignKey("produits.id"), nullable=False)

    date_ajout = db.Column(db.DateTime, default=datetime.utcnow)

    produit = db.relationship("Produit")

    __table_args__ = (
        db.UniqueConstraint("acheteur_id", "produit_id", name="uq_favori_acheteur_produit"),
    )


class Beneficiaire(db.Model):
    """Personne inscrite uniquement pour recevoir des transferts d'argent libres (diaspora -> Afrique),
    sans forcément être producteur, acheteur ou livreur sur AgriChange."""
    __tablename__ = "beneficiaires"

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(120), nullable=False)
    telephone = db.Column(db.String(20), unique=True, nullable=False)
    mot_de_passe_hash = db.Column(db.String(255), nullable=False)

    pays = db.Column(db.String(50), nullable=False)
    ville = db.Column(db.String(100))

    operateur_mobile_money = db.Column(db.String(30))  # Orange Money, MTN Money, Wave, Moov Money, Autre
    numero_mobile_money = db.Column(db.String(30))

    push_token = db.Column(db.String(255))
    actif = db.Column(db.Boolean, default=True)
    date_inscription = db.Column(db.DateTime, default=datetime.utcnow)

    transferts_recus = db.relationship("TransfertArgent", backref="destinataire", lazy=True)
    numeros_mobile_money = db.relationship("NumeroMobileMoney", backref="beneficiaire", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "nom": self.nom,
            "telephone": self.telephone,
            "pays": self.pays,
            "ville": self.ville,
            "operateur_mobile_money": self.operateur_mobile_money,
            "numero_mobile_money": self.numero_mobile_money,
            "numeros_mobile_money": [n.to_dict() for n in self.numeros_mobile_money],
            "date_inscription": self.date_inscription.isoformat(),
        }


class NumeroMobileMoney(db.Model):
    """Numéro Mobile Money supplémentaire d'un bénéficiaire (il peut en avoir plusieurs, sur des réseaux différents)."""
    __tablename__ = "numeros_mobile_money"

    id = db.Column(db.Integer, primary_key=True)
    beneficiaire_id = db.Column(db.Integer, db.ForeignKey("beneficiaires.id"), nullable=False)
    operateur = db.Column(db.String(30), nullable=False)  # Orange Money, MTN Money, Wave, Moov Money, Autre
    numero = db.Column(db.String(30), nullable=False)

    def to_dict(self):
        return {"id": self.id, "operateur": self.operateur, "numero": self.numero}


class TransfertArgent(db.Model):
    """Transfert d'argent libre (diaspora -> Afrique), sans lien avec un achat de produit.
    Le montant est enregistré ; le versement réel se fait dès l'activation du paiement en ligne."""
    __tablename__ = "transferts_argent"

    id = db.Column(db.Integer, primary_key=True)
    destinataire_id = db.Column(db.Integer, db.ForeignKey("beneficiaires.id"), nullable=False)

    expediteur_nom = db.Column(db.String(120), nullable=False)
    expediteur_telephone = db.Column(db.String(30))
    expediteur_pays = db.Column(db.String(50))

    montant = db.Column(db.Float, nullable=False)
    message = db.Column(db.Text)

    # Agent marchand ayant réalisé ce transfert pour le compte de l'expéditeur (optionnel)
    agent_id = db.Column(db.Integer, db.ForeignKey("agents_marchand.id"), nullable=True)
    origine = db.Column(db.String(20), default="client_en_ligne")  # client_en_ligne / agent_kiosque
    frais_service = db.Column(db.Float, default=0.0)      # frais total facturé en plus du montant net
    commission_agent = db.Column(db.Float, default=0.0)   # part des frais qui revient à l'agent

    statut = db.Column(db.String(20), default="initie")  # initie / verse / annule
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)
    date_versement = db.Column(db.DateTime)
    date_annulation = db.Column(db.DateTime)
    motif_annulation = db.Column(db.String(255))

    agent = db.relationship("AgentMarchand", backref="transferts_realises")

    def to_dict(self):
        return {
            "id": self.id,
            "destinataire_id": self.destinataire_id,
            "destinataire_nom": self.destinataire.nom if self.destinataire else None,
            "destinataire_numero": self.destinataire.numero_mobile_money if self.destinataire else None,
            "destinataire_operateur": self.destinataire.operateur_mobile_money if self.destinataire else None,
            "expediteur_nom": self.expediteur_nom,
            "expediteur_telephone": self.expediteur_telephone,
            "expediteur_pays": self.expediteur_pays,
            "montant": self.montant,
            "message": self.message,
            "agent_id": self.agent_id,
            "agent_nom": self.agent.nom if self.agent else None,
            "origine": self.origine,
            "frais_service": self.frais_service,
            "commission_agent": self.commission_agent,
            "statut": self.statut,
            "date_creation": self.date_creation.isoformat(),
            "date_versement": self.date_versement.isoformat() if self.date_versement else None,
            "date_annulation": self.date_annulation.isoformat() if self.date_annulation else None,
            "motif_annulation": self.motif_annulation,
        }


class AgentMarchand(db.Model):
    """Agent indépendant (comme un point Orange Money) qui réalise des transferts d'argent
    pour le compte de clients via AgriChange, en échange d'une commission versée sur son solde."""
    __tablename__ = "agents_marchand"

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(120), nullable=False)
    telephone = db.Column(db.String(20), unique=True, nullable=False)
    mot_de_passe_hash = db.Column(db.String(255), nullable=False)
    code_agent = db.Column(db.String(12), unique=True, nullable=False)  # code que le client communique à l'agent

    pays = db.Column(db.String(50), nullable=False)
    ville = db.Column(db.String(100))

    operateur_mobile_money = db.Column(db.String(30))  # pour recevoir ses gains
    numero_mobile_money = db.Column(db.String(30))

    # Vérification d'identité obligatoire (il manipule l'argent de tiers, comme producteurs/livreurs)
    piece_identite_recto = db.Column(db.String(255))
    piece_identite_verso = db.Column(db.String(255))
    identite_verifiee = db.Column(db.Boolean, default=False)

    # Solde de trésorerie de l'agent : c'est CE solde qui est débité quand l'agent envoie
    # de l'argent pour le compte d'un client (modèle kiosque, client paie cash à l'agent).
    # L'agent le recharge lui-même par dépôt bancaire / mobile money, validé par l'admin.
    solde_disponible = db.Column(db.Float, default=0.0)

    solde_commission = db.Column(db.Float, default=0.0)  # gains en attente de retrait
    total_commission_gagnee = db.Column(db.Float, default=0.0)  # cumul historique (indicatif)

    actif = db.Column(db.Boolean, default=True)
    date_inscription = db.Column(db.DateTime, default=datetime.utcnow)

    retraits = db.relationship("RetraitAgent", backref="agent", lazy=True)
    recharges = db.relationship("RechargeAgent", backref="agent", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "nom": self.nom,
            "telephone": self.telephone,
            "code_agent": self.code_agent,
            "pays": self.pays,
            "ville": self.ville,
            "operateur_mobile_money": self.operateur_mobile_money,
            "numero_mobile_money": self.numero_mobile_money,
            "identite_verifiee": self.identite_verifiee,
            "solde_disponible": self.solde_disponible,
            "solde_commission": self.solde_commission,
            "total_commission_gagnee": self.total_commission_gagnee,
            "nombre_transferts": len(self.transferts_realises),
            "date_inscription": self.date_inscription.isoformat(),
        }


class RechargeAgent(db.Model):
    """Demande de recharge du solde de trésorerie d'un agent (dépôt bancaire ou mobile money
    que l'agent effectue lui-même vers AgriChange, validé ensuite par l'admin)."""
    __tablename__ = "recharges_agent"

    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey("agents_marchand.id"), nullable=False)
    montant = db.Column(db.Float, nullable=False)
    methode = db.Column(db.String(30))  # depot_bancaire / mobile_money / autre
    reference = db.Column(db.String(120))  # référence du dépôt/virement pour vérification
    statut = db.Column(db.String(20), default="demande")  # demande / validee / rejetee
    date_demande = db.Column(db.DateTime, default=datetime.utcnow)
    date_validation = db.Column(db.DateTime)

    def to_dict(self):
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "montant": self.montant,
            "methode": self.methode,
            "reference": self.reference,
            "statut": self.statut,
            "date_demande": self.date_demande.isoformat(),
            "date_validation": self.date_validation.isoformat() if self.date_validation else None,
        }


class RetraitAgent(db.Model):
    """Demande de retrait du solde de commission accumulé par un agent marchand."""
    __tablename__ = "retraits_agent"

    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey("agents_marchand.id"), nullable=False)
    montant = db.Column(db.Float, nullable=False)
    statut = db.Column(db.String(20), default="demande")  # demande / verse
    date_demande = db.Column(db.DateTime, default=datetime.utcnow)
    date_versement = db.Column(db.DateTime)

    def to_dict(self):
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "montant": self.montant,
            "statut": self.statut,
            "date_demande": self.date_demande.isoformat(),
            "date_versement": self.date_versement.isoformat() if self.date_versement else None,
        }


class Hotel(db.Model):
    """Établissement hôtelier partenaire, consultable et réservable depuis AgriChange
    (utile notamment pour la diaspora qui veut réserver un hôtel en Afrique, ou l'inverse)."""
    __tablename__ = "hotels"

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    pays = db.Column(db.String(50), nullable=False)
    ville = db.Column(db.String(100), nullable=False)
    adresse = db.Column(db.String(255))
    telephone = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(120))
    photo = db.Column(db.String(255))
    mot_de_passe_hash = db.Column(db.String(255), nullable=False)
    actif = db.Column(db.Boolean, default=True)
    date_inscription = db.Column(db.DateTime, default=datetime.utcnow)

    chambres = db.relationship("ChambreHotel", backref="hotel", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id, "nom": self.nom, "description": self.description,
            "pays": self.pays, "ville": self.ville, "adresse": self.adresse,
            "telephone": self.telephone, "email": self.email, "photo": self.photo,
            "nombre_chambres": len(self.chambres),
            "date_inscription": self.date_inscription.isoformat(),
        }


class ChambreHotel(db.Model):
    """Type de chambre proposé par un hôtel (ex: Standard, Suite...)."""
    __tablename__ = "chambres_hotel"

    id = db.Column(db.Integer, primary_key=True)
    hotel_id = db.Column(db.Integer, db.ForeignKey("hotels.id"), nullable=False)
    nom = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    prix_nuit = db.Column(db.Float, nullable=False)
    capacite = db.Column(db.Integer, default=2)
    photo = db.Column(db.String(255))
    disponible = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {
            "id": self.id, "hotel_id": self.hotel_id, "nom": self.nom,
            "description": self.description, "prix_nuit": self.prix_nuit,
            "capacite": self.capacite, "photo": self.photo, "disponible": self.disponible,
        }


class ReservationHotel(db.Model):
    """Réservation d'une chambre par un client (client local ou diaspora réservant à distance)."""
    __tablename__ = "reservations_hotel"

    id = db.Column(db.Integer, primary_key=True)
    hotel_id = db.Column(db.Integer, db.ForeignKey("hotels.id"), nullable=False)
    chambre_id = db.Column(db.Integer, db.ForeignKey("chambres_hotel.id"), nullable=False)

    client_nom = db.Column(db.String(120), nullable=False)
    client_telephone = db.Column(db.String(30), nullable=False)
    client_pays = db.Column(db.String(50))  # pays depuis lequel le client réserve (ex: France pour la diaspora)

    date_arrivee = db.Column(db.Date, nullable=False)
    date_depart = db.Column(db.Date, nullable=False)
    nombre_nuits = db.Column(db.Integer, nullable=False)
    nombre_personnes = db.Column(db.Integer, default=1)
    montant_total = db.Column(db.Float, nullable=False)
    message = db.Column(db.Text)

    statut = db.Column(db.String(20), default="initiee")  # initiee / payee / confirmee / annulee
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

    hotel = db.relationship("Hotel", backref="reservations")
    chambre = db.relationship("ChambreHotel", backref="reservations")

    def to_dict(self):
        return {
            "id": self.id, "hotel_id": self.hotel_id, "hotel_nom": self.hotel.nom if self.hotel else None,
            "chambre_id": self.chambre_id, "chambre_nom": self.chambre.nom if self.chambre else None,
            "client_nom": self.client_nom, "client_telephone": self.client_telephone, "client_pays": self.client_pays,
            "date_arrivee": self.date_arrivee.isoformat(), "date_depart": self.date_depart.isoformat(),
            "nombre_nuits": self.nombre_nuits, "nombre_personnes": self.nombre_personnes,
            "montant_total": self.montant_total, "message": self.message,
            "statut": self.statut, "date_creation": self.date_creation.isoformat(),
        }


class Restaurant(db.Model):
    """Restaurant, mini-restaurant ou cuisinière/vendeuse de nourriture inscrite sur AgriChange,
    pour permettre aux clients (ex: employés de bureau) de commander un repas livré."""
    __tablename__ = "restaurants"

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(150), nullable=False)
    type_etablissement = db.Column(db.String(30), default="restaurant")  # restaurant / cuisiniere / mini_restaurant
    description = db.Column(db.Text)
    pays = db.Column(db.String(50), nullable=False)
    ville = db.Column(db.String(100), nullable=False)
    quartier = db.Column(db.String(100))
    telephone = db.Column(db.String(30), nullable=False)
    photo = db.Column(db.String(255))
    mot_de_passe_hash = db.Column(db.String(255), nullable=False)
    actif = db.Column(db.Boolean, default=True)
    date_inscription = db.Column(db.DateTime, default=datetime.utcnow)

    plats = db.relationship("PlatMenu", backref="restaurant", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id, "nom": self.nom, "type_etablissement": self.type_etablissement,
            "description": self.description, "pays": self.pays, "ville": self.ville, "quartier": self.quartier,
            "telephone": self.telephone, "photo": self.photo,
            "nombre_plats": len(self.plats),
            "date_inscription": self.date_inscription.isoformat(),
        }


class PlatMenu(db.Model):
    """Plat proposé au menu d'un restaurant/cuisinière."""
    __tablename__ = "plats_menu"

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurants.id"), nullable=False)
    nom = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    prix = db.Column(db.Float, nullable=False)
    photo = db.Column(db.String(255))
    disponible = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {
            "id": self.id, "restaurant_id": self.restaurant_id, "nom": self.nom,
            "description": self.description, "prix": self.prix, "photo": self.photo, "disponible": self.disponible,
        }


class CommandeNourriture(db.Model):
    """Commande de repas passée à un restaurant/cuisinière, à livrer (ex: sur le lieu de travail du client)."""
    __tablename__ = "commandes_nourriture"

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurants.id"), nullable=False)
    livreur_id = db.Column(db.Integer, db.ForeignKey("livreurs.id"))

    client_nom = db.Column(db.String(120), nullable=False)
    client_telephone = db.Column(db.String(30), nullable=False)
    adresse_livraison = db.Column(db.String(255), nullable=False)

    items = db.Column(db.Text, nullable=False)  # JSON: [{"plat_id":.., "nom":.., "prix":.., "quantite":..}]
    montant_total = db.Column(db.Float, nullable=False)
    message = db.Column(db.Text)

    statut = db.Column(db.String(20), default="initiee")  # initiee / en_preparation / en_livraison / livree / annulee
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

    restaurant = db.relationship("Restaurant", backref="commandes")
    livreur = db.relationship("Livreur", backref="commandes_nourriture")

    def to_dict(self):
        return {
            "id": self.id, "restaurant_id": self.restaurant_id, "restaurant_nom": self.restaurant.nom if self.restaurant else None,
            "livreur_id": self.livreur_id, "livreur_nom": self.livreur.nom if self.livreur else None,
            "client_nom": self.client_nom, "client_telephone": self.client_telephone,
            "adresse_livraison": self.adresse_livraison,
            "items": json.loads(self.items) if self.items else [],
            "montant_total": self.montant_total, "message": self.message,
            "statut": self.statut, "date_creation": self.date_creation.isoformat(),
        }


class Commerce(db.Model):
    """Annuaire universel : n'importe quel type de commerce ou service peut s'inscrire ici,
    même s'il ne correspond à aucune catégorie spécifique déjà codée dans l'app (hôtel, restaurant...).
    C'est la porte d'entrée pour tout business qui n'a pas encore de système dédié."""
    __tablename__ = "commerces"

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(150), nullable=False)
    categorie = db.Column(db.String(30), default="autre")  # ecommerce / restaurant / finance / client_service / autre
    description_activite = db.Column(db.Text, nullable=False)  # "ce qu'il fait", en texte libre
    pays = db.Column(db.String(50), nullable=False)
    ville = db.Column(db.String(100), nullable=False)
    telephone = db.Column(db.String(30), nullable=False)
    photo = db.Column(db.String(255))
    actif = db.Column(db.Boolean, default=True)
    date_inscription = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "nom": self.nom, "categorie": self.categorie,
            "description_activite": self.description_activite,
            "pays": self.pays, "ville": self.ville, "telephone": self.telephone, "photo": self.photo,
            "date_inscription": self.date_inscription.isoformat(),
        }


class OffreTroc(db.Model):
    """Un producteur propose d'échanger un produit contre un autre, sans argent."""
    __tablename__ = "offres_troc"

    id = db.Column(db.Integer, primary_key=True)
    producteur_id = db.Column(db.Integer, db.ForeignKey("producteurs.id"), nullable=False)
    produit_propose = db.Column(db.String(150), nullable=False)
    quantite_proposee = db.Column(db.Float, nullable=False)
    unite = db.Column(db.String(30), default="kg")
    produit_recherche = db.Column(db.String(255), nullable=False)  # ce qu'il veut en échange
    description = db.Column(db.Text)
    statut = db.Column(db.String(20), default="ouverte")  # ouverte / conclue / annulee
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

    producteur = db.relationship("Producteur", backref="offres_troc")
    propositions = db.relationship("PropositionTroc", backref="offre", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id, "producteur_id": self.producteur_id,
            "producteur_nom": self.producteur.nom if self.producteur else None,
            "producteur_ville": self.producteur.ville if self.producteur else None,
            "producteur_pays": self.producteur.pays if self.producteur else None,
            "produit_propose": self.produit_propose, "quantite_proposee": self.quantite_proposee, "unite": self.unite,
            "produit_recherche": self.produit_recherche, "description": self.description,
            "statut": self.statut, "date_creation": self.date_creation.isoformat(),
            "nombre_propositions": len(self.propositions),
        }


class PropositionTroc(db.Model):
    """Contre-proposition d'un autre producteur pour répondre à une offre de troc."""
    __tablename__ = "propositions_troc"

    id = db.Column(db.Integer, primary_key=True)
    offre_troc_id = db.Column(db.Integer, db.ForeignKey("offres_troc.id"), nullable=False)
    producteur_id = db.Column(db.Integer, db.ForeignKey("producteurs.id"), nullable=False)
    produit_offert_en_retour = db.Column(db.String(150), nullable=False)
    quantite = db.Column(db.Float, nullable=False)
    unite = db.Column(db.String(30), default="kg")
    message = db.Column(db.Text)
    statut = db.Column(db.String(20), default="proposee")  # proposee / acceptee / refusee
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

    producteur = db.relationship("Producteur", backref="propositions_troc")

    def to_dict(self):
        return {
            "id": self.id, "offre_troc_id": self.offre_troc_id,
            "producteur_id": self.producteur_id, "producteur_nom": self.producteur.nom if self.producteur else None,
            "producteur_telephone": self.producteur.telephone if self.producteur else None,
            "produit_offert_en_retour": self.produit_offert_en_retour, "quantite": self.quantite, "unite": self.unite,
            "message": self.message, "statut": self.statut, "date_creation": self.date_creation.isoformat(),
        }


class JourMarche(db.Model):
    """Calendrier communautaire des jours de marché traditionnels par village/ville."""
    __tablename__ = "jours_marche"

    id = db.Column(db.Integer, primary_key=True)
    ville = db.Column(db.String(100), nullable=False)
    pays = db.Column(db.String(50), nullable=False)
    jour_semaine = db.Column(db.Integer, nullable=False)  # 0 = lundi ... 6 = dimanche
    nom_marche = db.Column(db.String(150))  # ex: "Grand marché de Bouaké"
    description = db.Column(db.Text)
    ajoute_par_producteur_id = db.Column(db.Integer, db.ForeignKey("producteurs.id"))
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
        return {
            "id": self.id, "ville": self.ville, "pays": self.pays,
            "jour_semaine": self.jour_semaine, "jour_semaine_label": jours[self.jour_semaine],
            "nom_marche": self.nom_marche, "description": self.description,
        }


class Tontine(db.Model):
    """Tontine digitale : épargne tournante entre producteurs. Chaque cycle, un membre différent
    reçoit le pot commun, selon un ordre de rotation fixé à l'adhésion."""
    __tablename__ = "tontines"

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(150), nullable=False)
    createur_id = db.Column(db.Integer, db.ForeignKey("producteurs.id"), nullable=False)
    pays = db.Column(db.String(50), nullable=False)
    ville = db.Column(db.String(100), nullable=False)
    montant_cotisation = db.Column(db.Float, nullable=False)  # montant fixe par membre et par cycle
    frequence = db.Column(db.String(20), default="mensuelle")  # hebdomadaire / mensuelle
    nombre_membres_max = db.Column(db.Integer, nullable=False)
    cycle_actuel = db.Column(db.Integer, default=1)
    statut = db.Column(db.String(20), default="ouverte")  # ouverte (recrute encore) / en_cours / terminee
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

    createur = db.relationship("Producteur", backref="tontines_creees")
    membres = db.relationship("MembreTontine", backref="tontine", lazy=True, cascade="all, delete-orphan", order_by="MembreTontine.ordre_tour")
    cotisations = db.relationship("CotisationTontine", backref="tontine", lazy=True, cascade="all, delete-orphan")

    def beneficiaire_cycle_actuel(self):
        for m in self.membres:
            if m.ordre_tour == ((self.cycle_actuel - 1) % max(1, len(self.membres))) + 1:
                return m
        return None

    def to_dict(self):
        beneficiaire = self.beneficiaire_cycle_actuel()
        return {
            "id": self.id, "nom": self.nom, "createur_id": self.createur_id,
            "createur_nom": self.createur.nom if self.createur else None,
            "pays": self.pays, "ville": self.ville,
            "montant_cotisation": self.montant_cotisation, "frequence": self.frequence,
            "nombre_membres_max": self.nombre_membres_max, "nombre_membres_actuel": len(self.membres),
            "cycle_actuel": self.cycle_actuel, "statut": self.statut,
            "beneficiaire_cycle_actuel": beneficiaire.producteur.nom if beneficiaire and beneficiaire.producteur else None,
            "date_creation": self.date_creation.isoformat(),
        }


class MembreTontine(db.Model):
    __tablename__ = "membres_tontine"

    id = db.Column(db.Integer, primary_key=True)
    tontine_id = db.Column(db.Integer, db.ForeignKey("tontines.id"), nullable=False)
    producteur_id = db.Column(db.Integer, db.ForeignKey("producteurs.id"), nullable=False)
    ordre_tour = db.Column(db.Integer, nullable=False)  # position dans la rotation (1, 2, 3...)
    date_adhesion = db.Column(db.DateTime, default=datetime.utcnow)

    producteur = db.relationship("Producteur", backref="tontines_rejointes")

    def to_dict(self):
        return {
            "id": self.id, "tontine_id": self.tontine_id,
            "producteur_id": self.producteur_id, "producteur_nom": self.producteur.nom if self.producteur else None,
            "producteur_telephone": self.producteur.telephone if self.producteur else None,
            "ordre_tour": self.ordre_tour, "date_adhesion": self.date_adhesion.isoformat(),
        }


class CotisationTontine(db.Model):
    """Cotisation d'un membre pour un cycle donné. Validée manuellement par l'admin
    (même principe que les recharges agent), en attendant un paiement en ligne actif."""
    __tablename__ = "cotisations_tontine"

    id = db.Column(db.Integer, primary_key=True)
    tontine_id = db.Column(db.Integer, db.ForeignKey("tontines.id"), nullable=False)
    membre_id = db.Column(db.Integer, db.ForeignKey("membres_tontine.id"), nullable=False)
    cycle_numero = db.Column(db.Integer, nullable=False)
    montant = db.Column(db.Float, nullable=False)
    reference = db.Column(db.String(120))
    statut = db.Column(db.String(20), default="declaree")  # declaree / validee
    date_declaration = db.Column(db.DateTime, default=datetime.utcnow)
    date_validation = db.Column(db.DateTime)

    membre = db.relationship("MembreTontine", backref="cotisations")

    def to_dict(self):
        return {
            "id": self.id, "tontine_id": self.tontine_id, "membre_id": self.membre_id,
            "membre_nom": self.membre.producteur.nom if self.membre and self.membre.producteur else None,
            "cycle_numero": self.cycle_numero, "montant": self.montant, "reference": self.reference,
            "statut": self.statut, "date_declaration": self.date_declaration.isoformat(),
        }


class OffreEmploi(db.Model):
    """Offre d'emploi publiée par une entreprise, un producteur ou toute structure recherchant du personnel."""
    __tablename__ = "offres_emploi"

    id = db.Column(db.Integer, primary_key=True)
    entreprise_nom = db.Column(db.String(150), nullable=False)
    titre_poste = db.Column(db.String(150), nullable=False)
    description_poste = db.Column(db.Text, nullable=False)
    type_contrat = db.Column(db.String(30), default="CDI")  # CDI / CDD / Stage / Freelance / Saisonnier
    salaire_propose = db.Column(db.String(100))  # texte libre, ex: "150 000 - 200 000 FCFA/mois"
    pays = db.Column(db.String(50), nullable=False)
    ville = db.Column(db.String(100), nullable=False)
    telephone_contact = db.Column(db.String(30), nullable=False)
    statut = db.Column(db.String(20), default="ouverte")  # ouverte / fermee
    date_publication = db.Column(db.DateTime, default=datetime.utcnow)

    candidatures = db.relationship("Candidature", backref="offre", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id, "entreprise_nom": self.entreprise_nom, "titre_poste": self.titre_poste,
            "description_poste": self.description_poste, "type_contrat": self.type_contrat,
            "salaire_propose": self.salaire_propose, "pays": self.pays, "ville": self.ville,
            "telephone_contact": self.telephone_contact, "statut": self.statut,
            "date_publication": self.date_publication.isoformat(),
            "nombre_candidatures": len(self.candidatures),
        }


class Candidature(db.Model):
    """Candidature spontanée d'un utilisateur à une offre d'emploi."""
    __tablename__ = "candidatures"

    id = db.Column(db.Integer, primary_key=True)
    offre_emploi_id = db.Column(db.Integer, db.ForeignKey("offres_emploi.id"), nullable=False)
    nom = db.Column(db.String(120), nullable=False)
    telephone = db.Column(db.String(30), nullable=False)
    message = db.Column(db.Text)
    date_candidature = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "offre_emploi_id": self.offre_emploi_id,
            "nom": self.nom, "telephone": self.telephone, "message": self.message,
            "date_candidature": self.date_candidature.isoformat(),
        }


class OpportuniteInvestissement(db.Model):
    """Annonce de recherche d'investisseurs pour un projet. Mise en relation uniquement :
    aucune transaction financière ne passe par AgriChange, exactement comme pour les terrains."""
    __tablename__ = "opportunites_investissement"

    id = db.Column(db.Integer, primary_key=True)
    nom_projet = db.Column(db.String(150), nullable=False)
    entreprise_porteuse = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    secteur = db.Column(db.String(100))
    montant_recherche = db.Column(db.String(100))  # texte libre, ex: "5 000 000 FCFA"
    pays = db.Column(db.String(50), nullable=False)
    ville = db.Column(db.String(100), nullable=False)
    contact_nom = db.Column(db.String(120), nullable=False)
    contact_telephone = db.Column(db.String(30), nullable=False)
    statut = db.Column(db.String(20), default="ouverte")  # ouverte / clotturee
    date_publication = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "nom_projet": self.nom_projet, "entreprise_porteuse": self.entreprise_porteuse,
            "description": self.description, "secteur": self.secteur, "montant_recherche": self.montant_recherche,
            "pays": self.pays, "ville": self.ville, "contact_nom": self.contact_nom,
            "contact_telephone": self.contact_telephone, "statut": self.statut,
            "date_publication": self.date_publication.isoformat(),
        }


class Cooperative(db.Model):
    """Coopérative virtuelle : regroupement de producteurs pour négocier ensemble de plus gros volumes."""
    __tablename__ = "cooperatives"

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    pays = db.Column(db.String(50))
    ville = db.Column(db.String(100))
    createur_id = db.Column(db.Integer, db.ForeignKey("producteurs.id"), nullable=False)
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

    createur = db.relationship("Producteur")
    membres = db.relationship("MembreCooperative", backref="cooperative", lazy=True)

    def to_dict(self):
        return {
            "id": self.id, "nom": self.nom, "description": self.description,
            "pays": self.pays, "ville": self.ville,
            "createur_id": self.createur_id, "createur_nom": self.createur.nom if self.createur else None,
            "nombre_membres": len(self.membres),
            "date_creation": self.date_creation.isoformat(),
        }


class MembreCooperative(db.Model):
    """Adhésion d'un producteur à une coopérative virtuelle."""
    __tablename__ = "membres_cooperative"

    id = db.Column(db.Integer, primary_key=True)
    cooperative_id = db.Column(db.Integer, db.ForeignKey("cooperatives.id"), nullable=False)
    producteur_id = db.Column(db.Integer, db.ForeignKey("producteurs.id"), nullable=False)
    date_adhesion = db.Column(db.DateTime, default=datetime.utcnow)

    producteur = db.relationship("Producteur")

    __table_args__ = (
        db.UniqueConstraint("cooperative_id", "producteur_id", name="uq_membre_cooperative"),
    )

    def to_dict(self):
        return {
            "id": self.id, "producteur_id": self.producteur_id,
            "producteur_nom": self.producteur.nom if self.producteur else None,
            "producteur_ville": self.producteur.ville if self.producteur else None,
            "date_adhesion": self.date_adhesion.isoformat(),
        }


class Invendu(db.Model):
    """Surplus ou invendu proposé à prix cassé, ou en don, pour éviter le gaspillage."""
    __tablename__ = "invendus"

    id = db.Column(db.Integer, primary_key=True)
    producteur_id = db.Column(db.Integer, db.ForeignKey("producteurs.id"), nullable=False)

    nom = db.Column(db.String(150), nullable=False)
    quantite = db.Column(db.Float, nullable=False)
    unite = db.Column(db.String(20), default="kg")
    prix_reduit = db.Column(db.Float, default=0)  # 0 = don gratuit
    description = db.Column(db.Text)

    actif = db.Column(db.Boolean, default=True)
    date_ajout = db.Column(db.DateTime, default=datetime.utcnow)

    producteur = db.relationship("Producteur")

    def to_dict(self):
        return {
            "id": self.id,
            "producteur_id": self.producteur_id,
            "producteur_nom": self.producteur.nom if self.producteur else None,
            "producteur_ville": self.producteur.ville if self.producteur else None,
            "producteur_pays": self.producteur.pays if self.producteur else None,
            "producteur_telephone": self.producteur.telephone if self.producteur else None,
            "nom": self.nom,
            "quantite": self.quantite,
            "unite": self.unite,
            "prix_reduit": self.prix_reduit,
            "est_don": self.prix_reduit == 0,
            "description": self.description,
            "actif": self.actif,
            "date_ajout": self.date_ajout.isoformat(),
        }


class Signalement(db.Model):
    """Signalement communautaire d'un comportement suspect (anti-arnaque)."""
    __tablename__ = "signalements"

    id = db.Column(db.Integer, primary_key=True)
    signale_type = db.Column(db.String(20), nullable=False)  # producteur / acheteur / livreur
    signale_id = db.Column(db.Integer, nullable=False)
    signale_nom = db.Column(db.String(150))

    signale_par_nom = db.Column(db.String(120))
    signale_par_telephone = db.Column(db.String(30))

    motif = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)

    statut = db.Column(db.String(20), default="ouvert")  # ouvert / traite
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "signale_type": self.signale_type,
            "signale_id": self.signale_id,
            "signale_nom": self.signale_nom,
            "signale_par_nom": self.signale_par_nom,
            "signale_par_telephone": self.signale_par_telephone,
            "motif": self.motif,
            "description": self.description,
            "statut": self.statut,
            "date_creation": self.date_creation.isoformat(),
        }



class TicketSupport(db.Model):
    """Message envoyé par un utilisateur au support client."""
    __tablename__ = "tickets_support"

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(120), nullable=False)
    telephone = db.Column(db.String(20), nullable=False)
    sujet = db.Column(db.String(150))
    message = db.Column(db.Text, nullable=False)
    type_compte = db.Column(db.String(20))

    statut = db.Column(db.String(20), default="ouvert")
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "nom": self.nom,
            "telephone": self.telephone,
            "sujet": self.sujet,
            "message": self.message,
            "type_compte": self.type_compte,
            "statut": self.statut,
            "date_creation": self.date_creation.isoformat(),
        }


class TrajetPoint(db.Model):
    """Un point GPS horodaté du trajet réel parcouru pendant une livraison (traçabilité)."""
    __tablename__ = "trajet_points"

    id = db.Column(db.Integer, primary_key=True)
    commande_id = db.Column(db.Integer, db.ForeignKey("commandes.id"), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    horodatage = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "horodatage": self.horodatage.isoformat(),
        }


class Commande(db.Model):
    """Commande passée par un acheteur pour un produit."""
    __tablename__ = "commandes"

    id = db.Column(db.Integer, primary_key=True)
    acheteur_id = db.Column(db.Integer, db.ForeignKey("acheteurs.id"), nullable=False)
    produit_id = db.Column(db.Integer, db.ForeignKey("produits.id"), nullable=False)
    livreur_id = db.Column(db.Integer, db.ForeignKey("livreurs.id"))

    panier_id = db.Column(db.String(20))

    quantite = db.Column(db.Float, nullable=False)
    prix_total = db.Column(db.Float, nullable=False)
    commission_taux = db.Column(db.Float, default=0.08)  # 8% AgriChange + ~3,5% CinetPay = ~11,5% au total
    commission_montant = db.Column(db.Float)
    montant_producteur = db.Column(db.Float)

    frais_livraison = db.Column(db.Float, default=0)
    statut_paiement_livreur = db.Column(db.String(20), default="en_attente")  # en_attente / du / verse
    retour_confirme = db.Column(db.Boolean, default=False)  # le producteur a confirmé avoir récupéré le colis retourné

    statut = db.Column(db.String(30), default="en_attente")

    latitude_livraison = db.Column(db.Float)
    longitude_livraison = db.Column(db.Float)

    latitude_livreur = db.Column(db.Float)
    longitude_livreur = db.Column(db.Float)
    position_livreur_maj = db.Column(db.DateTime)

    reference_paiement = db.Column(db.String(100))
    date_commande = db.Column(db.DateTime, default=datetime.utcnow)

    acheteur = db.relationship("Acheteur", backref="commandes")
    produit = db.relationship("Produit", backref="commandes")

    def calculer_montants(self):
        taux = self.commission_taux if self.commission_taux is not None else 0.08
        self.commission_montant = round(self.prix_total * taux, 2)
        self.montant_producteur = round(self.prix_total - self.commission_montant, 2)

    def to_dict(self):
        return {
            "id": self.id,
            "acheteur_id": self.acheteur_id,
            "acheteur": self.acheteur.nom if self.acheteur else None,
            "produit_id": self.produit_id,
            "produit": self.produit.nom if self.produit else None,
            "produit_photo_url": self.produit.photo_url if self.produit else None,
            "produit_unite": self.produit.unite if self.produit else None,
            "producteur_id": self.produit.producteur_id if self.produit else None,
            "producteur_nom": self.produit.producteur.nom if self.produit and self.produit.producteur else None,
            "producteur_latitude": self.produit.producteur.latitude if self.produit and self.produit.producteur else None,
            "producteur_longitude": self.produit.producteur.longitude if self.produit and self.produit.producteur else None,
            "livreur_id": self.livreur_id,
            "livreur_nom": self.livreur.nom if self.livreur else None,
            "panier_id": self.panier_id,
            "quantite": self.quantite,
            "prix_total": self.prix_total,
            "commission_montant": self.commission_montant,
            "montant_producteur": self.montant_producteur,
            "frais_livraison": self.frais_livraison,
            "statut_paiement_livreur": self.statut_paiement_livreur,
            "retour_confirme": self.retour_confirme,
            "statut": self.statut,
            "latitude_livraison": self.latitude_livraison,
            "longitude_livraison": self.longitude_livraison,
            "latitude_livreur": self.latitude_livreur,
            "longitude_livreur": self.longitude_livreur,
            "position_livreur_maj": self.position_livreur_maj.isoformat() if self.position_livreur_maj else None,
            "reference_paiement": self.reference_paiement,
            "date_commande": self.date_commande.isoformat(),
        }
