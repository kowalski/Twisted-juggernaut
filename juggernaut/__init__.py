#!/usr/bin/env python
from twisted.application import service, internet
from twisted.internet import protocol, defer
from twisted.python import log, components
from twisted.web import client as web_client
from zope.interface import implements, Interface
import sys, re, json

from helpers import RequestParamsHelper

class JuggernautProtocol(protocol.Protocol):
    
    CR = "\0"
    CR_END = re.compile(CR + '$')
    
    def __init__(self):
        self.buffer = ""
        self.channel_id = None
        self.client_id = None
        self.session_id = None
        
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
    
        self.session_id = request['session_id']
        self.client_id = request['client_id']
        
        #def sendMessages(self, content):
            #if len(content) > 0:
                #log.msg("Sending payload from subscribe request to the client")
                #messages = json.load(content)
                #for message in messages:
                    #self.transport.write(
        self.factory.service.subscribeRequest(self, request['channels'])
            
    def connectionMade(self):
        self.factory.service.clients.append(self)
        
    def connectionLost(self, reason):
        log.msg('Connection lost channel_id %s' % str(self.channel_id))
        if self.channel_id:
            self.factory.service.removeClient(self)

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
    def broadcast(self, msg):
        """broadcast message to the clients"""
        
components.registerAdapter(JuggernautFactoryFromService, IJuggernautService, IJuggernautFactory)
        
class JuggernautService(service.Service):
    implements(IJuggernautService)
    
    def __init__(self, options):
        self.clients = []
        self.channels = {}
        self.config = options
    
    def broadcast(self, msg):
        for client in self.clients:
            client.transport.write("###\nMessage: %s\n###\n" % msg)
            
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
            client.transport.loseConnection()
        request_task.addCallbacks(appendClientToChannel, subscribeFail)
        
        return request_task
        
    def removeClient(self, client):
        content_helper = RequestParamsHelper(client, [client.channel_id], self)
        try:
            self.channels[client.channel_id].remove(client)
        except KeyError:
            log.err("Removing client from channel failed! Channel %s not found!" % str(client.channel_id))
        except ValueError:
            log.err("Removing client from channel failed! Client not found in channel %s" % str(client.channel_id))
        finally:
            web_client.getPage(self.config['logout_url'], method="POST", postdata=content_helper.loggedOutParams())
    def clientsInChannel(self, channel):
        try:
            return self.channels[channel]
        except KeyError:
            return []

components.registerAdapter(JuggernautService, IJuggernautService, service.IService)

def makeService(options):
    return JuggernautService(options)