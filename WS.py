import json
from wsgiref.simple_server import make_server
from spyne import Application, rpc, ServiceBase, Integer, Iterable, Unicode, Float, String
from spyne.protocol.soap import Soap11
from spyne.server.wsgi import WsgiApplication
import math
import requests

OpenRteSce_API_KEY = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjBhYTQ4MWRiYzJjMzQ5NWRiYzhhZTEyOGM4ZDZhNGM5IiwiaCI6Im11cm11cjY0In0="
OpenCage_API_KEY = "91f9a68a0eb04dd492e16b64e74faca0"

class ComputeTravelTime(ServiceBase):
    @rpc(float, float, float, _returns=float)      #Déclaration de fonction SOAP
    def compute(ctx, distance, evRange, chargeTime):
        arrets = max(math.ceil(distance / evRange) - 1, 0)
        vitesse_moy = 80
        temps_trajet = (distance / vitesse_moy) + arrets * chargeTime
        return temps_trajet

class NearChargingStations(ServiceBase):
    @rpc(Float, Float, Integer, _returns=Iterable(str))
    def near_charging(ctx, long, lat, radius):
        url = "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/bornes-irve/records?limit=5&where=within_distance(geo_point_borne,geom'POINT({long} {lat})', {radius})"
        long = float(long)
        lat = float(lat)
        radius = int(radius)
        requestUrl = url.format(long=long, lat=lat, radius=radius)
        payload = {};headers = {}
        print("[DEBUG] Req  url = %s" % requestUrl)
        response = requests.request("GET", requestUrl, headers=headers, data=payload)
        return response.text

class forwardGeocoding(ServiceBase):
    @rpc(String, _returns=Iterable(Unicode))
    def forward(ctx, name):
        url="https://api.opencagedata.com/geocode/v1/json?key={key}&q={name}&limit=3&pretty=1"
        payload={};headers = {}
        requestUrl = url.format(key=OpenCage_API_KEY, name=name)

        print("[DEBUG] Req  url = %s" % requestUrl)
        response = requests.request("GET", requestUrl, headers=headers, data=payload)
        response = response.json()
        formattedResponse = [str(response["results"][0]["formatted"]),str(response["results"][0]["geometry"]["lat"]), str(response["results"][0]["geometry"]["lng"])]
        return formattedResponse


application = Application(
    [ComputeTravelTime, NearChargingStations, forwardGeocoding],            # Liste des services exposés
    'localhost/travel',                 # Namespace du service
    in_protocol=Soap11(validator='lxml'),   # Protocole SOAP en entrée
    out_protocol=Soap11())                   # Protocole SOAP en sortie
wsgi_application = WsgiApplication(application)


if __name__ == '__main__':
    host="127.0.0.1"
    port=8000
    print("Serveur SOAP en cours d'exécution sur http://"+host+":"+str(port))
    server = make_server(host, port, wsgi_application)
    server.serve_forever()