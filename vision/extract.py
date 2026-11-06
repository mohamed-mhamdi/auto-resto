import argparse
import re
from pathlib import Path

import cv2

from camera import crop, load_regions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('video', type=Path)
    parser.add_argument('--config', type=Path, default=Path('camera.json'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--every', type=float, default=2)
    args = parser.parse_args()
    if args.every <= 0:
        parser.error('Intervalle positif requis.')
    size, boxes = load_regions(args.config)
    camera = cv2.VideoCapture(str(args.video))
    fps = camera.get(cv2.CAP_PROP_FPS)
    if not camera.isOpened() or not fps > 0:
        parser.error('Vidéo illisible.')
    args.out.mkdir(parents=True, exist_ok=False)
    interval = max(1, round(fps * args.every))
    stem = re.sub(r'[^a-zA-Z0-9_-]', '_', args.video.stem)
    frame_number = 0
    try:
        while True:
            ok, frame = camera.read()
            if not ok:
                break
            if [frame.shape[1], frame.shape[0]] != size:
                parser.error('Résolution différente du calibrage.')
            if frame_number % interval == 0:
                for table, box in boxes.items():
                    success, encoded = cv2.imencode('.jpg', crop(frame, box))
                    if not success:
                        raise RuntimeError('Impossible d’encoder une découpe.')
                    (args.out / f'{stem}_{frame_number:07}_T{table}.jpg').write_bytes(encoded.tobytes())
            frame_number += 1
    finally:
        camera.release()
    print(f'Découpes enregistrées dans {args.out}.')

if __name__ == '__main__':
    main()

