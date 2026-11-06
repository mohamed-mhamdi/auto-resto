import json
import os

import cv2


def open_camera():
    source = os.environ.get('SALLEPILOT_SOURCE', '0')
    if source.isdecimal():
        return cv2.VideoCapture(int(source))
    if source.lower().startswith(('rtsp://', 'rtsps://')):
        return cv2.VideoCapture(source, cv2.CAP_FFMPEG,
                                [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 4000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 4000])
    return cv2.VideoCapture(source)


def load_regions(path):
    settings = json.loads(path.read_text(encoding='utf-8-sig'))
    return settings['size'], {int(table): box for table, box in settings['tables'].items()}


def load_seats(path, regions, size):
    settings = json.loads(path.read_text(encoding='utf-8-sig'))
    seats = {int(table): zones for table, zones in settings.get('seats', {}).items()}
    width, height = size
    for table, zones in seats.items():
        if table not in regions or not zones:
            raise ValueError('Sièges associés à une table inconnue ou liste vide.')
        for x, y, w, h in zones:
            if x < 0 or y < 0 or min(w, h) < 5 or x + w > width or y + h > height:
                raise ValueError(f'Zone de siège invalide (table {table}).')
    return seats


def crop(frame, box):
    x, y, width, height = box
    return frame[y:y+height, x:x+width]
