class RequestParamsHelper:
    def __init__(self, client, channels, service):
        self.client = client
        self.channels = channels
        self.service = service
        
    def subscribe_params(self):
        params = []
        params.append("client_id=%s" % str(self.client.client_id))
        params.append("session_id=%s" % str(self.client.session_id))
        
        if len(self.channels) != 1:
            raise ValueError("You can pass only one channel to subscribe to")
        params.append("channels[]=%s" % str(self.channels[0]))
            
        i = -1
        for client in self.service.clients_in_channel(self.channels[0]):
            params.append("clients_in_channel[%d]=%s" % (i, str(client.session_id)))
            i += 1
            
        return '&'.join(params)