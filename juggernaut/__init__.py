#!/usr/bin/env python
from twisted.application import service, internet
from twisted.internet import protocol
from twisted.python import log, components
from zope.interface import implements, Interface
import sys

class JuggernautProtocol(protocol.Protocol):
    
    CR = "\0"
    
    def __init__(self):
        self.buffer = []
        self.messages = []
    
    def dataReceived(self, data):
        
        if data.strip() == "quit":
            self.transport.loseConnection()
            
        self.factory.service.broadcast(data)
    
    def connectionMade(self):
        self.factory.service.clients.append(self)
        
    def connectionLost(self, reason):
        self.factory.service.clients.remove(self)
        log.msg(self.factory.service.clients)

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
    
    def __init__(self):
        self.clients = []
    
    def broadcast(self, msg):
        for client in self.clients:
            client.transport.write("###\nMessage: %s\n###\n" % msg)

components.registerAdapter(JuggernautService, IJuggernautService, service.IService)