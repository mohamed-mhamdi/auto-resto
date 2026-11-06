"""Start an isolated demo room and replay a licensed sample through the vision worker."""
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    url = 'http://127.0.0.1:8768'
    environment = {**os.environ, 'SALLEPILOT_CAMERA_KEY': secrets.token_urlsafe(32)}
    with subprocess.Popen([sys.executable, 'server.py', '--demo', '--port', '8768',
                           '--db', 'data/video-replay.db'], cwd=root, env=environment) as server:
        try:
            for _ in range(40):
                if server.poll() is not None:
                    raise SystemExit('Le serveur de replay a échoué. Vérifiez le port 8768.')
                try:
                    with urllib.request.urlopen(url + '/api/video', timeout=.5):
                        break
                except (OSError, urllib.error.URLError):
                    time.sleep(.25)
            else:
                raise SystemExit('Le serveur de replay ne répond pas.')
            if '--no-browser' not in sys.argv:
                webbrowser.open(url + '/#video')
            subprocess.call([sys.executable, 'vision/worker.py', '--url', url,
                             '--replay', 'evaluation/replay-camera.mp4',
                             '--config', 'evaluation/replay-camera.json'], cwd=root, env=environment)
        except KeyboardInterrupt:
            pass
        finally:
            if server.poll() is None:
                server.terminate()


if __name__ == '__main__':
    main()
