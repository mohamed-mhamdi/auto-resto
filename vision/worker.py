import argparse
import base64
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import cv2

from alignment import Alignment
from camera import load_regions, load_seats, open_camera
from pipeline import FeedWatch, Pipeline


def send(url, key, observations, endpoint='/api/vision'):
    request = urllib.request.Request(
        url.rstrip('/') + endpoint, data=json.dumps(observations).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {key}'},
    )
    with urllib.request.urlopen(request, timeout=2) as response:
        response.read()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=Path('camera.json'))
    parser.add_argument('--detector', type=Path, default=Path('models/yolox_s.onnx'))
    parser.add_argument('--model', type=Path, help='Classificateur local facultatif')
    parser.add_argument('--crop-only', action='store_true', help='Ancien mode, exige --model')
    parser.add_argument('--url', default='http://127.0.0.1:8765')
    parser.add_argument('--margin', type=float, default=.2)
    parser.add_argument('--enter', type=float, default=5)
    parser.add_argument('--exit', type=float, default=30)
    parser.add_argument('--confidence', type=float, default=.22)
    parser.add_argument('--strong', type=float, default=.48)
    parser.add_argument('--preview', action='store_true', help='Activer l’aperçu vidéo local')
    parser.add_argument('--replay', type=Path, help='Lire un fichier dans le serveur de démonstration')
    args = parser.parse_args()
    key = os.environ.get('SALLEPILOT_CAMERA_KEY', '')
    if len(key) < 24 or not 0 <= args.margin <= 5 or min(args.enter, args.exit) <= 0:
        parser.error('Clé caméra et seuils valides requis.')
    if not 0 < args.confidence <= args.strong <= 1 or (args.crop_only and not args.model):
        parser.error('Seuils de détection invalides ou modèle de découpe absent.')
    size, boxes = load_regions(args.config)
    if not boxes or any(x < 0 or y < 0 or min(w, h) < 5 or x + w > size[0] or y + h > size[1]
                        for x, y, w, h in boxes.values()):
        parser.error('Zones de caméra invalides.')
    pipeline = Pipeline(boxes, None if args.crop_only else args.detector, args.model, args.margin,
                        args.enter, args.exit, args.confidence, args.strong,
                        seats=load_seats(args.config, boxes, size))
    reference = json.loads(args.config.read_text(encoding='utf-8-sig')).get('reference')
    alignment = Alignment(reference) if reference else None
    source = os.environ.get('SALLEPILOT_SOURCE', '0')
    if not args.replay and not source.isdecimal() and not source.lower().startswith(('rtsp://', 'rtsps://')):
        parser.error('Utilisez une webcam ou RTSP en direct. Pour un fichier vidéo : vision/benchmark.py.')
    while True:
        camera = cv2.VideoCapture(str(args.replay)) if args.replay else open_camera()
        fps = camera.get(cv2.CAP_PROP_FPS) if args.replay else 0
        if args.replay and not fps > 0:
            parser.error('Vidéo de replay illisible.')
        pipeline.reset()
        watch = FeedWatch()
        last_sample = 0
        was_frozen = False
        try:
            while True:
                ok, frame = camera.read()
                if not ok:
                    break
                if args.replay:
                    time.sleep(1 / fps)
                if [frame.shape[1], frame.shape[0]] != size:
                    parser.error('Résolution modifiée : recalibrez la caméra.')
                now = time.monotonic()
                if now - last_sample < .48:
                    continue
                last_sample = now
                if not watch.update(frame, now) or (alignment is not None and not alignment.good(frame)):
                    if not was_frozen:
                        print('Image figée, exposition ou cadrage invalide, envoi suspendu.', flush=True)
                        was_frozen = True
                    pipeline.reset()
                    continue
                was_frozen = False
                _, raw, confirmed = pipeline.update(frame, now)
                try:
                    if not args.replay:
                        send(args.url, key, confirmed)
                    if args.preview or args.replay:
                        width, height = size
                        scale = min(1, 960 / width)
                        image = cv2.resize(frame, (round(width * scale), round(height * scale)))
                        encoded, jpeg = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 70])
                        if encoded:
                            regions = {table: {'box': [x / width, y / height, w / width, h / height],
                                               'detected': raw[table]}
                                       for table, (x, y, w, h) in boxes.items()}
                            send(args.url, key, {'jpeg': base64.b64encode(jpeg).decode(),
                                                 'regions': regions, 'replay': bool(args.replay)},
                                 '/api/vision-preview')
                except urllib.error.HTTPError as error:
                    if error.code in (400, 401, 404):
                        parser.error(f'API caméra refusée (HTTP {error.code}). Vérifiez clé et tables.')
                    pipeline.reset()
                except (OSError, urllib.error.URLError):
                    pipeline.reset()
        finally:
            camera.release()
        print('Flux perdu, reconnexion dans trois secondes.', flush=True)
        time.sleep(3)


if __name__ == '__main__':
    main()

