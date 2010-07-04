import juggernaut
from twisted.application import internet, service

application = service.Application("juggernaut")
f = juggernaut.JuggernautService()
serviceCollection = service.IServiceCollection(application)
internet.TCPServer(5001, juggernaut.IJuggernautFactory(f)).setServiceParent(serviceCollection)
