from twisted.python import log
from twisted.internet import protocol, defer, task, reactor
import juggernaut

import sys
sys.path.append('test')
from test_helper import *

class BroadcastTest(JuggernautTest):
    
    def testBroadcastToChannel(self):
        self.webServer.expectRequests(9)
        clients = map(lambda x: MockFlashClient(x), range(3))
        rails_app = MockFlashClient()
        
        def subscribeClients(*a):
            for client in clients:
                client.sendSubscribeMessage()
            
        reactor.callLater(0.05, subscribeClients)
        reactor.callLater(0.1, rails_app.sendBroadcastToChannelsMessage, "Czesc", [1])
        
        def assertMessagesArrived(*a):
            for client in clients:
                self.assertEqual(len(client.connector.transport.protocol.messages), 1)
                msg = json.loads(client.connector.transport.protocol.messages[0])
                self.assertEqual(msg['body'], 'Czesc')
        d = task.deferLater(reactor, 0.2, assertMessagesArrived)
        
        def disconnectClients(*a):
            for client in clients + [rails_app]:
                client.connector.disconnect()
        d.addCallback(disconnectClients)
        
        return defer.DeferredList((map(lambda x: x.disconnectedEvent, clients + [rails_app])) + [d])
            
    def testBroadcastToClient(self):
        self.webServer.expectRequests(6)
        clients = map(lambda x: MockFlashClient(x), range(2))
        rails_app = MockFlashClient()
        
        def subscribeClients(*a):
            for client in clients:
                client.sendSubscribeMessage()
            
        reactor.callLater(0.05, subscribeClients)
        
        messages = [ "First client", "Second client" ]
        reactor.callLater(0.1, rails_app.sendBroadcastToClientsMessage, messages[0], [0])
        reactor.callLater(0.1, rails_app.sendBroadcastToClientsMessage, messages[1], [1])
        
        def assertMessagesArrived(*a):
            index = 0
            for client in clients:
                self.assertEqual(len(client.connector.transport.protocol.messages), 1)
                msg = json.loads(client.connector.transport.protocol.messages[0])
                self.assertEqual(msg['body'], messages[index])
                index += 1
        d = task.deferLater(reactor, 0.2, assertMessagesArrived)
        
        def disconnectClients(*a):
            for client in clients + [rails_app]:
                client.connector.disconnect()
        d.addCallback(disconnectClients)
        
        return defer.DeferredList((map(lambda x: x.disconnectedEvent, clients + [rails_app])) + [d])
        
    def testTwoChannels(self):
        '''Here we subscribe to two different channels and make sure message reach correct destination'''
        self.webServer.expectRequests(12)
        #base.DelayedCall.debug = True
        clients = map(lambda x: MockFlashClient(x), range(4))
        rails_app = MockFlashClient()
        
        def subscribeClients(*a):
            index = 0
            for client in clients:
                client.sendSubscribeMessage([index / 2]) #two clients per channel 0 and 1
                index += 1
            
        reactor.callLater(0.05, subscribeClients)
        
        messages = [ "First channel", "Second channel" ]
        reactor.callLater(0.1, rails_app.sendBroadcastToChannelsMessage, messages[0], [0])
        reactor.callLater(0.1, rails_app.sendBroadcastToChannelsMessage, messages[1], [1])
        
        def assertMessagesArrived(*a):
            index = 0
            for client in clients:
                self.assertEqual(len(client.connector.transport.protocol.messages), 1)
                msg = json.loads(client.connector.transport.protocol.messages[0])
                self.assertEqual(msg['body'], messages[index / 2])
                index += 1
        d = task.deferLater(reactor, 0.2, assertMessagesArrived)
        d.addErrback(errorHandler)
        
        def disconnectClients(*a):
            for client in clients + [rails_app]:
                client.connector.disconnect()
        d.addCallback(disconnectClients)
        
        return defer.DeferredList((map(lambda x: x.disconnectedEvent, clients + [rails_app])) + [d])