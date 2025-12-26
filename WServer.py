#Imports
from flask import Flask, render_template, request, jsonify
import folium
import zeep
import json
import math

app = Flask(__name__)

# APIZeep définition du Service Web

#wsdl = 'http://127.0.0.1:8000/?wsdl' ### Pour le developpement en local
wsdl = 'https://soap-engine-bth0b0d3hpfqd7e7.francecentral-01.azurewebsites.net/?wsdl'
client = zeep.Client(wsdl=wsdl)


def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calcule la distance géodésique entre deux points INFOS.md.

    Args:
        lat1 (float): Latitude du point 1.
        lon1 (float): Longitude du point 1.
        lat2 (float): Latitude du point 2.
        lon2 (float): Longitude du point 2.

    Returns:
        float: Distance en kilomètres.
    """
    R = 6371  # Rayon de la Terre en km

    # Conversion en radians
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    # Formule de Haversine
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))

    return R * c


@app.route("/vehicules", methods=['GET', 'POST'])
def vehicules():
    """
    Route utilitaire retournant la liste brute des véhicules.

    Args:
        None (Utilise implicitement request).

    Returns:
        str: JSON brut de la liste des véhicules.
    """
    result = client.service.get_vehicule_list()
    return result

@app.route("/")
def components():
    """
    Génère la page d'accueil avec la carte et le sélecteur de véhicule.

    Args:
        None.

    Returns:
        Template HTML: 'index.html' avec la carte Folium et la liste des options véhicules.
    """
    m = folium.Map(
        width=800,
        height=600,
    )

    m.get_root().render()
    header = m.get_root().header.render()
    body_html = m.get_root().html.render()
    script = m.get_root().script.render()
    vehicule_json_str = client.service.get_vehicule_list()
    vehicule_data = json.loads(vehicule_json_str)

    vehicule_list_raw = vehicule_data.get("data", {}).get("vehicleList", [])

    vehicule_options = []
    for v in vehicule_list_raw:
        naming = v.get("naming", {})
        name = f"{naming.get('make', 'N/A')} {naming.get('model', 'N/A')}"
        # Stocker l'ID comme valeur (ce qui sera envoyé par le formulaire)
        vehicule_options.append({
            'id': v.get('id', ''),
            'name': name
        })
    return render_template("index.html", header=header, body_html=body_html, folium_script=script,
                           vehicules=vehicule_options)


@app.route("/computeTravel", methods=['GET', 'POST'])
def componentsCompute():
    """
        Orchestre le calcul complet : itinéraire, recherche de bornes et affichage.

        Args:
            None (Récupère 'start', 'end', 'vehicule' via request.form).

        Returns:
            Template HTML: 'results.html' avec la carte, le tracé et les statistiques.
        """
    try:
        # ---                     Key variables                          ---#
        m = folium.Map(
            width=800,
            height=600,
        )

        # ---                     Vehicule list                          ---#
        vehicule_json_str = client.service.get_vehicule_list()
        vehicule_data = json.loads(vehicule_json_str)

        vehicule_list_raw = vehicule_data.get("data", {}).get("vehicleList", [])

        vehicule_options = []
        for v in vehicule_list_raw:
            naming = v.get("naming", {})
            name = f"{naming.get('make', 'N/A')} {naming.get('model', 'N/A')}"
            # Stocker l'ID comme valeur (ce qui sera envoyé par le formulaire)
            vehicule_options.append({
                'id': v.get('id', ''),
                'name': name
            })

        # ---                     Post form values                          ---#
        start = request.form['start']
        end = request.form['end']
        vehiculeId = request.form['vehicule']

        # ---                    Key variables again                         ---#
        autonomieTot = 0
        autonomieTotkWh = 0
        for v in vehicule_data.get("data", {}).get("vehicleList", []):
            if v['id'] == vehiculeId:
                autonomieTot = v["range"]["chargetrip_range"]["worst"]
                autonomieTotkWh = v["battery"]["usable_kwh"]
        autonomieRestante = autonomieTot
        coordonneesBornes = []
        totalChargeSeconds = 0
        print("[DEBUG] Autonomie totale: " + str(autonomieTot))

        # ---                     Forward Geo Coding                          ---#
        # Forward result format : ["formatted address","latitude","longitude"]
        forwardStartResult = client.service.forward(start)
        forwardEndResult = client.service.forward(end)

        GeoJSONStr = client.service.compute_travel(
            forwardStartResult[2],
            forwardStartResult[1],
            forwardEndResult[2],
            forwardEndResult[1]
        )
        GeoJSON = json.loads(GeoJSONStr)
        print("[DEBUG] Primary path computed!")

        # ---                     Calcul primaire du chemin                          ---#
        listePtsChemin = []
        for lon, lat in GeoJSON["features"][0]["geometry"]["coordinates"]:
            listePtsChemin.append([lat, lon])

        print("[DEBUG] Computed listePtsChemin! Size: " + str(len(listePtsChemin)))

        # ---        Recalcul de l'itinéraire pour prendre en compte les bornes      ---#
        distance_parcourue = 0
        coordonneesBornes.append([float(forwardStartResult[2]), float(forwardStartResult[1])])
        print("[DEBUG] Begin computing logic based on geometry points...")
        for i in range(len(listePtsChemin) - 1):
            # Point actuel (A) et point suivant (B)
            p1_lat, p1_lon = listePtsChemin[i]
            p2_lat, p2_lon = listePtsChemin[i + 1]

            # Calcul de la distance de ce petit segment
            dist_segment = haversine_distance(p1_lat, p1_lon, p2_lat, p2_lon)

            # Vérification de l'autonomie
            if autonomieRestante - dist_segment < 10:
                print(f"[DEBUG] Low autonomy ({autonomieRestante:.2f} km) at point index {i}")

                try:
                    # Recherche de borne autour du point actuel (P1)
                    res_json = client.service.near_charging(
                        p1_lon,
                        p1_lat,
                        "10"
                    )
                    data = json.loads(res_json)

                    # Sécurité si l'API renvoie une liste vide ou mal formatée
                    next_station = None
                    if "results" in data and len(data["results"]) > 0:
                        next_station = data["results"][0]

                    # Tentative rayon plus large si échec
                    if not next_station:
                        print("[DEBUG] No station in 10km, trying 30km...")
                        res_json = client.service.near_charging(p1_lon, p1_lat, "30km")
                        data = json.loads(res_json)
                        if "results" in data and len(data["results"]) > 0:
                            next_station = data["results"][0]

                    if not next_station:
                        raise Exception("Pas de bornes trouvées")

                except Exception as e:
                    print(f"[DEBUG] Erreur recherche borne: {e}")
                    return render_template("results.html",
                                           erreur="Pas de bornes en portée d'autonomie sur le trajet (Zone blanche)")

                # Ajout de la borne à la liste des étapes
                coordonneesBornes.append((next_station["xlongitude"], next_station["ylatitude"]))
                print(f"[DEBUG] Found station at: {next_station['xlongitude']}, {next_station['ylatitude']}")

                # Calcul du temps de charge
                pourcentRestant = max(autonomieRestante, 0) / autonomieTot
                pourcentNecessaire = 0.80 - pourcentRestant  # On recharge jusqu'à 80%

                # Formule temps de charge (approximative)
                if pourcentNecessaire > 0:
                    temps_charge_heures = (autonomieTotkWh * pourcentNecessaire) / (next_station["puiss_max"] * 0.9)
                    totalChargeSeconds += temps_charge_heures * 3600
                    print(f"[DEBUG] Charging time added: {temps_charge_heures:.2f} hours")

                    # On "remplit" la batterie
                    autonomieRestante += (autonomieTot * pourcentNecessaire)
                    print("[DEBUG] Nouvelle autonomie : " + str(autonomieRestante))
                else:
                    print("[DEBUG] Battery still sufficient (>80%), skipping charge logic update but keeping station")

            # Soustraction de la distance parcourue sur ce segment
            autonomieRestante -= dist_segment
            distance_parcourue += dist_segment

        # ---                     Calcul secondaire du chemin                          ---#
        print("[DEBUG] Recomputing path...")
        coordonneesBornes.append([float(forwardEndResult[2]), float(forwardEndResult[1])])
        coordonneesStr = json.dumps(coordonneesBornes)
        GeoJSONStr = client.service.compute_travel_profiled(coordonneesStr)
        print("[DEBUG] Called compute_travel_profiled!")
        GeoJSON = json.loads(GeoJSONStr)
        listePtsChemin = []
        for lat, lng in GeoJSON["features"][0]["geometry"]["coordinates"]:
            listePtsChemin.append((lng, lat))
        print("[DEBUG] Second path computed")

        # --- CALCULS FINAUX ET FORMATAGE ---
        # Récupération de la liste des segments (il y en a autant que d'étapes + 1)
        segments = GeoJSON["features"][0]["properties"]["segments"]

        # On additionne la durée et la distance de CHAQUE segment
        totalDrivingSeconds = sum(seg["duration"] for seg in segments)
        totalDistanceMeters = sum(seg["distance"] for seg in segments)

        # Ajout du temps de charge calculé précédemment
        totalSeconds = totalDrivingSeconds + totalChargeSeconds

        # Formatage Distance (Mètres -> Km)
        dist_km = round(totalDistanceMeters / 1000, 2)

        # Fonction utilitaire pour convertir secondes -> "Xh Ymin"
        def format_time(seconds):
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            return f"{h}h {m}min"

        travel_time_formatted = format_time(totalSeconds)
        charge_time_formatted = format_time(totalChargeSeconds)

        # ---                     Tracé du chemin                          ---#
        folium.PolyLine(listePtsChemin, tooltip="Itinéraire").add_to(m)
        print("[DEBUG] Path traced")

        # ---                     Marqueur Bornes                          ---#
        for b in coordonneesBornes[1:len(coordonneesBornes) - 1]:
            folium.Marker(
                location=[b[1], b[0]],
                tooltip="Recharge",
                icon=folium.Icon(icon="plug-circle-bolt", prefix="fa")
            ).add_to(m)
            print("[DEBUG] Station added to folium to coord : " + str(b[1]) + " " + str(b[0]))
        print("[DEBUG] Charging stations marked")

        # ---                     Marqueur Source                          ---#
        folium.Marker(
            location=[forwardStartResult[1], forwardStartResult[2]],
            tooltip="Départ",
            popup=forwardStartResult[0],  # ADRESSE SOURCE
            icon=folium.Icon(color="green"),
        ).add_to(m)
        print("[DEBUG] Source marked")

        # ---                     Marqueur Destination                          ---#
        folium.Marker(
            location=[forwardEndResult[1], forwardEndResult[2]],
            tooltip="Arrivée",
            popup=forwardEndResult[0],  # ADRESSE DEST
            icon=folium.Icon(color="red"),
        ).add_to(m)
        print("[DEBUG] Destination marked")

        # ---                     Zoom auto                          ---#
        south_west = [min(forwardStartResult[1], forwardEndResult[1]), min(forwardStartResult[2], forwardEndResult[2])]
        north_east = [max(forwardStartResult[1], forwardEndResult[1]), max(forwardStartResult[2], forwardEndResult[2])]
        m.fit_bounds([south_west, north_east])
        print("[DEBUG] Map zoomed")

        # ---                     Rendu de la carte                          ---#
        m.get_root().render()
        header = m.get_root().header.render()
        body_html = m.get_root().html.render()
        script = m.get_root().script.render()
        print("[DEBUG] Map rendered")

        # --- RETOUR DU TEMPLATE AVEC LES VARIABLES ---
        return render_template(
            "results.html",
            header=header,
            body_html=body_html,
            folium_script=script,
            distance=dist_km,
            travelTime=travel_time_formatted,
            chargeTime=charge_time_formatted
        )

    except Exception as e:  # Affichage de l'erreur en cas d'erreur
        return render_template("results.html", erreur=str(e))




"""
    Point de terminaison API pour le calcul d'itinéraire électrique (M2M).

    Cette route permet à une application tierce (mobile, web, etc.) de consommer
    la logique de calcul de trajet et de placement des bornes sans utiliser 
    l'interface graphique HTML.

    Route : /api/calculate_trip
    Méthode : POST
    Type de contenu : application/json

    Paramètres d'entrée (JSON ou Formulaire) :
    ------------------------------------------
    - start (str) : Adresse de départ.
    - end (str) : Adresse de destination.
    - vehiculeId (str) : L'identifiant unique du véhicule (issu de l'API Chargetrip).

    Exemple de corps de requête :
    {
        "start": "Cognin",
        "end": "Brest",
        "vehiculeId": "5f043b26bc262f1627fc0233" (Tesla modèle S)
    }

    Réponse (JSON) :
    ----------------
    Retourne un objet JSON structuré contenant :
    - trajet : Résumé (distance, temps total avec charge, temps de conduite).
    - bornes_recharge : Liste des arrêts avec coordonnées INFOS.md exactes.
    - vehicule : Rappel des infos du véhicule utilisé.

    Exemple de réponse réussie (200 OK) :
    {
        "trajet": {
            "depart": {"adresse": "Cognin", "lat": 45.5, "lng": 5.8},
            "arrivee": {"adresse": "Brest", "lat": 48.3, "lng": -4.4},
            "distance_km": 1075.4,
            "temps_total_str": "12h 30min",
            "nb_arrets": 3
        },
        "bornes_recharge": [
            {
                "nom": "Ionity Aire de...",
                "latitude": 46.12,
                "longitude": 4.89,
                "puissance": 350
            }
        ],
        "vehicule": {
            "id": "5f04...",
            "autonomie_theorique": 350
        }
    }

    Codes d'erreur :
    ----------------
    - 400 : Paramètres manquants (start, end ou vehiculeId).
    - 404 : Véhicule non trouvé (ID incorrect ou hors liste).
    - 500 : Erreur interne (Problème de connexion aux services SOAP/Externes).
    """

@app.route("/api/calculate_trip", methods=['POST'])
def api_calculate_trip():
    """
        API JSON fournissant l'itinéraire et les bornes pour applications tierces.

        Args:
            None (Récupère 'start', 'end', 'vehiculeId' via JSON ou Form).

        Returns:
            Response (JSON): Objet contenant 'trajet', 'bornes_recharge' et 'vehicule'.
        """
    try:
        # --- 1. Récupération des paramètres ---
        data = request.get_json(force=True, silent=True)
        if not data:
            data = request.form

        start = data.get('start')
        end = data.get('end')
        raw_vehiculeId = data.get('vehiculeId') or data.get('vehicule')

        if not start or not end or not raw_vehiculeId:
            return jsonify({"error": "Parametres manquants (start, end, vehiculeId)"}), 400

        target_id = str(raw_vehiculeId).strip()

        # --- 2. Récupération Info Véhicule ---
        vehicule_json_str = client.service.get_vehicule_list()
        vehicule_data = json.loads(vehicule_json_str)
        vehicle_list = vehicule_data.get("data", {}).get("vehicleList", [])

        autonomieTot = 0
        autonomieTotkWh = 0
        found = False

        for v in vehicle_list:
            if str(v['id']).strip() == target_id:
                autonomieTot = v["range"]["chargetrip_range"]["worst"]
                autonomieTotkWh = v["battery"]["usable_kwh"]
                found = True
                break

        if not found:
            return jsonify({"error": "Véhicule non trouvé"}), 404

        # --- 3. Géocodage et Route Initiale ---
        startRes = client.service.forward(start)
        endRes = client.service.forward(end)

        # Appel SOAP pour le tracé initial
        GeoJSONStr = client.service.compute_travel(startRes[2], startRes[1], endRes[2], endRes[1])
        GeoJSON = json.loads(GeoJSONStr)

        # Extraction des points du chemin
        listePtsChemin = []
        # Note: ORS renvoie [Lon, Lat], on stocke [Lat, Lon]
        for lon, lat in GeoJSON["features"][0]["geometry"]["coordinates"]:
            listePtsChemin.append([lat, lon])

        # --- 4. Algorithme de recherche de bornes ---
        autonomieRestante = autonomieTot
        bornes_trouvees = []  # Liste pour stocker les infos des bornes
        totalChargeSeconds = 0

        for i in range(len(listePtsChemin) - 1):
            p1_lat, p1_lon = listePtsChemin[i]
            p2_lat, p2_lon = listePtsChemin[i + 1]

            dist_segment = haversine_distance(p1_lat, p1_lon, p2_lat, p2_lon)

            # Si batterie faible (< 10km)
            if autonomieRestante - dist_segment < 10:
                try:
                    # Recherche SOAP d'une borne à 10km
                    res_json = client.service.near_charging(p1_lon, p1_lat, "10")
                    data_bornes = json.loads(res_json)

                    next_station = None
                    if "results" in data_bornes and len(data_bornes["results"]) > 0:
                        next_station = data_bornes["results"][0]

                    # Si échec, tentative à 30km
                    if not next_station:
                        res_json = client.service.near_charging(p1_lon, p1_lat, "30km")
                        data_bornes = json.loads(res_json)
                        if "results" in data_bornes and len(data_bornes["results"]) > 0:
                            next_station = data_bornes["results"][0]

                    if next_station:
                        # On stocke la borne trouvée
                        borne_info = {
                            "nom": next_station.get("n_station", "Borne inconnue"),
                            "latitude": next_station["ylatitude"],
                            "longitude": next_station["xlongitude"],
                            "puissance": next_station["puiss_max"]
                        }
                        bornes_trouvees.append(borne_info)

                        # Calcul temps de charge
                        pourcentRestant = max(autonomieRestante, 0) / autonomieTot
                        pourcentNecessaire = 0.80 - pourcentRestant

                        if pourcentNecessaire > 0:
                            temps_charge_h = (autonomieTotkWh * pourcentNecessaire) / (next_station["puiss_max"] * 0.9)
                            totalChargeSeconds += temps_charge_h * 3600
                            autonomieRestante += (autonomieTot * pourcentNecessaire)

                except Exception as e:
                    print(f"[API ERROR] Erreur recherche borne: {e}")
                    # On continue pour ne pas planter l'API, mais sans ajouter de borne

            autonomieRestante -= dist_segment

        # --- 5. Finalisation des totaux ---
        segments = GeoJSON["features"][0]["properties"]["segments"]
        totalDrivingSeconds = sum(seg["duration"] for seg in segments)
        totalDistanceMeters = sum(seg["distance"] for seg in segments)

        totalSeconds = totalDrivingSeconds + totalChargeSeconds
        dist_km = totalDistanceMeters / 1000

        def format_time(seconds):
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            return f"{h}h {m}min"

        # --- 6. Construction de la réponse JSON ---
        response = {
            "trajet": {
                "depart": {"adresse": startRes[0], "lat": startRes[1], "lng": startRes[2]},
                "arrivee": {"adresse": endRes[0], "lat": endRes[1], "lng": endRes[2]},
                "distance_km": round(dist_km, 2),
                "temps_total_str": format_time(totalSeconds),
                "temps_conduite_str": format_time(totalDrivingSeconds),
                "temps_recharge_str": format_time(totalChargeSeconds),
                "nb_arrets": len(bornes_trouvees)
            },
            "bornes_recharge": bornes_trouvees,
            "vehicule": {
                "id": target_id,
                "modele": f"{v['naming']['make']} {v['naming']['model']}",
                "autonomie_theorique": autonomieTot
            }
        }

        return jsonify(response)

    except Exception as e:
        print(f"[API CRITICAL ERROR] {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)