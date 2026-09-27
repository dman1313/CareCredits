import socket
import unittest
from scripts.dev import free_port


class DevPortTests(unittest.TestCase):
    def test_free_port_skips_a_bound_preferred_port(self):
        occupied = socket.socket()
        occupied.bind(('127.0.0.1', 0))
        preferred = occupied.getsockname()[1]
        try:
            chosen = free_port(preferred)
            self.assertNotEqual(chosen, preferred)
            self.assertGreaterEqual(chosen, preferred)
        finally:
            occupied.close()
