from flask import Flask, render_template, request
import folium
import zeep
import json
import math
import os
app = Flask(__name__)

# APIZeep définition du Sce Web
# Si la variable existe (sur Azure), on l'utilise, sinon on prend localhost (sur votre PC)
wsdl_url = os.environ.get('SOAP_URL', 'http://127.0.0.1:8000')
wsdl = f'{wsdl_url}/?wsdl'
client = zeep.Client(wsdl=wsdl)
#wsdl = 'http://127.0.0.1:8000/?wsdl'
#client = zeep.Client(wsdl=wsdl)


def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calcule la distance entre deux points GPS en km en utilisant la formule de Haversine
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
    result = client.service.get_vehicule_list()
    print(result)


@app.route("/compute", methods=['GET', 'POST'])  # Render de l'index avec calcul
def compute():
    try:
        distance = request.form['distance']
        evRange = request.form['evRange']
        chargeTime = request.form['chargeTime']
        print("[DEBUG] Variables récupérées : distance=" + str(distance) + ", evRange=" + str(
            evRange) + ", chargeTime=" + str(chargeTime))
        result = client.service.compute(distance, evRange, chargeTime)  # Requêtage du Sce Web avec APIZeep
        print("[DEBUG] Résultat: " + str(result))
        return render_template("travelTimeForm.html", resultat=result)

    except Exception as e:  # Affichage de l'erreur en cas d'erreur
        return render_template("travelTimeForm.html", erreur=str(e))


@app.route("/")
def components():
    """Extract map components and put those on a page."""
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
        # Attention : GeoJSON est en [Lon, Lat], votre code inverse pour avoir [Lat, Lon] dans listePtsChemin
        for lon, lat in GeoJSON["features"][0]["geometry"]["coordinates"]:
            listePtsChemin.append([lat, lon])

        print("[DEBUG] Computed listePtsChemin! Size: " + str(len(listePtsChemin)))

        # ---        Recalcul de l'itinéraire pour prendre en compte les bornes      ---#
        distance_parcourue = 0
        coordonneesBornes.append([float(forwardStartResult[2]), float(forwardStartResult[1])])
        print("[DEBUG] Begin computing logic based on geometry points...")

        # On itère point par point sur la ligne tracée (Geometry) au lieu des steps
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
                        p1_lon,  # Attention l'API attend souvent Longitude, Latitude
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

            # Optionnel : Arrêter de chercher si on est très proche de la fin pour éviter une charge à 2km de l'arrivée
            # if distance_parcourue > (total_distance_estimee - 10): break



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


if __name__ == "__main__":
    app.run(debug=True)