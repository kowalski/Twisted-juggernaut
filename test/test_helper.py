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
    def __init__(self, onRequest):
        self.onRequest = onRequest
        
    def render_POST(self, request):
        self.onRequest.callback(request)
        return server.NOT_DONE_YET

class MockWebServer:
    def __init__(self):
        resource = RootResource()
        self.onRequest = defer.Deferred()
        resource.putChild('subscribe', ChildResource(self.onRequest))
        resource.putChild('disconnected', ChildResource(self.onRequest))
        resource.putChild('logged_out', ChildResource(self.onRequest))
        self.site = server.Site(resource)
        self.connector = reactor.listenTCP(8080, self.site)

def errorHandler(a):
    log.err(str(a))