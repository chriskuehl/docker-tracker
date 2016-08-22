#!/usr/bin/env python
"""Docker proxy which tracks containers created.

To use, start this script, passing in the port to bind on.
Then, you may launch other programs with DOCKER_HOST=localhost:[port].

For example:

    ./tracker.py -p 8080

    # in another context
    DOCKER_HOST=localhost:8080 ./my-bad-program

    # later, clean up any containers it left running
    curl http://localhost:8080/tracker | xargs -n1 docker kill

    # finally, kill the tracker
    # ...left as an exercise to the reader
"""
import argparse
import json
import re

from twisted.internet import reactor
from twisted.web import http
from twisted.web import proxy
from twisted.web import server
from twisted.web.http import HTTPClient
from twisted.web.resource import Resource


containers_launched = set()


class DockerProxyClient(proxy.ProxyClient, object):

    def __init__(self, *args, **kwargs):
        super(DockerProxyClient, self).__init__(*args, **kwargs)
        self._upgrade = False
        self._received = b''

    @property
    def _is_create_container(self):
        return self.command == 'POST' and re.match('/v[\d\.]+/containers/create', self.rest)

    def handleHeader(self, key, value):
        super(DockerProxyClient, self).handleHeader(key, value)
        if key.lower() == b'upgrade' and value.lower() == b'tcp':
            self._upgrade = True

    def handleEndHeaders(self):
        if self._upgrade:
            # Force end of headers, keep us out of chunked mode
            self.father.responseHeaders.addRawHeader('content-length', 0)
            self.father.write(b'')

            # Patch the channel from server -> client to write byte-by-byte
            def dataReceivedFromDocker(data):
                if not self._finished:
                    self.father.write(data)

            self.rawDataReceived = dataReceivedFromDocker

            herpderp = self.father.channel.write

            # Patch the client -> server channel the same way
            def dataReceivedFromClient(data):
                if not self._finished:
                    self.transport.write(data)

            self.father.channel._producer.resumeProducing()
            self.father.channel.setRawMode()
            self.father.channel.rawDataReceived = dataReceivedFromClient

    def handleResponsePart(self, buff):
        super(DockerProxyClient, self).handleResponsePart(buff)
        if self._is_create_container:
            self._received += buff

    def handleResponseEnd(self):
        if self._upgrade and not self._finished:
            self.father.channel.loseConnection()

        super(DockerProxyClient, self).handleResponseEnd()
        if self._is_create_container:
            # https://docs.docker.com/engine/reference/api/docker_remote_api_v1.24/#/create-a-container
            j = json.loads(self._received)
            containers_launched.add(j['Id'])


class DockerProxyClientFactory(proxy.ProxyClientFactory, object):
    protocol = DockerProxyClient


class DockerReverseProxyResource(proxy.ReverseProxyResource, object):
    proxyClientFactoryClass = DockerProxyClientFactory

    def __init__(self, unix_socket, path, reactor=reactor):
        super(DockerReverseProxyResource, self).__init__(
            'fake.host',
            1234,
            path,
            reactor=reactor,
        )
        self.unix_socket = unix_socket

    def getChild(self, path, request):
        child = super(DockerReverseProxyResource, self).getChild(path, request)
        return DockerReverseProxyResource(
            self.unix_socket,
            child.path,
            child.reactor,
        )

    def render(self, request):
        """Modified render that instead uses UNIX sockets.

        We don't want to duplicate all the logic that happens here:
        https://github.com/twisted/twisted/blob/45d3b7ee43c405eaf815797dc9f46ebdfee186af/src/twisted/web/proxy.py#L282-L303

        ...so instead, we patch the reactor

        Sorry about this :(
        """
        def fake_connect_tcp(host, port, factory):
            return self.reactor.connectUNIX(self.unix_socket, factory)

        self.reactor._connectTCP = self.reactor.connectTCP
        self.reactor.connectTCP = fake_connect_tcp
        try:
            return super(DockerReverseProxyResource, self).render(request)
        finally:
            self.reactor.connectTCP = self.reactor._connectTCP


class StatusEndpoint(Resource, object):

    def render_GET(self, request):
        return (
            b'\n'.join(sorted(container.encode('utf8') for container in containers_launched)) +
            (b'\n' if containers_launched else b'')  # final newline only if we printed lines
        )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('-p', '--port', type=int, default=8080)
    args = parser.parse_args()

    # start the proxy
    root = DockerReverseProxyResource('/var/run/docker.sock', '')
    root.putChild('', root)
    root.putChild('tracker', StatusEndpoint())

    site = server.Site(root)
    reactor.listenTCP(args.port, site)
    print('Listening on port {}...'.format(args.port))
    reactor.run()


if __name__ == '__main__':
    exit(main())
