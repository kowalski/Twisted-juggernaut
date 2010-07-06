==================
Twisted Juggernaut
==================

This project is a rewrite of popular juggernaut server which ships with juggernaut gem. My motivation for this project is simple:
 * I wanted to learn Twisted
 * Juggernaut seems to be perfectly suited to for the first Twisted project
 * Existing juggernaut server code is...  far from being readable. I thought it would be nice to port juggernaut not to use flash socket connections. I plan to serve the same protocol through the websocket. This could work nice with IPads, IPhones and so on.
 
Feautures of this implementation
=================================

My plan is to make this server as simillar to Juggernaut as possible. But frankly there are some things in original Juggernaut implemenetation that I do not like at all. So below I list feautures I _do not_ plan to include in this implementation:
 * Clients can listen only to one channel. Original subscribe command allowed passing an array of channels, but I'm not even sure this worked. At least not with Rails. In my implementation only a single channel is allowed (though API stays the same)
 * Clients cannot broadcast. There is no broadcast request. Any client with ip not listed in allowed_ips will be disconneted imediatly. 
 
On the other hand there are some features not available in original implementation which I plan to include:
 * Subscribe action can render a json with form [ msg1, msg2, msg3 ]. Theese messages will be sent to newly subscribed client.
 * Deadlock problem solved. Now you can query juggernaut, send messages, etc from inside subscribe/disconneted/logged_out actions without risking the deadlock. This was one of the most annoying bugs of original implementation.
 * Subscribe action sends extra params. You get an hash called clients_in_channel, which values are the client_id's of clients already connected to the channel.
 * Monitoring is included. This is something given extra from twisted. This server ships as a .deb package which installs scripts in /etc/init.d and performs all the magic. You don't have to worry about server going down.