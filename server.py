import argparse
import base64
import csv
import hmac
import io
import json
import os
import sqlite3
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from store import Conflict, Store


ROOT = Path(__file__).resolve().parent
ASSETS = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'),
          '/style.css': ('style.css', 'text/css'), '/favicon.svg': ('favicon.svg', 'image/svg+xml'),
          '/video.js': ('video.js', 'text/javascript')}


def handler(store, demo, name, password, camera_key, vision_auto=False, vision_departure=False):
    staff_auth = 'Basic ' + base64.b64encode(f'equipe:{password}'.encode()).decode()
    vision_auth = f'Bearer {camera_key}'
    preview = None
    preview_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        timeout = 8

        def log_message(self, format, *args):
            pass

        def send_data(self, status, body, kind, headers=None):
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy',
                             "default-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def json(self, status, payload, headers=None):
            self.send_data(status, json.dumps(payload).encode(), 'application/json', headers)

        def authorized(self, vision=False):
            provided = self.headers.get('Authorization', '').encode()
            if vision:
                if camera_key and hmac.compare_digest(provided, vision_auth.encode()):
                    return True
                self.json(401, {'error': 'Clé caméra requise.'})
            elif demo or hmac.compare_digest(provided, staff_auth.encode()):
                return True
            else:
                self.json(401, {'error': 'Connexion requise.'},
                          {'WWW-Authenticate': 'Basic realm="SallePilot"'})
            return False

        def do_GET(self):
            if not self.authorized():
                return
            path = urlsplit(self.path).path
            if path in ASSETS:
                file, kind = ASSETS[path]
                self.send_data(200, (ROOT / 'web' / file).read_bytes(), kind + '; charset=utf-8')
            elif path == '/api/snapshot':
                self.json(200, {**store.snapshot(), 'demo': demo, 'name': name, 'vision_auto': vision_auto,
                                'vision_departure': vision_departure})
            elif path == '/api/report':
                self.json(200, store.visits(time.time() - 7 * 86400))
            elif path == '/api/video':
                with preview_lock:
                    packet = preview
                if packet is None or time.monotonic() - packet[0] > 4:
                    self.json(200, {'online': False, 'demo': demo})
                else:
                    self.json(200, {'online': True, 'demo': demo, **packet[1]})
            elif path in ('/api/export', '/api/vision-export'):
                vision_log = path == '/api/vision-export'
                if vision_log:
                    fields = ['table_id', 'at', 'observation', 'staff_state']
                    rows = store.vision_log(time.time() - 7 * 86400)
                else:
                    fields = ['id', 'table_id', 'seated', 'acknowledged', 'served', 'departed', 'ready', 'alerted']
                    rows = store.visits()
                buffer = io.StringIO()
                writer = csv.DictWriter(buffer, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
                filename = 'sallepilot-vision.csv' if vision_log else 'sallepilot-visites.csv'
                self.send_data(200, buffer.getvalue().encode(), 'text/csv; charset=utf-8',
                               {'Content-Disposition': f'attachment; filename="{filename}"'})
            else:
                self.json(404, {'error': 'Page inconnue.'})

        def do_POST(self):
            nonlocal preview
            path = urlsplit(self.path).path
            if path not in ('/api/vision', '/api/action', '/api/vision-preview'):
                self.json(404, {'error': 'Action inconnue.'})
                return
            if not self.authorized(vision=path != '/api/action'):
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                limit = 600000 if path == '/api/vision-preview' else 16384
                if self.headers.get_content_type() != 'application/json' or not 0 < size <= limit:
                    raise ValueError('Requête JSON invalide.')
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError('Objet JSON attendu.')
                if path == '/api/vision-preview':
                    jpeg, regions = data.get('jpeg'), data.get('regions')
                    if (not isinstance(jpeg, str) or not isinstance(regions, dict) or not 0 < len(regions) <= 100
                            or data.get('replay', False) is not demo):
                        raise ValueError('Aperçu invalide.')
                    if not base64.b64decode(jpeg, validate=True).startswith(b'\xff\xd8'):
                        raise ValueError('Image JPEG requise.')
                    for table, region in regions.items():
                        if not table.isdecimal() or not isinstance(region, dict):
                            raise ValueError('Zone invalide.')
                        box = region.get('box')
                        if (not isinstance(box, list) or len(box) != 4
                                or any(type(value) not in (int, float) or not 0 <= value <= 1 for value in box)
                                or region.get('detected') not in ('empty', 'occupied', None)):
                            raise ValueError('Zone invalide.')
                    with preview_lock:
                        preview = (time.monotonic(), {'jpeg': jpeg, 'regions': regions})
                elif path == '/api/action':
                    table, revision, action = data.get('table'), data.get('revision'), data.get('action')
                    if type(table) is not int or type(revision) is not int or not isinstance(action, str):
                        raise ValueError('Action invalide.')
                    store.action(table, action, revision)
                else:
                    observations = {int(key): value for key, value in data.items()}
                    if any(value not in ('empty', 'occupied', None) for value in observations.values()):
                        raise ValueError('Observation invalide.')
                    store.observe(observations, automatic=vision_auto and not demo,
                                  automatic_departure=vision_departure)
                self.json(200, {'ok': True})
            except Conflict as error:
                self.json(409, {'error': str(error)})
            except (ValueError, sqlite3.IntegrityError):
                self.json(400, {'error': 'Vérifiez les paramètres et les numéros de table.'})

    return Handler


def main():
    parser = argparse.ArgumentParser(description='Serveur local SallePilot')
    parser.add_argument('--demo', action='store_true')
    parser.add_argument('--vision-auto', action='store_true',
                        help='Autoriser les arrivées automatiques après recette')
    parser.add_argument('--vision-auto-departure', action='store_true',
                        help='Autoriser aussi les départs automatiques après recette')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--tables', type=int, default=8)
    parser.add_argument('--wait', type=int, default=300, help='Seuil alerte en secondes')
    parser.add_argument('--name', default='Mon restaurant')
    parser.add_argument('--db', type=Path)
    args = parser.parse_args()
    if not 1 <= args.tables <= 100 or not 1 <= args.wait <= 7200:
        parser.error('Tables : 1 à 100. Seuil : 1 à 7200 secondes.')
    password = os.environ.get('SALLEPILOT_PASSWORD', '')
    key = os.environ.get('SALLEPILOT_CAMERA_KEY', '')
    if not args.demo and len(password) < 16:
        parser.error('Définissez SALLEPILOT_PASSWORD (16 caractères minimum).')
    if key and len(key) < 24:
        parser.error('SALLEPILOT_CAMERA_KEY doit avoir au moins 24 caractères.')
    if args.vision_auto and (args.demo or not key):
        parser.error('Le mode automatique exige une installation réelle et une clé caméra.')
    if args.vision_auto_departure and not args.vision_auto:
        parser.error('Les départs automatiques exigent --vision-auto.')
    store = Store(args.db or ROOT / 'data' / ('demo.db' if args.demo else 'restaurant.db'), args.wait)
    store.seed(args.tables, args.demo)
    api = handler(store, args.demo, args.name, password, key, args.vision_auto, args.vision_auto_departure)
    stopped = threading.Event()

    def alert_loop():
        while not stopped.wait(2):
            try:
                store.record_alerts()
            except sqlite3.Error as error:
                print(f'Journal des alertes : {error}', file=sys.stderr, flush=True)

    with ThreadingHTTPServer(('127.0.0.1', args.port), api) as server:
        thread = threading.Thread(target=alert_loop, daemon=True)
        thread.start()
        try:
            print(f'SallePilot : http://127.0.0.1:{args.port}', flush=True)
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            stopped.set()
            thread.join()


if __name__ == '__main__':
    main()
