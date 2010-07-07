class RequestParamsHelper:
    def __init__(self, client, channels, service):
        self.client = client
        self.channels = channels
        self.service = service
        
    def _commonParams(self):
        params = []
        params.append("client_id=%s" % str(self.client.client_id))
        params.append("session_id=%s" % str(self.client.session_id))
        if len(self.channels) > 0:
            params.append("channels[]=%s" % str(self.channels[0]))
        return params
    
    def subscribeParams(self):
        params = self._commonParams()
        i = -1
        for client in self.service.clientsInChannel(self.client.channel_id):
            params.append("clients_in_channel[%d]=%s" % (i, str(client.session_id)))
            i += 1
            
        return '&'.join(params)
        
    def disconnectedParams(self):
        params = self._commonParams()
        return '&'.join(params)