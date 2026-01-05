import json
import os
from dotenv import load_dotenv
from wsgiref.simple_server import make_server
from spyne import Application, rpc, ServiceBase, Integer, Iterable, Unicode, Float, String
from spyne.protocol.soap import Soap11
from spyne.server.wsgi import WsgiApplication
import math
import requests

# Si on travaille en local, on load les clés API du .env
if os.path.exists(".env"):
    load_dotenv()

OpenRteSce_API_KEY = os.getenv("OPEN_ROUTE_SERVICE_KEY")
OpenCage_API_KEY = os.getenv("OPEN_CAGE_API_KEY")
GRAPHQL_QUERY = """
query vehicleList {
  vehicleList(size: 10, page: 0) {
    id
    naming {
      make
      model
      version
    }
    connectors {
      standard
      power
      time
      charge_speed
    }
    adapters {
      standard
      power
      time
      charge_speed
    }
    battery {
      usable_kwh
    }
    range {
      chargetrip_range {
        best
        worst
      }
    }
    media {
      image {
        id
        type
        url
        height
        width
        thumbnail_url
        thumbnail_height
        thumbnail_width
      }
      make {
        id
        type
        url
        height
        width
        thumbnail_url
        thumbnail_height
        thumbnail_width
      }
    }
    routing {
      fast_charging_support
    }
  }
}
        """

class NearChargingStations(ServiceBase):
    @rpc(Float, Float, String, _returns=Unicode)
    def near_charging(ctx, long, lat, radius):
        """
            Recherche la borne de recharge la plus proche autour de coordonnées données.

            Args:
                long (float): Longitude du point de recherche.
                lat (float): Latitude du point de recherche.
                radius (str): Rayon de recherche (ex: "10" ou "10km").

            Returns:
                str: Chaîne JSON contenant les détails de la borne trouvée (API OpenDataSoft).
            """
        # Conversion initiale
        long = float(long)
        lat = float(lat)
        try:
            radius = int(radius)
        except:
            radius = 10  # Valeur par défaut si erreur de conversion

        url = "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/bornes-irve/records?limit=1&where=within_distance(geo_point_borne,geom'POINT({long} {lat})', {radius}km)&order_by=puiss_max DESC"

        # Initialisation des variables de contrôle
        current_count = 0
        protection = 0
        final_text_response = "{}"  # Pour stocker le résultat final

        while current_count == 0 and protection < 10:
            requestUrl = url.format(long=long, lat=lat, radius=radius)
            payload = {};
            headers = {}

            print("[DEBUG] Req url = %s" % requestUrl)

            # 1. On stocke l'objet réponse dans une variable distincte 'r'
            r = requests.request("GET", requestUrl, headers=headers, data=payload)

            # 2. On sauvegarde le texte pour le retour de la fonction
            final_text_response = r.text

            # 3. On convertit en JSON pour vérifier la condition de sortie
            try:
                data = r.json()
                current_count = data.get("total_count", 0)
            except:
                current_count = 0  # Si le JSON est invalide, on continue

            if current_count == 0:
                print("[DEBUG] No station found, expanding radius...")
                radius += 5
                protection += 1

        return final_text_response

class forwardGeocoding(ServiceBase):
    @rpc(String, _returns=Iterable(Unicode))
    def forward(ctx, name):
        """
            Convertit une adresse textuelle en coordonnées INFOS.md (Géocodage).

            Args:
                name (str): Adresse ou nom de ville à géocoder.

            Returns:
                list[str]: Liste contenant [Adresse formatée, Latitude, Longitude].
            """
        url="https://api.opencagedata.com/geocode/v1/json?key={key}&q={name}&limit=3&pretty=1"
        payload={};headers = {}
        requestUrl = url.format(key=OpenCage_API_KEY, name=name)

        print("[DEBUG] Req  url = %s" % requestUrl)
        response = requests.request("GET", requestUrl, headers=headers, data=payload)
        response = response.json()
        formattedResponse = [str(response["results"][0]["formatted"]),str(response["results"][0]["geometry"]["lat"]), str(response["results"][0]["geometry"]["lng"])]
        return formattedResponse

class computeTravel(ServiceBase):
    @rpc(Float, Float, Float, Float, _returns=Unicode)
    def compute_travel(ctx, startPosLat, startPosLng, endPosLat, endPosLng):
        """
            Récupère la géométrie d'un trajet simple entre deux points.

            Args:
                startPosLat (float): Latitude de départ.
                startPosLng (float): Longitude de départ.
                endPosLat (float): Latitude d'arrivée.
                endPosLng (float): Longitude d'arrivée.

            Returns:
                str: Chaîne GeoJSON brute de l'itinéraire (API OpenRouteService).
            """
        requestUrl = f"https://api.openrouteservice.org/v2/directions/driving-car?api_key={OpenRteSce_API_KEY}&start={startPosLat},{startPosLng}&end={endPosLat},{endPosLng}"
        payload = {};headers = {}
        print("[DEBUG] Req  url = %s" % requestUrl)
        response = requests.request("GET", requestUrl, headers=headers, data=payload)
        return response.text

class computeTravelProfiled(ServiceBase):
    @rpc(Unicode, _returns=Unicode)
    def compute_travel_profiled(ctx, coordJson):
        """
            Calcule un itinéraire précis passant par une liste ordonnée de points (bornes).

            Args:
                coordJson (str): Chaîne JSON représentant une liste de coordonnées [[lon, lat], ...].

            Returns:
                str: Chaîne GeoJSON brute de l'itinéraire complet (API OpenRouteService).
            """
        coords = json.loads(coordJson)
        requestUrl = f"https://api.openrouteservice.org/v2/directions/driving-car/geojson?api_key={OpenRteSce_API_KEY}"
        payload = {"coordinates":coords};headers = {"Content-Type": "application/json"}
        print("[DEBUG] Req  url = %s" % requestUrl)
        response = requests.request("POST", requestUrl, headers=headers, json=payload)
        return response.text

class getVehiculeList(ServiceBase):
    @rpc(_returns=Unicode)
    def get_vehicule_list(ctx):
        """
            Récupère la liste des véhicules électriques et leurs détails techniques.

            Args:
                None: Pas d'arguments d'entrée.

            Returns:
                str: Chaîne JSON contenant la liste des véhicules (API GraphQL Chargetrip).
            """
        requestUrl = "https://api.chargetrip.io/graphql"
        payload = {"query": GRAPHQL_QUERY}
        headers = {
            'x-client-id': os.getenv("CHARGETRIP_CLIENT_ID"),
            'x-app-id': os.getenv("CHARGETRIP_APP_ID")}
        response = requests.request("POST", requestUrl, headers=headers, data=payload)
        return response.text

application = Application(
    [NearChargingStations, forwardGeocoding, computeTravel, getVehiculeList, computeTravelProfiled],
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