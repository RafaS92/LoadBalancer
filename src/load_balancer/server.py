"""Shared threaded HTTP server behavior."""

from http.server import ThreadingHTTPServer


class GracefulThreadingHTTPServer(ThreadingHTTPServer):
    """Threaded server that waits for active requests during close."""

    daemon_threads = False
