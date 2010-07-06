import juggernaut
from twisted.application import internet, service

config = {
    'host': 'localhost',
    'port': 5001,
    'allowed_ips': ['127.0.0.1'],
    'subscription_url': 'http://localhost:8080/subscribe',
    'logout_connection_url': 'http://localhost:8080/disconnected',
    'logout_url': 'http://localhost:8080/logged_out',
    'timeout': 10
}

application = service.Application("juggernaut")
f = juggernaut.makeService(config)
serviceCollection = service.IServiceCollection(application)
internet.TCPServer(config['port'], juggernaut.IJuggernautFactory(f)).setServiceParent(serviceCollection)
