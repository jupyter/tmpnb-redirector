#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Redirect service for multiple tmpnb instances on different hosts.

Requests are redirected to tmpnb instances, using the available capacity as a weight.

Add hosts for instances with POST requests to the api_port

    curl -X POST -d '{"host": "https://tmpnb.org"}' http://127.0.0.1:9001/hosts

Remove them with DELETE

    curl -X DELETE -d '{"host": "https://tmpnb.org"}' http://127.0.0.1:9001/hosts

"""

import json
import random

try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse

try:
    # py3
    from http.client import responses
except ImportError:
    from httplib import responses

import tornado
import tornado.options
from tornado.log import app_log
from tornado.web import RequestHandler

from tornado import gen, web
from tornado import ioloop

from tornado.httpclient import HTTPRequest, HTTPError, AsyncHTTPClient

AsyncHTTPClient.configure("tornado.curl_httpclient.CurlAsyncHTTPClient")

@gen.coroutine
def update_stats(stats):
    """Get updated stats for each host
    
    If a host fails to reply,
    assume it is is down and assign it zero availability and capacity
    """

    http_client = AsyncHTTPClient()
    futures = {}
    for host in stats.keys():
        app_log.debug("Checking stats on %s" % host)
        req = HTTPRequest(host + '/stats')
        futures[host] = http_client.fetch(req)
    
    for host, f in futures.items():
        try:
            reply = yield f
            data = json.loads(reply.body.decode('utf8'))
        except Exception as e:
            app_log.error("Failed to get stats for %s: %s", host, e)
            if host in stats:
                stats[host] = {'available': 0, 'capacity': 0, 'down': True}
        else:
            app_log.debug("Got stats from %s: %s", host, data)
            if host in stats:
                stats[host] = data


class HostsAPIHandler(RequestHandler):
    """API handler for adding or removing redirect targets"""
    def _get_host(self):
        try:
            host = json.loads(self.request.body.decode('utf8', 'replace'))['host']
            scheme = urlparse(host).scheme
            if(scheme == 'http' or scheme == 'https'):
                return host

            raise Exception("Invalid host, must include http or https")

        except Exception as e:
            app_log.error("Bad host %s", e)
            raise web.HTTPError(400)
        
    def post(self):
        host = self._get_host()
        self.stats.setdefault(host, {'available': 0, 'capacity': 0, 'down': True})
        ioloop.IOLoop.current().add_callback(lambda : update_stats(self.stats))
    
    def delete(self):
        host = self._get_host()
        self.stats.pop(host)
    
    @property
    def stats(self):
        return self.settings['stats']

class StatsHandler(RequestHandler):
    def get(self):
        """Returns some statistics/metadata about the tmpnb servers"""
        response = {
                'available': sum(s['available'] for s in self.stats.values()),
                'capacity': sum(s['capacity'] for s in self.stats.values()),
                'hosts': self.stats,
                'version': '0.0.1',
        }
        self.write(response)

    @property
    def stats(self):
        return self.settings['stats']

class RerouteHandler(RequestHandler):
    """Redirect based on load"""
    
    def write_error(self, status_code, **kwargs):
        exc_info = kwargs.get('exc_info')
        message = ''
        status_message = responses.get(status_code, 'Unknown HTTP Error')
        if exc_info:
            exception = exc_info[1]
            # get the custom message, if defined
            try:
                message = exception.log_message % exception.args
            except Exception:
                pass

            # construct the custom reason, if defined
            reason = getattr(exception, 'reason', '')
            if reason:
                status_message = reason

        self.set_header('Content-Type', 'text/html')
        self.render("error.html",
            status_code=status_code,
            status_message=status_message,
            message=message,
        )

    def get(self):
        up = {host:stats for host,stats in self.stats.items() if not stats.get('down')}
        if not up:
            if self.stats:
                msg = "All redirect targets are down"
            else:
                msg = "No redirect targets"
            raise web.HTTPError(503, msg)

        key = 'available'
        total = sum(s[key] for s in up.values())
        if not total:
            # everybody's full, redirect based on capacity only
            key = 'capacity'
            total = sum(s[key] for s in up.values())
        choice = random.randint(0, total)
        cumsum = 0
        for host, stats in up.items():
            cumsum += stats[key]
            if cumsum >= choice:
                break
        self.redirect(host + self.request.path, permanent=False)
    
    @property
    def stats(self):
        return self.settings['stats']

def main():
    tornado.options.define('stats_period', default=60,
        help="Interval (s) for checking capacity of servers."
    )
    tornado.options.define('port', default=9000,
        help="port for the redirect server to listen on"
    )
    tornado.options.define('api_port', default=9001,
        help="port for the REST API used"
    )
    tornado.options.define('api_ip', default='127.0.0.1',
        help="IP address for the REST API"
    )

    tornado.options.parse_command_line()
    opts = tornado.options.options

    handlers = [
        (r"/stats", StatsHandler),
        (r'/.*', RerouteHandler),
    ]
    
    api_handlers = [
        (r'/hosts', HostsAPIHandler),
    ]
    
    # the stats dict, keyed by host
    # the values are the most recent stats for each host
    stats = {}

    settings = dict(
        stats=stats,
        xsrf_cookies=True,
        debug=True,
        autoescape=None,
    )
    
    stats_poll_ms = 1e3 * opts.stats_period
    app_log.info("Polling server stats every %i seconds", opts.stats_period)
    poller = ioloop.PeriodicCallback(lambda : update_stats(stats), stats_poll_ms)
    poller.start()
    
    app_log.info("Listening on {}".format(opts.port))
    app_log.info("Hosts API on {}:{}".format(opts.api_ip, opts.api_port))
    app = tornado.web.Application(handlers, **settings)
    app.listen(opts.port)
    
    api_app = tornado.web.Application(api_handlers, stats=stats)
    api_app.listen(opts.api_port, opts.api_ip)
    
    ioloop.IOLoop.instance().start()

if __name__ == "__main__":
    main()
