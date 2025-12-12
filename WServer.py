from flask import Flask, render_template, request
import folium
import zeep
import json
app = Flask(__name__)

#APIZeep définition du Sce Web
wsdl = 'http://127.0.0.1:8000/?wsdl'
client = zeep.Client(wsdl=wsdl)

@app.route("/vehicules", methods=['GET','POST'])
def vehicules():
    result = client.service.get_vehicule_list()
    print(result)

@app.route("/compute", methods=['GET','POST']) #Render de l'index avec calcul
def compute():
    try:
        distance = request.form['distance']
        evRange = request.form['evRange']
        chargeTime = request.form['chargeTime']
        print("[DEBUG] Variables récupérées : distance=" + str(distance) + ", evRange=" + str(evRange) + ", chargeTime=" + str(chargeTime))
        result = client.service.compute(distance, evRange, chargeTime) #Requêtage du Sce Web avec APIZeep
        print("[DEBUG] Résultat: " + str(result))
        return render_template("travelTimeForm.html", resultat=result)

    except Exception as e: #Affichage de l'erreur en cas d'erreur
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
    return render_template("index.html", header=header, body_html=body_html, folium_script=script, vehicules=vehicule_options)

@app.route("/computeTravel", methods=['GET','POST'])
def componentsCompute():
    try:
        """Extract map components and put those on a page."""
        m = folium.Map(
            width=800,
            height=600,
        )
        #Form values
        start=request.form['start']
        end=request.form['end']

        #Forward result format : ["formatted address","latitude","longitude"]
        forwardStartResult = client.service.forward(start)
        forwardEndResult = client.service.forward(end)

        GeoJSONStr = client.service.compute_travel(
            forwardStartResult[2],
            forwardStartResult[1],
            forwardEndResult[2],
            forwardEndResult[1]
        )
        GeoJSON = json.loads(GeoJSONStr)
        # Tracé du chemin
        listePtsChemin = []
        for lat, lng in GeoJSON["features"][0]["geometry"]["coordinates"]:
            listePtsChemin.append((lng, lat))
        print(listePtsChemin)
        folium.PolyLine(listePtsChemin, tooltip="Itinéraire").add_to(m)

        #Marqueur origine
        folium.Marker(
            location=[forwardStartResult[1],forwardStartResult[2]],
            tooltip="Click me!",
            popup=forwardStartResult[0], #ADRESSE SOURCE
            icon=folium.Icon(color="green"),
        ).add_to(m)

        #Marqueur destination
        folium.Marker(
            location=[forwardEndResult[1],forwardEndResult[2]],
            tooltip="Click me!",
            popup=forwardEndResult[0],  #ADRESSE DEST
            icon=folium.Icon(color="red"),
        ).add_to(m)

        #Zoom auto & limites de carte
        south_west = [min(forwardStartResult[1], forwardEndResult[1]), min(forwardStartResult[2], forwardEndResult[2])]
        north_east = [max(forwardStartResult[1], forwardEndResult[1]), max(forwardStartResult[2], forwardEndResult[2])]
        m.fit_bounds([south_west, north_east])

        #Rendu de la carte
        m.get_root().render()
        header = m.get_root().header.render()
        body_html = m.get_root().html.render()
        script = m.get_root().script.render()
        print(script)
        return render_template("index.html", header=header, body_html=body_html, folium_script=script)

    except Exception as e: #Affichage de l'erreur en cas d'erreur
        return render_template("index.html", erreur=str(e))


if __name__ == "__main__":
    app.run(debug=True)


