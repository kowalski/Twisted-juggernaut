from twisted.internet import protocol, defer
from twisted.internet import reactor
from twisted.web import resource, server
import juggernaut
from twisted.python import log

import json

class TestConfig:
    config = {
        'host': 'localhost',
        'port': 5001,
        'allowed_ips': ['127.0.0.1'],
        'subscription_url': 'http://localhost:8080/subscribe',
        'logout_connection_url': 'http://localhost:8080/disconnected',
        'logout_url': 'http://localhost:8080/logged_out'
    }

class ClientProtocol(protocol.Protocol):
    def connectionMade(self):
        self.factory.onConnectionMade.callback(self)

    def connectionLost(self, *a):
        self.factory.onConnectionLost.callback(self)

class MockFlashClient:
    def __init__(self, host=TestConfig.config['host'], port=TestConfig.config['port']):
        factory = protocol.ClientFactory()
        factory.protocol = ClientProtocol
        self.connectedEvent = defer.Deferred()
        self.disconnectedEvent = defer.Deferred()
        factory.onConnectionMade = self.connectedEvent 
        factory.onConnectionLost = self.disconnectedEvent 
        self.connector = reactor.connectTCP(host, port, factory)
        
    def subscribeMessage(self, id, channels=[1]):
        handshake = {
            'command': 'subscribe',
            'session_id': id,
            'client_id': id,
            'channels': channels
        }
        return json.dumps(handshake) + "\0"
        
class RootResource(resource.Resource):
    pass

class ChildResource(resource.Resource):
    def __init__(self, webserver):
        self.webserver = webserver
        
    def render_POST(self, request):
        if self.webserver.return200s:
            return ""
        self.webserver.onRequest.callback(request)
        return server.NOT_DONE_YET

class MockWebServer:
    def __init__(self):
        resource = RootResource()
        self.onRequest = defer.Deferred()
        resource.putChild('subscribe', ChildResource(self))
        resource.putChild('disconnected', ChildResource(self))
        resource.putChild('logged_out', ChildResource(self))
        self.site = server.Site(resource)
        self.connector = reactor.listenTCP(8080, self.site)
        self.return200s = False

    def giveOnly200(self):
        self.return200s = True
        
def errorHandler(a):
    log.err(str(a))