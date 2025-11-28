from wsgiref.simple_server import make_server
from spyne import Application, rpc, ServiceBase, Integer, Iterable, Unicode
from spyne.protocol.soap import Soap11
from spyne.server.wsgi import WsgiApplication
import math

class ComputeTravelTime(ServiceBase):
    @rpc(float, float, float, _returns=float)      #Déclaration de fonction SOAP
    def compute(ctx, distance, evRange, chargeTime):
        arrets = max(math.ceil(distance / evRange) - 1, 0)
        vitesse_moy = 80
        temps_trajet = (distance / vitesse_moy) + arrets * chargeTime
        return temps_trajet

application = Application(
    [ComputeTravelTime],            # Liste des services exposés
    'localhost/travel',        # Namespace du service
    in_protocol=Soap11(validator='lxml'),   # Protocole SOAP en entrée
    out_protocol=Soap11())                   # Protocole SOAP en sortie
wsgi_application = WsgiApplication(application)


if __name__ == '__main__':
    host="127.0.0.1"
    port=8000
    print("Serveur SOAP en cours d'exécution sur http://"+host+":"+str(port))
    server = make_server(host, port, wsgi_application)
    server.serve_forever()