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
        d = self.webServer.getAllRequests().addCallback(self.listeningPort.stopListening
            ).addCallback(self.webServer.connector.stopListening)
        return d

    def testNonJsonDissconnects(self):
        client = MockFlashClient()
        
        def sendMsg(a):
            client.connector.transport.write('czesc\0')
        client.connectedEvent.addCallback(sendMsg)
        
        return client.disconnectedEvent
        
    def testSubscribeSuccessful(self):
        self.webServer.expectRequests(3)
        def onRequest((r, c)):
            if c == 0:
                self.assertEqual(r.content.read(), "client_id=1&session_id=1&channels[]=1")
                self.assertEqual(r.prePathURL().split('/')[-1], 'subscribe')
            elif c == 1:
                self.assertEqual(r.content.read(), "client_id=1&session_id=1&channels[]=1")
                self.assertEqual(r.prePathURL().split('/')[-1], 'disconnected')
            r.finish()
        self.webServer.requestHandler = onRequest
        
        client = MockFlashClient()
        defer1 = client.connectedEvent.addCallback(lambda _: client.sendSubscribeMessage(1)).addErrback(errorHandler)
        
        def assertsOnService(*a):
            self.assertEqual(len(self.service.channels.keys()), 1)
            self.assertEqual(len(self.service.channels[1]), 1)
        task.deferLater(reactor, 0.05, assertsOnService
            ).addCallback(lambda _: client.connector.disconnect())
            
        return client.disconnectedEvent
        
    def testSubscribeDisconnectsWhenCodeNot200(self):
        self.webServer.expectRequests(2)
        client = MockFlashClient()
        
        defer1 = client.connectedEvent.addCallback(lambda _: client.sendSubscribeMessage(1)).addErrback(errorHandler)
        
        def onRequest((request, counter)):
            if counter == 0:
                self.assertEqual(request.content.read(), "client_id=1&session_id=1&channels[]=1")
                self.assertEqual(request.prePathURL().split('/')[-1], 'subscribe')
                request.setResponseCode(409)
            else:
                request.setResponseCode(200)
            request.finish()
        self.webServer.requestHandler = onRequest
        
        return client.disconnectedEvent
        
    def testManySubscribers(self):
        """Subscribe 3 clients, expects 9 reqeusts 3x subscribe, 3x disconnect, 3x logged_out
        Check that service records correct data at each step"""
        self.webServer.expectRequests(9)
        
        client1 = MockFlashClient()
        client2 = MockFlashClient()
        client3 = MockFlashClient()
        client1.connectedEvent.addCallback(lambda _: client1.sendSubscribeMessage(1, [1]))
        client2.connectedEvent.addCallback(lambda _: client2.sendSubscribeMessage(2, [1]))
        client3.connectedEvent.addCallback(lambda _: client3.sendSubscribeMessage(3, [2]))
        
        def assertsOnService(*a):
            self.assertEqual(len(self.service.channels.keys()), 2)
            self.assertEqual(len(self.service.channels[1]), 2)
            self.assertEqual(len(self.service.channels[2]), 1)
            self.assertEqual(len(self.service.clients.keys()), 3)
            self.assertEqual(self.service.clients.keys(), [1, 2, 3])
        task.deferLater(reactor, 0.05, assertsOnService
            ).addCallback(lambda _: client1.connector.disconnect()
            ).addCallback(lambda _: client2.connector.disconnect()
            ).addCallback(lambda _: client3.connector.disconnect())

        def assertClientsDead(*a):
            for channel in self.service.channels.values():
                for client in channel:
                    self.assertFalse(client.is_alive)
        self.webServer.getNFirstRequests(6).addCallback(assertsOnService #clients are not removed from channels yet, only marked as dead
            ).addCallback(assertClientsDead)
            
        def assertClientsRemoved(*a):
            self.assertEqual(len(self.service.channels.keys()), 0)
            self.assertEqual(len(self.service.clients.keys()), 0)
        self.webServer.getAllRequests().addCallback(assertClientsRemoved)
        return defer.DeferredList([client1.disconnectedEvent, client2.disconnectedEvent, client3.disconnectedEvent])
                
    def testIdIsUnique(self):
        self.webServer.expectRequests(3)
        
        client1 = MockFlashClient()
        client2 = MockFlashClient()
        client1.connectedEvent.addCallback(lambda _: client1.sendSubscribeMessage(1, [1]))
        task.deferLater(reactor, 0.01, client2.sendSubscribeMessage, 1, [2]) # make sure this message is handled second 
        
        def assertsOnService(*a):
            self.assertEqual(len(self.service.channels.keys()), 1)
            self.assertEqual(len(self.service.channels[1]), 1)
            self.assertEqual(len(self.service.clients.keys()), 1)
            self.assertEqual(self.service.clients.keys(), [1])
        task.deferLater(reactor, 0.05, assertsOnService
            ).addCallback(lambda _: client1.connector.disconnect()
            ).addCallback(lambda _: client2.connector.disconnect())
        
        return defer.DeferredList([client1.disconnectedEvent, client2.disconnectedEvent])
        
    def testReconnectDoesntSendLogout(self):
        self.webServer.expectRequests(5)
        
        def onRequest((request, counter)):
            expectations = [ 'subscribe', 'disconnected', 'subscribe', 'disconnected', 'logged_out' ]
            self.assertEqual(request.prePathURL().split('/')[-1], expectations[counter], "Counter %d" % counter)
            request.setResponseCode(200)
            request.finish()
        self.webServer.requestHandler = onRequest
        
        first_client = MockFlashClient()
        reconnecting_client = MockFlashClient()
        def connectAnotherClient(client):
            client.connectedEvent.addCallback(lambda _: client.sendSubscribeMessage(1, [1]))
            task.deferLater(reactor, 0.02, client.connector.disconnect)
        
        first_client.connectedEvent.addCallback(lambda _: first_client.sendSubscribeMessage(1, [1]))
        reactor.callLater(0.02, first_client.connector.disconnect)
        reactor.callLater(0.03, connectAnotherClient, reconnecting_client)
        
        return reconnecting_client.disconnectedEvent
        
    def testReconnectAfterTheTimeout(self):
        self.webServer.expectRequests(6)
        
        def onRequest((request, counter)):
            expectations = [ 'subscribe', 'disconnected', 'logged_out', 'subscribe', 'disconnected', 'logged_out' ]
            self.assertEqual(request.prePathURL().split('/')[-1], expectations[counter], "Counter %d" % counter)
            request.setResponseCode(200)
            request.finish()
        self.webServer.requestHandler = onRequest
        
        first_client = MockFlashClient()
        reconnecting_client = MockFlashClient()
        
        def connectAnotherClient(client):
            client.connectedEvent.addCallback(lambda _: client.sendSubscribeMessage(1, [1]))
            task.deferLater(reactor, 0.02, client.connector.disconnect)
        
        first_client.connectedEvent.addCallback(lambda _: first_client.sendSubscribeMessage(1, [1]))
        reactor.callLater(0.02, first_client.connector.disconnect)
        reactor.callLater(0.06, connectAnotherClient, reconnecting_client)
        
        return reconnecting_client.disconnectedEvent
        
    def testBroadcastToChannels(self):
        pass