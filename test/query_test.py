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
        
    def _assertResponse(self, response):
        self.assertEqual(response, json.loads(self.rails.connector.transport.protocol.messages[-1]))