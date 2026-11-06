"""Replay real frames through the detector and an isolated local HTTP API."""
import argparse
import base64
import json
import secrets
import sys
import tempfile
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'vision'))

from benchmark import read_frames
from ops.backup import backup
from pipeline import Pipeline
from server import handler
from store import Store
from worker import send


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=Path('recordings/cheese-mites.mp4'))
    args = parser.parse_args()
    password, key = secrets.token_urlsafe(20), secrets.token_urlsafe(30)
    auth = 'Basic ' + base64.b64encode(f'equipe:{password}'.encode()).decode()
    pipeline = Pipeline({1: [0, 98, 288, 366]}, ROOT / 'models' / 'yolox_s.onnx')
    with tempfile.TemporaryDirectory() as directory:
        db = Path(directory) / 'integration.db'
        store = Store(db)
        store.seed(1)
        with ThreadingHTTPServer(('127.0.0.1', 0), handler(store, False, 'Recette', password, key, True)) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f'http://127.0.0.1:{server.server_port}'

            def staff(path, body=None):
                data = json.dumps(body).encode() if body is not None else None
                req = urllib.request.Request(url + path, data=data,
                                             headers={'Authorization': auth, 'Content-Type': 'application/json'})
                with urllib.request.urlopen(req, timeout=5) as response:
                    return response.read()

            try:
                first = None
                for at, frame in read_frames(args.source, 6, 25, .5):
                    _, _, states = pipeline.update(frame, at)
                    send(url, key, states)
                    if states[1] == 'occupied' and first is None:
                        first = at
                current = json.loads(staff('/api/snapshot'))['tables'][0]
                assert first is not None and current['state'] == 'waiting' and current['online']
                for action in ('ack', 'serve', 'leave', 'ready'):
                    staff('/api/action', {'table': 1, 'revision': current['revision'], 'action': action})
                    current = json.loads(staff('/api/snapshot'))['tables'][0]
                assert current['state'] == 'free'
                assert b'table_id,seated' in staff('/api/export')
                copy = Path(directory) / 'copy.db'
                backup(db, copy)
                visits = Store(copy).visits()
                assert len(visits) == 1 and visits[0]['ready'] is not None and visits[0]['served'] is not None
                print(f'Vidéo > ONNX > API > SQLite : présence confirmée à {first:.2f}s du film.')
                print('Parcours équipe, CSV et restauration : OK.')
            finally:
                server.shutdown()
                thread.join()


if __name__ == '__main__':
    main()

