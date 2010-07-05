from twisted.trial import unittest
from twisted.python import log
from twisted.internet import protocol, defer, task, reactor
import juggernaut

import sys
sys.path.append('test')
from test_helper import *

class SubscribeTest(unittest.TestCase):
    timeout = 5
    
    def setUp(self):
        self.service = juggernaut.makeService(TestConfig.config)
        factory = juggernaut.IJuggernautFactory(self.service)
        self.listeningPort = reactor.listenTCP(TestConfig.config['port'], factory)
        
        self.webServer = MockWebServer()
        
    def tearDown(self):
        return defer.DeferredList([self.listeningPort.stopListening(), self.webServer.connector.stopListening()])

    def testNonJsonDissconnects(self):
        client = MockFlashClient()
        
        def sendMsg(a):
            client.connector.transport.write('czesc\0')
        client.connectedEvent.addCallback(sendMsg)
        
        return client.disconnectedEvent
        
    def testSubscribeSuccessful(self):
        client = MockFlashClient()
        
        def sendMsg(a):
            client.connector.transport.write(client.subscribeMessage(1))
        defer1 = client.connectedEvent.addCallback(sendMsg).addErrback(errorHandler)
        
        def onRequest(request):
            self.assertEqual(request.content.read(), "client_id=1&session_id=1&channels[]=1")
            self.assertEqual(request.prePathURL().split('/')[-1], 'subscribe')
            request.finish()
        defer2 = self.webServer.onRequest.addCallback(onRequest).addErrback(errorHandler)
        
        def assertsOnService():
            self.assertEqual(len(self.service.channels.keys()), 1)
            self.assertEqual(len(self.service.channels[1]), 1)
        task.deferLater(reactor, 0.05, assertsOnService
            ).addCallback(lambda _: client.connector.disconnect())
            
        return client.disconnectedEvent
        
    def testSubscribeDisconnectsWhenCodeNot200(self):
        client = MockFlashClient()
        
        def sendMsg(a):
            client.connector.transport.write(client.subscribeMessage(1))
        defer1 = client.connectedEvent.addCallback(sendMsg).addErrback(errorHandler)
        
        def onRequest(request):
            self.assertEqual(request.content.read(), "client_id=1&session_id=1&channels[]=1")
            self.assertEqual(request.prePathURL().split('/')[-1], 'subscribe')
            request.setResponseCode(409)
            request.finish()
        defer2 = self.webServer.onRequest.addCallback(onRequest).addErrback(errorHandler)
        
        return client.disconnectedEvent
        