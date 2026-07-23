from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

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
    zone_livraison = db.Column(db.String(255))  # ex: "Abidjan - Cocody, Yopougon"

    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

    type_production = db.Column(db.String(50))  # cereales, elevage, maraichage, transforme
    description = db.Column(db.Text)

    photo_url = db.Column(db.String(255))
    histoire = db.Column(db.Text)

    verifie = db.Column(db.Boolean, default=False)  # badge "vendeur vérifié", accordé par l'admin

    code_parrainage = db.Column(db.String(10), unique=True)  # code à partager
    code_parrain_utilise = db.Column(db.String(10))  # code d'un autre producteur, saisi à l'inscription
    nombre_filleuls = db.Column(db.Integer, default=0)

    push_token = db.Column(db.String(255))  # jeton Expo pour notifications push

    actif = db.Column(db.Boolean, default=True)
    date_inscription = db.Column(db.DateTime, default=datetime.utcnow)

    produits = db.relationship("Produit", backref="producteur", lazy=True)
    avis = db.relationship("Avis", backref="producteur", lazy=True)

    def to_dict(self):
        notes = [a.note for a in self.avis]
        note_moyenne = round(sum(notes) / len(notes), 1) if notes else None
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
            "verifie": self.verifie,
            "code_parrainage": self.code_parrainage,
            "nombre_filleuls": self.nombre_filleuls,
            "actif": self.actif,
            "date_inscription": self.date_inscription.isoformat(),
            "nombre_produits": len(self.produits),
            "note_moyenne": note_moyenne,
            "nombre_avis": len(notes),
        }


class Produit(db.Model):
    """Produit mis en vente par un producteur."""
    __tablename__ = "produits"

    id = db.Column(db.Integer, primary_key=True)
    producteur_id = db.Column(db.Integer, db.ForeignKey("producteurs.id"), nullable=False)

    nom = db.Column(db.String(150), nullable=False)
    categorie = db.Column(db.String(50), nullable=False)  # cereales, elevage, maraichage, transforme, restaurant, autre
    prix_unitaire = db.Column(db.Float, nullable=False)  # en FCFA
    unite = db.Column(db.String(20), default="unité")  # kg, sac, unité, litre
    quantite_disponible = db.Column(db.Float, nullable=False, default=0)
    photo_url = db.Column(db.String(255))  # photo de couverture (première photo), pour compatibilité
    photos_urls = db.Column(db.Text)  # liste JSON de toutes les photos (jusqu'à 4)
    video_url = db.Column(db.String(500))  # courte vidéo (15s max)
    description = db.Column(db.Text)

    actif = db.Column(db.Boolean, default=True)
    date_ajout = db.Column(db.DateTime, default=datetime.utcnow)

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
            "actif": self.actif,
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

    push_token = db.Column(db.String(255))  # jeton Expo pour notifications push

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
    vehicule = db.Column(db.String(50))  # moto, voiture, tricycle, à pied...

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

    expediteur_type = db.Column(db.String(20), nullable=False)  # "acheteur" ou "producteur"
    contenu_original = db.Column(db.Text, nullable=False)
    contenu_filtre = db.Column(db.Text, nullable=False)  # ce qui est réellement affiché
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

    note = db.Column(db.Integer, nullable=False)  # de 1 à 5
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


class TicketSupport(db.Model):
    """Message envoyé par un utilisateur au support client."""
    __tablename__ = "tickets_support"

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(120), nullable=False)
    telephone = db.Column(db.String(20), nullable=False)
    sujet = db.Column(db.String(150))
    message = db.Column(db.Text, nullable=False)
    type_compte = db.Column(db.String(20))  # "producteur", "acheteur", "livreur" ou "visiteur"

    statut = db.Column(db.String(20), default="ouvert")  # "ouvert" ou "traite"
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


class Commande(db.Model):
    """Commande passée par un acheteur pour un produit."""
    __tablename__ = "commandes"

    id = db.Column(db.Integer, primary_key=True)
    acheteur_id = db.Column(db.Integer, db.ForeignKey("acheteurs.id"), nullable=False)
    produit_id = db.Column(db.Integer, db.ForeignKey("produits.id"), nullable=False)
    livreur_id = db.Column(db.Integer, db.ForeignKey("livreurs.id"))

    panier_id = db.Column(db.String(20))  # regroupe plusieurs commandes validées en un seul panier multi-vendeurs

    quantite = db.Column(db.Float, nullable=False)
    prix_total = db.Column(db.Float, nullable=False)  # avant commission
    commission_taux = db.Column(db.Float, default=0.08)  # 8% par défaut
    commission_montant = db.Column(db.Float)
    montant_producteur = db.Column(db.Float)  # ce que le producteur reçoit

    statut = db.Column(db.String(30), default="en_attente")
    # en_attente -> confirmee_producteur -> livree -> terminee / annulee

    # Position de livraison choisie par l'acheteur à la commande
    latitude_livraison = db.Column(db.Float)
    longitude_livraison = db.Column(db.Float)

    # Suivi en direct : dernière position partagée par le livreur (ou le producteur) pour cette commande
    latitude_livreur = db.Column(db.Float)
    longitude_livreur = db.Column(db.Float)
    position_livreur_maj = db.Column(db.DateTime)

    reference_paiement = db.Column(db.String(100))  # id transaction CinetPay/PayDunya
    date_commande = db.Column(db.DateTime, default=datetime.utcnow)

    acheteur = db.relationship("Acheteur", backref="commandes")
    produit = db.relationship("Produit", backref="commandes")

    def calculer_montants(self):
        self.commission_montant = round(self.prix_total * self.commission_taux, 2)
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
            "livreur_id": self.livreur_id,
            "livreur_nom": self.livreur.nom if self.livreur else None,
            "panier_id": self.panier_id,
            "quantite": self.quantite,
            "prix_total": self.prix_total,
            "commission_montant": self.commission_montant,
            "montant_producteur": self.montant_producteur,
            "statut": self.statut,
            "latitude_livraison": self.latitude_livraison,
            "longitude_livraison": self.longitude_livraison,
            "latitude_livreur": self.latitude_livreur,
            "longitude_livreur": self.longitude_livreur,
            "position_livreur_maj": self.position_livreur_maj.isoformat() if self.position_livreur_maj else None,
            "reference_paiement": self.reference_paiement,
            "date_commande": self.date_commande.isoformat(),
        }
