from twisted.python import log
from twisted.internet import protocol, defer, task, reactor
import juggernaut

import sys
sys.path.append('test')
from test_helper import *

class QueryTest(JuggernautTest):
    def setUp(self):
        JuggernautTest.setUp(self)
        self.rails = MockFlashClient()
        self.client = MockFlashClient(1)
        reactor.callLater(0.1, self.client.sendSubscribeMessage)
        
    def tearDown(self):
        self.rails.connector.disconnect()
        return defer.DeferredList([self.rails.disconnectedEvent, JuggernautTest.tearDown(self)])
    
    def testQueryRemoveChannelsFromClient(self):
        '''Remove client with ID=1, should not affect client with ID=2'''
        self.webServer.expectRequests(6)
        second_client = MockFlashClient(2)
        reactor.callLater(0.1, second_client.sendSubscribeMessage, [2])
        reactor.callLater(0.2, self._sendRemoveChannelsMessage, [1], [1])
        
        d = task.deferLater(reactor, 0.3, self._assertClientIsConnected, second_client)
        d.addCallback(lambda _: second_client.connector.disconnect())
        
        return defer.DeferredList([self.client.disconnectedEvent, second_client.disconnectedEvent])
        
    def testQueryRemoveChannelsFromClientWithNonexistingData(self):
        '''Send the request with nonexisting client_ids and channel. Client should stay connected'''
        self.webServer.expectRequests(3)
        reactor.callLater(0.2, self._sendRemoveChannelsMessage, [2, 3, 4], [4])
        
        d = task.deferLater(reactor, 0.3, self._assertClientIsConnected, self.client)
        d.addCallback(lambda _: self.client.connector.disconnect())
        
        return self.client.disconnectedEvent
        
    def testQueryShowChannelsForClient(self):
        self.webServer.expectRequests(3)
        
        reactor.callLater(0.2, self._sendShowChannelsMessage, 1)
        reactor.callLater(0.3, self._assertResponse, [1])
        reactor.callLater(0.3, self._sendShowChannelsMessage, 2) #nonexisting client
        reactor.callLater(0.4, self._assertResponse, None)
        
        d = task.deferLater(reactor, 0.5, self.client.connector.disconnect)
        
        return self.client.disconnectedEvent
        
    def testShowClients(self):
        self.webServer.expectRequests(6)
        self.config['timeout'] = 0.1
        
        reactor.callLater(0.2, self._sendShowClientsMessage)
        reactor.callLater(0.25, self._assertResponse, [{ 'client_id': 1, 'session_id': 1, "num_connections": 1 }])
        
        client2 = MockFlashClient(2)
        reactor.callLater(0.3, client2.sendSubscribeMessage, [2])
        
        reactor.callLater(0.35, self._sendShowClientsMessage, [1]) #query only for the previous client
        reactor.callLater(0.4, self._assertResponse, [{ 'client_id': 1, 'session_id': 1, "num_connections": 1 }])
        reactor.callLater(0.45, self._sendShowClientsMessage)
        reactor.callLater(0.5, self._assertResponse, [{ 'client_id': 1, 'session_id': 1, "num_connections": 1 }, { 'client_id': 2, 'session_id': 2, "num_connections": 1 }])
        
        d = task.deferLater(reactor, 0.55, self.client.connector.disconnect)
        d.addCallback(lambda _: client2.connector.disconnect())
        dd1 = task.deferLater(reactor, 0.6, self._sendShowClientsMessage)
        dd2 = task.deferLater(reactor, 0.65, self._assertResponse, [{ 'client_id': 1, 'session_id': 1, "num_connections": 0 }, { 'client_id': 2, 'session_id': 2, "num_connections": 0 }]) # dead clients should report num_connection = 0
        
        dd3 = task.deferLater(reactor, 0.7, self._sendShowClientsMessage)
        dd4 = task.deferLater(reactor, 0.75, self._assertResponse, []) # after timeout clients vanish
        
        return defer.DeferredList([self.client.disconnectedEvent, client2.disconnectedEvent, dd1, dd2, dd3, dd4])
    
    def testShowClientsForChannel(self):
        self.webServer.expectRequests(6)
        self.config['timeout'] = 0.1
        
        reactor.callLater(0.2, self._sendShowClientsForChannelsMessage, [1])
        reactor.callLater(0.25, self._assertResponse, [{ 'client_id': 1, 'session_id': 1, "num_connections": 1 }])
        
        client2 = MockFlashClient(2)
        reactor.callLater(0.3, client2.sendSubscribeMessage, [2])
        
        reactor.callLater(0.35, self._sendShowClientsForChannelsMessage, [1]) 
        reactor.callLater(0.4, self._assertResponse, [{ 'client_id': 1, 'session_id': 1, "num_connections": 1 }])
        reactor.callLater(0.45, self._sendShowClientsForChannelsMessage, [1, 2])
        reactor.callLater(0.5, self._assertResponse, [{ 'client_id': 1, 'session_id': 1, "num_connections": 1 }, { 'client_id': 2, 'session_id': 2, "num_connections": 1 }])
        
        d = task.deferLater(reactor, 0.55, self.client.connector.disconnect)
        d.addCallback(lambda _: client2.connector.disconnect())
        dd1 = task.deferLater(reactor, 0.6, self._sendShowClientsForChannelsMessage, [1, 2])
        dd2 = task.deferLater(reactor, 0.65, self._assertResponse, [{ 'client_id': 1, 'session_id': 1, "num_connections": 0 }, { 'client_id': 2, 'session_id': 2, "num_connections": 0 }]) 
        
        dd3 = task.deferLater(reactor, 0.7, self._sendShowClientsForChannelsMessage, [1, 2])
        dd4 = task.deferLater(reactor, 0.75, self._assertResponse, []) # after timeout clients vanish
        
        return defer.DeferredList([self.client.disconnectedEvent, client2.disconnectedEvent, dd1, dd2, dd3, dd4])
        
    def testShowClient(self):
        self.webServer.expectRequests(3)
        reactor.callLater(0.2, self._sendShowClient, 1)
        reactor.callLater(0.25, self._assertResponse, { 'client_id': 1, 'session_id': 1, "num_connections": 1 })
        
        reactor.callLater(0.25, self._sendShowClient, 2)
        reactor.callLater(0.3, self._assertResponse, None)
        
        reactor.callLater(0.35, self.client.connector.disconnect)
        
        return self.client.disconnectedEvent
    
    def _sendRemoveChannelsMessage(self, client_ids, channels):
        self.rails.sendMessage({
            'command': 'query',
            'type': 'remove_channels_from_client',
            'client_ids': client_ids,
            'channels': channels
        })
        
    def _sendShowChannelsMessage(self, client_id):
        self.rails.sendMessage({
            'command': 'query',
            'type': 'show_channels_for_client',
            'client_id': client_id
        })
        
    def _sendShowClientsMessage(self, client_ids=None):
        msg = {
            'command': 'query',
            'type': 'show_clients'
        }
        if client_ids:
            msg['client_ids'] = client_ids
        self.rails.sendMessage(msg)
    
    def _sendShowClientsForChannelsMessage(self, channels):
        self.rails.sendMessage({
            'command': 'query',
            'type': 'show_clients_for_channels',
            'channels': channels
        })
    
    def _sendShowClient(self, client_id):
        self.rails.sendMessage({
            'command': 'query',
            'type': 'show_client',
            'client_id': client_id
        })
    
    def _assertResponse(self, response):
        self.assertEqual(response, json.loads(self.rails.connector.transport.protocol.messages[-1]))