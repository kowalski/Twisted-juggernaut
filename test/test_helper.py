from twisted.trial import unittest
from twisted.internet import protocol, defer
from twisted.internet import reactor
from twisted.web import resource, server
import juggernaut
from twisted.python import log
from twisted.trial.unittest import FailTest

import json, re

class JuggernautTest(unittest.TestCase):
    timeout = 5
    
    def setUp(self):
        self.config = dict(TestConfig.config)
        self.service = juggernaut.makeService(self.config)
        factory = juggernaut.IJuggernautFactory(self.service)
        self.listeningPort = reactor.listenTCP(self.config['port'], factory)
        
        self.webServer = MockWebServer()
        
    def tearDown(self):
        d = self.webServer.getAllRequests(
            ).addCallback(self.listeningPort.stopListening
            ).addCallback(self.webServer.connector.stopListening)
        return d


class TestConfig:
    config = {
        'host': 'localhost',
        'port': 5001,
        'allowed_ips': ['127.0.0.1'],
        'subscription_url': 'http://localhost:8080/subscribe',
        'logout_connection_url': 'http://localhost:8080/disconnected',
        'logout_url': 'http://localhost:8080/logged_out',
        'timeout': 0.02
    }

class ClientProtocol(protocol.Protocol):
    CR = "\0"
    CR_END = re.compile(CR + '$')
    
    def __init__(self):
        self.buffer = ""
        self.messages = []
        
    def dataReceived(self, data):
        self.buffer += data
        split = self.buffer.split(self.CR)
        
        if not self.CR_END.match(self.buffer):
            self.buffer = split.pop()
    
        for message in split:
            self.messages.append(message)
        
    def connectionMade(self):
        self.factory.onConnectionMade.callback(self)

    def connectionLost(self, *a):
        self.factory.onConnectionLost.callback(self)
        

class MockFlashClient:
    def __init__(self, client_id=None):
        factory = protocol.ClientFactory()
        factory.protocol = ClientProtocol
        self.connectedEvent = defer.Deferred()
        self.disconnectedEvent = defer.Deferred()
        factory.onConnectionMade = self.connectedEvent 
        factory.onConnectionLost = self.disconnectedEvent 
        self.connector = reactor.connectTCP(TestConfig.config['host'], TestConfig.config['port'], factory)
        
        self.id = client_id
        
    def subscribeMessage(self, id, channels=[1]):
        handshake = {
            'command': 'subscribe',
            'session_id': id,
            'client_id': id,
            'channels': channels
        }
        return json.dumps(handshake) + "\0"
    
    def sendSubscribeMessage(self, channels=[1]):
        self.connector.transport.write(self.subscribeMessage(self.id, channels))
        
    def broadcastToChannelsMessage(self, body, channels):
        payload = {
            'command': 'broadcast',
            'type': 'to_channels',
            'channels': channels,
            'body': body
        }
        return json.dumps(payload) + "\0"
        
    def sendBroadcastToChannelsMessage(self, body, channels):
        self.connector.transport.write(self.broadcastToChannelsMessage(body, channels))
        
    def broadcastToClientsMessage(self, body, clients):
        payload = {
            'command': 'broadcast',
            'type': 'to_clients',
            'client_ids': clients,
            'body': body
        }
        return json.dumps(payload) + "\0"
        
    def sendBroadcastToClientsMessage(self, body, clients):
        self.connector.transport.write(self.broadcastToClientsMessage(body, clients))
    
        
class ChildResource(resource.Resource):
    def __init__(self, webserver):
        self.webserver = webserver
        
    def render_POST(self, request):
        if self.webserver.counter >= len(self.webserver.deferList):
            raise FailTest("Request not expected %s!" % str(request))
        self.webserver.requests.append(request)
        
        def defaultHandler((r, c)):
            request.finish()
        handler = self.webserver.requestHandler or defaultHandler
        
        d = self.webserver.deferList[self.webserver.counter]
        d.addCallback(handler).addErrback(errorHandler)
        d.callback((request, self.webserver.counter))
        
        self.webserver.counter += 1
        
        return server.NOT_DONE_YET

class MockWebServer:
    def __init__(self):
        res = resource.Resource()
        self.requestHandler = None
        res.putChild('subscribe', ChildResource(self))
        res.putChild('disconnected', ChildResource(self))
        res.putChild('logged_out', ChildResource(self))
        self.site = server.Site(res)
        self.connector = reactor.listenTCP(8080, self.site)
        
        self.return200s = False
        self.counter = 0
        self.deferList = []
        self.requests = []

    def expectRequests(self, num):
        self.deferList = map(lambda _: defer.Deferred(), range(num))
        
    def getAllRequests(self):
        return self.getNFirstRequests(len(self.deferList))

    def getNFirstRequests(self, num):
        return defer.DeferredList(self.deferList[0:num])
    
def errorHandler(a):
    log.err(str(a))