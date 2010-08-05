#!/usr/bin/env python
from twisted.application import service, internet
from twisted.internet import protocol, defer, reactor
from twisted.python import log, components
from twisted.web import client as web_client
from zope.interface import implements, Interface
import sys, re, json

from helpers import RequestParamsHelper

class IJuggernautClient(Interface):
    def __init__(self, connector, client_id, session_id):
        pass
    
    def markDead(self):
        """Mark client connection as disconnected. Dead clients only store messages"""

class JuggernautClient():
    implements(IJuggernautClient)

    def __init__(self, connector, client_id, session_id, channel_id):
        self.connector = connector
        self.client_id = client_id
        self.channel_id = None
        self.session_id = session_id
        self.is_alive = True
        self.service = self.connector.factory.service
        self.logoutTaskCall = None

    def markDead(self):
        self.is_alive = False
        self.connector = None
        self.stored_messages = []
        log.msg('Marked dead client_id=%s, channel_id=%s' % (str(self.client_id), str(self.channel_id)))
        if self.channel_id != None:
            self.service.disconnectedRequest(self, [self.channel_id])
        self.logoutTaskCall = reactor.callLater(self.service.config['timeout'], self.service.logoutRequest, self)
            
    def markAlive(self, connector):
        """Called when the disconnected client subscribes again"""
        self.connector = connector
        self.is_alive = True
        self.sendStoredMessages()
        
        if self.logoutTaskCall:
            self.logoutTaskCall.cancel()
            self.logoutTaskCall = None
            
    def sendMessage(self, body):
        """Send message to connection, store it if client is dead"""
        
        msg = Message(body)
        if self.is_alive:
            log.msg("Sending message to client_id=%s body=%s" % (str(self.client_id), str(msg)))
            self.writeMessageToConnection(msg)
        else:
            self.stored_messages.append(msg)
            
    def writeMessageToConnection(self, msg):
        """Write message body to a connection transport"""
        self.connector.transport.write(str(msg) + JuggernautProtocol.CR)
        
    def sendStoredMessages(self):
        """Send stored messages after the client has been reconnected"""
        for message in self.stored_messages:
            self.writeMessageToConnection(message)
        self.stored_messages = None
        
    def toJSON(self):
        return json.dumps({
            'client_id': self.client_id, 
            'num_connections': self.numConnections(),
            'session_id': self.session_id
        })
        
    def numConnections(self):
        if self.is_alive:
            return 1
        return 0
        
class IJuggernautProtocol(Interface):
    pass

class Message:
    current_id = 0
    
    def __init__(self, body):
        self.body = body
        self.id = Message.current_id 
        Message.current_id += 1
        
    def __str__(self):
        return json.dumps({'id': self.id, 'body': self.body})

components.registerAdapter(JuggernautClient, IJuggernautClient, IJuggernautProtocol)
      
class JuggernautProtocol(protocol.Protocol):
    implements(IJuggernautProtocol)
    
    CR = "\0"
    CR_END = re.compile(CR + '$')
    
    def __init__(self):
        self.buffer = ""
        self.client = None
        
    def dataReceived(self, data):
        self.buffer += data
        split = self.buffer.split(self.CR)
        
        if not self.CR_END.match(self.buffer):
            self.buffer = split.pop()
            
        for message in split:
            self.processMessage(message)
        
    def processMessage(self, message):
        log.msg("Processing message: %s" % message)
        try:
            request = json.loads(message)
            self._checkExists(request, 'command', unicode)
            method = getattr(self, request['command'] + "Command")
            method(request)
        except Exception as e:
            if message == "<policy-file-request/>":
                self.sendPolicyFile()
            else:
                log.err("Processing message failed with exception: %s" % str(e))
                self.transport.loseConnection()
        
    def subscribeCommand(self, request):
        log.msg("SUBSCRIBE: %s" % str(request))
        
        self._checkExists(request, 'channels', list)
        self._checkExists(request, 'client_id', int)
        self._checkExists(request, 'session_id', int)
        if len(request['channels']) != 1:
            raise ValueError("You can pass only one channel to subscribe to!")
    
        self.client = self.factory.service.findOrCreateClient(self, request['client_id'], request['session_id'], request['channels'][0])
        self.factory.service.subscribeRequest(self.client, [request['channels'][0]])
            
            
    def broadcastCommand(self, request):
        log.msg("BROADCAST: %s" % str(request))
        
        self._checkExists(request, 'type', unicode)
        self._checkExists(request, 'body', [unicode, dict])
                
        self.factory.service.authenticateBroadcastOrQuery(self, request)
        
        method = getattr(self.factory.service, 'broadcast_' + request['type'])
        method(request)
        
    def queryCommand(self, request):
        log.msg("QUERY: %s" % str(request))
        
        self._checkExists(request, 'type', unicode)
        
        self.factory.service.authenticateBroadcastOrQuery(self, request)
        
        method = getattr(self.factory.service, 'query_' + request['type'])
        method(request, self)
        
    def connectionLost(self, reason):
        if self.client:
            self.client.markDead()

    def _checkExists(self, request, key, classes):
        if not isinstance(classes, list):
            classes = [ classes ]
        if not classes.__contains__(request[key].__class__):
            raise ValueError("Key %s should be of type of %s, but was %s instead" % (key, str(classes), request[key].__class__.__name__))

    def sendPolicyFile(self):
        log.msg('Sending policy file')
        self.transport.write('''
            <cross-domain-policy>
                <allow-access-from domain="*" to-ports="%d" />
            </cross-domain-policy>''' % self.factory.service.config['port'])
        self.transport.loseConnection()

class IJuggernautFactory(Interface):
    pass
    
class JuggernautFactoryFromService(protocol.ServerFactory):
    implements(IJuggernautFactory)
    
    protocol = JuggernautProtocol
    
    def __init__(self, service):
        self.service = service
        
class IJuggernautService(Interface):
    pass
        
components.registerAdapter(JuggernautFactoryFromService, IJuggernautService, IJuggernautFactory)
        
class JuggernautService(service.Service):
    implements(IJuggernautService)
    
    def __init__(self, options):
        self.channels = {}
        self.config = options
        self.clients = {}
    
    def findOrCreateClient(self, connector, client_id, session_id, channel_id):
        try: 
            found_client = self.clients[client_id]  # TODO: Make it somehow secure. Now connection can be kidnappned
            if found_client.is_alive:
                raise Exception("Client with id %s already logged in" % str(client_id))
            found_client.markAlive(connector)
            return found_client
        except KeyError:
            new_client = JuggernautClient(connector, client_id, session_id, channel_id)
            self.clients[client_id] = new_client
            return new_client
    
    def subscribeRequest(self, client, channels):
        content_helper = RequestParamsHelper(client, channels, self)
        request_task = web_client.getPage(self.config['subscription_url'], method="POST", postdata=content_helper.subscribeParams()) 
        
        channel_id = channels[0]
        def appendClientToChannel(*a):
            try:
                self.channels[channel_id].append(client)
            except KeyError:
                self.channels[channel_id] = [ client ]
            client.channel_id = channel_id
            
        def subscribeFail(err):
            log.err("Sending request failed %s" % str(err))
            client.connector.transport.loseConnection()
        request_task.addCallbacks(appendClientToChannel, subscribeFail)
        
        return request_task
        
    def disconnectedRequest(self, client, channels):
        content_helper = RequestParamsHelper(client, [client.channel_id], self)
        web_client.getPage(self.config['logout_connection_url'], method="POST", postdata=content_helper.disconnectedParams())
    
    def logoutRequest(self, client):
        content_helper = RequestParamsHelper(client, [client.channel_id], self)
        web_client.getPage(self.config['logout_url'], method="POST", postdata=content_helper.disconnectedParams())
        self.removeClient(client)
        
    def removeClient(self, client):
        try:
            self.channels[client.channel_id].remove(client)
            if len(self.channels[client.channel_id]) == 0:
                log.msg("Removing channel %s" % str(client.channel_id))
                del(self.channels[client.channel_id])
        except KeyError:
            log.err("Removing client from channel failed! Channel %s not found!" % str(client.channel_id))
        except ValueError:
            log.err("Removing client from channel failed! Client not found in channel %s" % str(client.channel_id))
        try:
            del(self.clients[client.client_id])
        except KeyError:
            log.err("Removing client failed. Client with id %s not found!" % str(client.client_id))
        
    def clientsInChannel(self, channel):
        try:
            return self.channels[channel]
        except KeyError:
            return []

    def authenticateBroadcastOrQuery(self, connector, request):
        ip = connector.transport.getHost().host
        if self.config['allowed_ips'].__contains__(ip):
            return True
        else:
            raise Exception('Dissalowed request %s from %s' % (str(request), str(ip)))
        
    def broadcast_to_channels(self, request):
        ids_to_send = []
        for channel in request['channels']:
            map(lambda x: ids_to_send.append(x.client_id), self.clientsInChannel(channel))
        
        request['client_ids'] = ids_to_send
        self.broadcast_to_clients(request)
         
    def broadcast_to_clients(self, request):
        for client_id in request['client_ids']:
            client = self._findClient(client_id)
            if client:
                client.sendMessage(request['body'])
                
    def query_remove_channels_from_client(self, request, connector):
        '''Disconnect clients from the given channels'''
        for client_id in request['client_ids']:
            client = self._findClient(client_id)
            if client and request['channels'].__contains__(client.channel_id):
                client.connector.transport.loseConnection()

    def query_show_channels_for_client(self, request, connector):
        client = self._findClient(request['client_id'])
        resp = None
        if client:
            resp = [ client.channel_id ]
        self._publishResponse(connector, resp)
        
    def query_show_clients(self, request, connector):
        if request.has_key('client_ids'):
            clients = map(lambda x: self._findClient(x), request['client_ids'])
            clients = filter(lambda x: x != None, clients)
        else:
            clients = self.clients
        self._publishResponse(connector, map(lambda x: x.toJSON(), clients))
    
    def query_show_client(self, request, connector):
        client = self._findClient(request['client_id'])
        resp = client and client.to_json() or json.dumps(None)
        self._publishResponse(connector, resp)
        
    def query_show_clients_for_channels(self, request, connector):
        clients = []
        for channel_id in request['channels']:
            if self.channels.has_key[channel_id]:
                clients = clients + self.channels[channel_id]
        self._publishResponse(connector, map(lambda x: x.toJSON(), clients))
            
    def _publishResponse(self, connector, msg):
        connector.transport.write(json.dumps(msg) + JuggernautProtocol.CR)
    
    def _findClient(self, client_id):
        try:
            return self.clients[client_id]
        except KeyError:
            log.err('Client with id %s not found!' % client_id)
            return None
    
components.registerAdapter(JuggernautService, IJuggernautService, service.IService)

def makeService(options):
    return JuggernautService(options)