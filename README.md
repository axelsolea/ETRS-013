# ⚡ Planificateur d'Itinéraire pour Véhicules Électriques (SOA)

Ce projet est une application web basée sur une **Architecture Orientée Services (SOA)** permettant de planifier des trajets en véhicule électrique (VE). L'application calcule l'itinéraire optimal, identifie les besoins de recharge en fonction de l'autonomie réelle du véhicule sélectionné et positionne les bornes de recharge nécessaires sur la carte.

Projet réalisé dans le cadre du module **ETRS013 - Architectures Orientées Service** à l'Université Savoie Mont Blanc.

---

## 🚀 Fonctionnalités

* **Catalogue de Véhicules :** Récupération dynamique d'une liste de véhicules électriques et de leurs caractéristiques (batterie, autonomie, connecteurs) via une API GraphQL externe.
* **Calcul d'Itinéraire Intelligent :** Algorithme prenant en compte l'autonomie du véhicule pour déterminer les segments de conduite et les arrêts nécessaires.
* **Localisation des Bornes :** Recherche de bornes de recharge réelles (Base de données nationale IRVE) à proximité des points critiques du trajet.
* **Visualisation Cartographique :** Affichage interactif du tracé, des étapes et des marqueurs de recharge sur une carte (Folium/Leaflet).
* **API Publique (M2M) :** Mise à disposition d'une API REST JSON permettant à des tiers d'intégrer le moteur de calcul sans interface graphique.

---

## 🛠️ Architecture Technique

Le projet est divisé en deux micro-services distincts déployés sur le Cloud (Microsoft Azure) :

### 1. Moteur de Calcul (Backend SOAP)
* **Fichier :** `WS.py`
* **Technologie :** Python, Spyne (Protocole SOAP).
* **Rôle :** Expose les méthodes de calcul (`near_charging`, `forward`, `compute_travel`).
* **APIs Externes Consommées :**
    * *OpenRouteService* : Géométrie et navigation.
    * *OpenDataSoft (Bornes IRVE)* : Localisation des bornes.
    * *OpenCage Data* : Géocodage (Adresse ↔ GPS).
    * *Chargetrip* : Données véhicules (GraphQL).

### 2. Interface & Gateway (Frontend Flask)
* **Fichier :** `WServer.py`
* **Technologie :** Python, Flask, Zeep (Client SOAP).
* **Rôle :** Serveur Web pour l'IHM HTML/Bootstrap et point d'entrée de l'API REST JSON. Il agit comme un client qui consomme le service SOAP.

---

# ☁️ Déploiement sur Azure
## L'application nécessite deux App Services distincts sur Azure (un pour le moteur, un pour l'interface).
### Configuration du Moteur (WS.py)
Commande de démarrage :
```Bash
gunicorn --bind=0.0.0.0 --timeout 600 WS:wsgi_application
```

### Configuration de l'Interface (WServer.py)
Commande de démarrage :
```Bash
gunicorn --bind=0.0.0.0 --timeout 600 WServer:app
```
Liaison : Variable wsdl dans WServer.py pour pointer vers l'URL Azure du moteur SOAP :
```Python
wsdl = 'https://soap-engine-<id>.<server>.azurewebsites.net/?wsdl'
```
---
# Documentation de l'API (M2M)
Une API REST JSON est disponible via le service Flask pour permettre l'intégration du calcul d'itinéraire dans des applications tierces.
### Endpoint : Calculer un trajet
- URL : /api/calculate_trip
- Méthode : POST
- Format : JSON

### Paramètres d'entrée
| Champ | Type | Obligatoire | Description |
| :--- | :--- | :---: | :--- |
| `start` | `string` | Oui | Ville ou adresse de départ (ex: "Cognin"). |
| `end` | `string` | Oui | Ville ou adresse d'arrivée (ex: "Brest"). |
| `vehiculeId` | `string` | Oui | ID unique du véhicule (issu de l'API Chargetrip). |

### Exemple de Requête (Body)
```json
{
    "start": "Cognin",
    "end": "Brest",
    "vehiculeId": "5f043b26bc262f1627fc0233" 
}
```

### Exemple de Réponse (200 OK)
```json
{
    "trajet": {
        "depart": {
            "adresse": "Cognin, France",
            "lat": 45.558,
            "lng": 5.893
        },
        "arrivee": {
            "adresse": "Brest, France",
            "lat": 48.390,
            "lng": -4.486
        },
        "distance_km": 1075.42,
        "temps_total_str": "12h 30min",
        "temps_conduite_str": "10h 15min",
        "temps_recharge_str": "2h 15min",
        "nb_arrets": 3
    },
    "bornes_recharge": [
        {
            "nom": "Ionity Aire de Macon",
            "latitude": 46.1234,
            "longitude": 4.8901,
            "puissance": 350
        },
        {
            "nom": "TotalEnergies Relais...",
            "latitude": 47.5678,
            "longitude": 3.1234,
            "puissance": 175
        }
    ],
    "vehicule": {
        "id": "5f043b26bc262f1627fc0233",
        "modele": "Tesla Model S",
        "autonomie_theorique": 350
    }
}
```
### Gestion des Erreurs
- 400 Bad Request : Paramètres manquants.
- 404 Not Found : Véhicule introuvable.
- 500 Internal Server Error : Problème de calcul ou de service tiers.
