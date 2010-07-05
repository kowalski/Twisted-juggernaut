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
        
    def testManySubscribers(self):
        self.webServer.giveOnly200()
        
        def sendMsg(client, id, channels):
            client.connector.transport.write(client.subscribeMessage(id, channels))
        client1 = MockFlashClient()
        client2 = MockFlashClient()
        client3 = MockFlashClient()
        client1.connectedEvent.addCallback(lambda _: sendMsg(client1, 1, [1]))
        client2.connectedEvent.addCallback(lambda _: sendMsg(client2, 2, [1]))
        client3.connectedEvent.addCallback(lambda _: sendMsg(client3, 3, [2]))
        
        def assertsOnService():
            self.assertEqual(len(self.service.channels.keys()), 2)
            self.assertEqual(len(self.service.channels[1]), 2)
            self.assertEqual(len(self.service.channels[2]), 1)
        task.deferLater(reactor, 0.05, assertsOnService
            ).addCallback(lambda _: client1.connector.disconnect()
            ).addCallback(lambda _: client2.connector.disconnect()
            ).addCallback(lambda _: client3.connector.disconnect())
            
        return defer.DeferredList([client1.disconnectedEvent, client2.disconnectedEvent, client3.disconnectedEvent])