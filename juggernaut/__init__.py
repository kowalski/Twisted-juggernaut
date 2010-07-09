#!/usr/bin/env python
from twisted.application import service, internet
from twisted.internet import protocol, defer
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
        
        self.service.subscribeRequest(self, [channel_id])

    def markDead(self):
        self.is_alive = False
        self.connector = None
        if self.channel_id:
            self.service.disconnectedRequest(self, [self.channel_id])

class IJuggernautProtocol(Interface):
    pass

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
    
        self.client = JuggernautClient(self, request['client_id'], request['session_id'], request['channels'][0])
            
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
        
    def removeClient(self, client):
        content_helper = RequestParamsHelper(client, [client.channel_id], self)
        try:
            self.channels[client.channel_id].remove(client)
        except KeyError:
            log.err("Removing client from channel failed! Channel %s not found!" % str(client.channel_id))
        except ValueError:
            log.err("Removing client from channel failed! Client not found in channel %s" % str(client.channel_id))
        finally:
            pass
    def clientsInChannel(self, channel):
        try:
            return self.channels[channel]
        except KeyError:
            return []

components.registerAdapter(JuggernautService, IJuggernautService, service.IService)

def makeService(options):
    return JuggernautService(options)