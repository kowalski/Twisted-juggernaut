import juggernaut
from twisted.application import internet, service
from twisted.python import log
import yaml

config_name = 'juggernaut.yml'
try:
    config = yaml.load(open(config_name, 'r').read())
except IOError:
    log.err("Config file %s not found! " % config_name)
    raise

application = service.Application("juggernaut")
f = juggernaut.makeService(config)
serviceCollection = service.IServiceCollection(application)
internet.TCPServer(config['port'], juggernaut.IJuggernautFactory(f)).setServiceParent(serviceCollection)
