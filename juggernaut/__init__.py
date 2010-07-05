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
            method = getattr(self, request['command'] + "_command")
            method(request)
        except Exception as e:
            log.err("Processing message failed with exception: %s" % str(e))
            self.transport.loseConnection()
        
    def subscribe_command(self, request):
        log.msg("SUBSCRIBE: %s" % str(request))
        
        self._checkExists(request, 'channels', list)
        self._checkExists(request, 'client_id', int)
        self._checkExists(request, 'session_id', int)
        
        self.client_id = request['client_id']
        self.session_id = request['session_id']
        
        #def sendMessages(self, content):
            #if len(content) > 0:
                #log.msg("Sending payload from subscribe request to the client")
                #messages = json.load(content)
                #for message in messages:
                    #self.transport.write(
        self.factory.service.subscribe_request(self, request['channels'])
            
    def connectionMade(self):
        self.factory.service.clients.append(self)
        
    def connectionLost(self, reason):
        self.factory.service.clients.remove(self)

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
            
    def subscribe_request(self, client, channels):
        content_helper = RequestParamsHelper(client, channels, self)
        request_task = web_client.getPage(self.config['subscription_url'], method="POST", postdata=content_helper.subscribe_params()) 
        def appendClientToChannel(*a):
            try:
                self.channels[channels[0]].append(client)
            except KeyError:
                self.channels[channels[0]] = [ client ]
        def subscribeFail(err):
            log.err("Sending request failed %s" % str(err))
            client.transport.loseConnection()
        
        request_task.addCallbacks(appendClientToChannel, subscribeFail)
        
        return request_task 
    
    def clients_in_channel(self, channel):
        try:
            return self.channels[channel]
        except KeyError:
            return []

components.registerAdapter(JuggernautService, IJuggernautService, service.IService)

def makeService(options):
    return JuggernautService(options)