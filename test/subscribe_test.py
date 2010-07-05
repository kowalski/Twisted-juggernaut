from twisted.trial import unittest
from twisted.python import log
from twisted.internet import protocol, defer
from twisted.internet import reactor
import juggernaut

class ClientProtocol(protocol.Protocol):
    def connectionMade(self):
        self.factory.onConnectionMade.callback(self)

    def connectionLost(self, *a):
        self.factory.onConnectionLost.callback(self)

class SubscribeTest(unittest.TestCase):
    test_config = {
        'port': 5001,
        'subscription_url': 'http://localhost:3000/juggernaut/subscribe',
        'allowed_ips': ['127.0.0.1'],
        'logout_connection_url': 'http://localhost:3000/juggernaut/disconnected',
        'logout_url': 'http://localhost:3000/juggernaut/logged_out'
    }
    
    def setUp(self):
        self.service = juggernaut.makeService(self.test_config)
        factory = juggernaut.IJuggernautFactory(self.service)
        self.listening_port = reactor.listenTCP(self.test_config['port'], factory)
        
    def tearDown(self):
        return self.listening_port.stopListening()

    def _connectClient(self, d1, d2):
        factory = protocol.ClientFactory()
        factory.protocol = ClientProtocol
        factory.onConnectionMade = d1
        factory.onConnectionLost = d2
        return reactor.connectTCP('localhost', self.test_config['port'], factory)
    
    def testConnect(self):
        connectedEvent = defer.Deferred()
        disconnectedEvent = defer.Deferred()
        client = self._connectClient(connectedEvent, disconnectedEvent)
        
        def sendMsg(a):
            client.transport.write('czesc\0')
        connectedEvent.addCallback(sendMsg)
        
        return disconnectedEvent
        
