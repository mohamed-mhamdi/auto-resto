"""Extract reproducible labelled crops from video windows without mixing source splits."""
import argparse
import json
from collections import Counter
from pathlib import Path

import cv2

from benchmark import read_frames, truth_at
from camera import crop


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--source-dir', type=Path, default=Path('recordings'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    clips = json.loads(args.manifest.read_text(encoding='utf-8-sig'))['clips']
    sources = {}
    names = set()
    for clip in clips:
        source = (args.source_dir / clip['file']).resolve()
        split = clip['split']
        if split not in ('train', 'val', 'test') or sources.setdefault(source, split) != split:
            parser.error('Une source complète doit rester dans un seul lot.')
        if not clip['id'].replace('-', '').isalnum() or clip['id'] in names:
            parser.error('Identifiant de clip dupliqué ou invalide.')
        names.add(clip['id'])
    args.out.mkdir(parents=True, exist_ok=False)
    counts = Counter()
    for clip in clips:
        frames = read_frames(args.source_dir / clip['file'], clip['start'], clip['end'], clip.get('every', .5))
        for at, frame in frames:
            if clip.get('size') and clip['size'] != [frame.shape[1], frame.shape[0]]:
                raise ValueError(f'Résolution inattendue : {clip["id"]}')
            for table, settings in clip['tables'].items():
                label = truth_at(settings['labels'], at)
                if label is None:
                    continue
                if label not in ('empty', 'occupied') or not table.isdecimal():
                    parser.error('Étiquette ou numéro de table invalide.')
                folder = args.out / clip['split'] / label
                folder.mkdir(parents=True, exist_ok=True)
                image = crop(frame, settings['region'])
                ok, encoded = cv2.imencode('.jpg', image)
                if not ok:
                    raise ValueError(f'Découpe illisible : {clip["id"]}, {at}s')
                (folder / f'{clip["id"]}-t{table}-{round(at*1000):08}.jpg').write_bytes(encoded.tobytes())
                counts[clip['split'] + '/' + label] += 1
    print(json.dumps(dict(sorted(counts.items())), indent=2))


if __name__ == '__main__':
    main()
