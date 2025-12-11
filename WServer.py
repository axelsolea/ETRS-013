from flask import Flask, render_template, request
import folium
import zeep
app = Flask(__name__)

#APIZeep définition du Sce Web
wsdl = 'http://127.0.0.1:8000/?wsdl'
client = zeep.Client(wsdl=wsdl)

@app.route("/") #Render de l'index
def index():
    return render_template('travelTimeForm.html')

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


if __name__ == "__main__":
    app.run(debug=True)


