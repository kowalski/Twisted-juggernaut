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
        log.msg('Marked dead client_id=%s, channel_id=%s' % (str(self.client_id), str(self.channel_id)))
        if self.channel_id:
            self.service.disconnectedRequest(self, [self.channel_id])
        self.logoutTaskCall = reactor.callLater(self.service.config['timeout'], self.service.logoutRequest, self)
            
    def markAlive(self, connector):
        self.connector = connector
        self.is_alive = True
        
        if self.logoutTaskCall:
            self.logoutTaskCall.cancel()
            self.logoutTaskCall = None
            
    def sendMessage(self, body):
        msg = Message(body)
        log.msg("Sending message to client_id=%s body=%s" % (str(self.client_id), str(msg)))
        
        self.connector.transport.write(str(msg) + JuggernautProtocol.CR)

class IJuggernautProtocol(Interface):
    pass

class Message:
    current_id = 0
    
    def __init__(self, body):
        self.body = body
        self.id = self.current_id 
        self.current_id += 1

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
        self._checkExists(request, 'body', unicode)
        
        self.factory.service.authenticateBroadcastOrQuery(self, request)
        
        method = getattr(self.factory.service, 'broadcast_' + request['type'])
        method(request)
        
    def connectionLost(self, reason):
        if self.client:
            self.client.markDead()

    def _checkExists(self, request, key, klass):
        if not isinstance(request[key], klass):
            raise ValueError("Key %s should be of type of %s, but was %s instead" % (key, klass.__name__, request[key].__class__.__name__))

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
            log.error("Removing client failed. Client with id %s not found!" % str(client.client_id))
        
    def clientsInChannel(self, channel):
        try:
            return self.channels[channel]
        except KeyError:
            return []

    def authenticateBroadcastOrQuery(self, connector, request):
        ip = connector.transport.getHost().host
        if self.config['allowed_ips'].__contains__(ip):
            return true
        else:
            raise Exception('Dissalowed request %s from %s' % (str(request), str(ip)))
        
    def broadcast_to_channels(self, request):
        ids_to_send = []
        for channel in request['channels']:
            map(lambda x: ids_to_send.append(x), self.clientsInChannel(channel))
        
        request['client_ids'] = ids_to_send
        self.broadcast_to_clients(self, request)
         
    def broadcast_to_clients(self, request):
        for client_id in request['client_ids']:
            try:
                self.clients[client_id].sendMessage(request['body'])
            except KeyError:
                log.error('Client with id %s not found!' % client_id)

components.registerAdapter(JuggernautService, IJuggernautService, service.IService)

def makeService(options):
    return JuggernautService(options)