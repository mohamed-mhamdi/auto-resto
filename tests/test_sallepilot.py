import base64
import io
import json
import tempfile
import time
import unittest
from pathlib import Path

from server import handler
from store import Conflict, Store
from vision.confirmation import Confirmation


class MemorySocket:
    def __init__(self, request):
        self.input = io.BytesIO(request)
        self.output = bytearray()

    def settimeout(self, timeout):
        pass

    def makefile(self, mode, *args):
        return self.input

    def sendall(self, body):
        self.output.extend(body)


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'test.db'
        self.store = Store(self.path, 5)
        self.store.seed(3)

    def exchange(self, method, path, auth='', body=None, *, auto=True, departure=False):
        data = b'' if body is None else json.dumps(body).encode()
        request = (f'{method} {path} HTTP/1.1\r\nHost: localhost\r\nAuthorization: {auth}\r\n'
                   f'Content-Type: application/json\r\nContent-Length: {len(data)}\r\n\r\n').encode() + data
        socket = MemorySocket(request)
        api = handler(self.store, False, 'Test', 'private password', 'camera test key', auto, departure)
        api(socket, ('local', 0), None)
        head, payload = bytes(socket.output).split(b'\r\n\r\n', 1)
        return int(head.split()[1]), payload

    def test_http_staff_and_camera(self):
        staff = 'Basic ' + base64.b64encode(b'equipe:private password').decode()
        vision = 'Bearer camera test key'
        self.assertEqual(self.exchange('GET', '/')[0], 401)
        status, page = self.exchange('GET', '/', staff)
        self.assertEqual(status, 200)
        self.assertIn(b'SallePilot', page)
        self.assertEqual(self.exchange('POST', '/api/vision', staff, {'1': 'occupied'})[0], 401)
        self.assertEqual(self.exchange('POST', '/api/vision', vision, {'99': 'occupied'})[0], 400)
        self.assertEqual(self.exchange('POST', '/api/vision', vision, {'1': 'occupied'})[0], 200)
        _, payload = self.exchange('GET', '/api/snapshot', staff)
        self.assertEqual(json.loads(payload)['tables'][0]['state'], 'waiting')
        action = dict(table=1, revision=1, action='serve')
        self.assertEqual(self.exchange('POST', '/api/action', staff, action)[0], 200)
        self.assertEqual(self.exchange('POST', '/api/action', staff, action)[0], 409)
        self.assertIn(b'table_id,seated', self.exchange('GET', '/api/export', staff)[1])

    def test_observation_is_audit_only_and_departures_require_opt_in(self):
        staff = 'Basic ' + base64.b64encode(b'equipe:private password').decode()
        vision = 'Bearer camera test key'
        status, _ = self.exchange('POST', '/api/vision', vision, {'1': 'occupied'}, auto=False)
        self.assertEqual(status, 200)
        self.assertEqual(self.store.snapshot()['tables'][0]['state'], 'free')
        self.assertIn(b'occupied,free', self.exchange('GET', '/api/vision-export', staff)[1])
        self.exchange('POST', '/api/vision', vision, {'1': 'occupied'})
        self.exchange('POST', '/api/vision', vision, {'1': 'empty'})
        self.assertEqual(self.store.snapshot()['tables'][0]['state'], 'waiting')
        self.exchange('POST', '/api/vision', vision, {'1': 'empty'}, departure=True)
        self.assertEqual(self.store.snapshot()['tables'][0]['state'], 'cleaning')

    def test_restore_recovers_service_without_creating_visit(self):
        self.store.observe({1: 'occupied'})
        self.store.action(1, 'serve', 1)
        self.store.observe({1: 'empty'})
        self.store.action(1, 'restore', 3)
        self.assertEqual(self.store.snapshot()['tables'][0]['state'], 'served')
        self.assertEqual(len(self.store.visits()), 1)
        self.assertIsNone(self.store.visits()[0]['departed'])

    def test_visit_survives_restart_and_alert_is_unique(self):
        self.store.observe({1: 'occupied'})
        with self.store.transaction() as db:
            db.execute('UPDATE visits SET seated=?', (time.time() - 30,))
        restarted = Store(self.path, 5)
        self.assertTrue(restarted.snapshot()['tables'][0]['alerted'])
        self.assertEqual(sum(e['action'] == 'alert' for e in restarted.snapshot()['history']), 1)
        restarted.action(1, 'ack', 1)
        with self.assertRaises(Conflict):
            restarted.action(1, 'serve', 1)
        restarted.action(1, 'serve', 2)
        restarted.observe({1: 'empty'})
        self.assertEqual(restarted.snapshot()['tables'][0]['state'], 'cleaning')
        restarted.observe({1: 'occupied'})
        restarted.action(1, 'ready', 4)
        self.assertIsNotNone(restarted.visits()[0]['ready'])
        self.assertEqual(restarted.snapshot()['tables'][0]['state'], 'free')

    def test_outage_and_manual_override(self):
        self.store.action(1, 'seat', 0)
        self.store.observe({1: 'empty'})
        with self.store.transaction() as db:
            db.execute('UPDATE cameras SET seen=?', (time.time() - 60,))
        table = self.store.snapshot()['tables'][0]
        self.assertEqual((table['state'], table['online']), ('waiting', 0))


class VisionTimingTest(unittest.TestCase):
    def test_gaps_and_uncertainty_break_confirmation(self):
        model = Confirmation(2, 3)
        self.assertIsNone(model.update('occupied', 0))
        self.assertEqual(model.update('occupied', 2), 'occupied')
        self.assertIsNone(model.update('empty', 3))
        self.assertIsNone(model.update(None, 4))
        self.assertIsNone(model.update('empty', 5))
        self.assertIsNone(model.update('empty', 10))
        self.assertEqual(model.update('empty', 13), 'empty')


if __name__ == '__main__':
    unittest.main()

