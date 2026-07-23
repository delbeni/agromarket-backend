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

    type_production = db.Column(db.String(50))  # cereales, elevage, maraichage, transforme
    description = db.Column(db.Text)

    photo_url = db.Column(db.String(255))
    histoire = db.Column(db.Text)

    verifie = db.Column(db.Boolean, default=False)  # badge "vendeur vérifié", accordé par l'admin

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
            "type_production": self.type_production,
            "description": self.description,
            "photo_url": self.photo_url,
            "histoire": self.histoire,
            "verifie": self.verifie,
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
    categorie = db.Column(db.String(50), nullable=False)  # cereales, elevage, maraichage, transforme
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

    date_inscription = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "nom": self.nom,
            "telephone": self.telephone,
            "pays": self.pays,
            "ville": self.ville,
            "adresse_livraison": self.adresse_livraison,
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


class Commande(db.Model):
    """Commande passée par un acheteur pour un produit."""
    __tablename__ = "commandes"

    id = db.Column(db.Integer, primary_key=True)
    acheteur_id = db.Column(db.Integer, db.ForeignKey("acheteurs.id"), nullable=False)
    produit_id = db.Column(db.Integer, db.ForeignKey("produits.id"), nullable=False)

    quantite = db.Column(db.Float, nullable=False)
    prix_total = db.Column(db.Float, nullable=False)  # avant commission
    commission_taux = db.Column(db.Float, default=0.08)  # 8% par défaut
    commission_montant = db.Column(db.Float)
    montant_producteur = db.Column(db.Float)  # ce que le producteur reçoit

    statut = db.Column(db.String(30), default="en_attente")
    # en_attente -> confirmee_producteur -> livree -> terminee / annulee

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
            "quantite": self.quantite,
            "prix_total": self.prix_total,
            "commission_montant": self.commission_montant,
            "montant_producteur": self.montant_producteur,
            "statut": self.statut,
            "reference_paiement": self.reference_paiement,
            "date_commande": self.date_commande.isoformat(),
        }
