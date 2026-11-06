"""Replay an annotated clip using video time and the same pipeline as the live worker."""
import argparse
import csv
import json
import statistics
import time
from collections import Counter
from pathlib import Path

import cv2

from alignment import Alignment
from pipeline import Pipeline


def read_frames(path, start, end, every):
    capture = cv2.VideoCapture(str(path))
    try:
        fps = capture.get(cv2.CAP_PROP_FPS)
        if not capture.isOpened() or not fps > 0:
            raise ValueError(f'Vidéo illisible : {path}')
        index = round(start * fps)
        capture.set(cv2.CAP_PROP_POS_FRAMES, index)
        next_sample = start
        while index / fps < end:
            ok, frame = capture.read()
            if not ok:
                break
            at = index / fps
            if at + .5 / fps >= next_sample:
                yield at, frame
                next_sample += every
            index += 1
    finally:
        capture.release()


def truth_at(windows, at):
    return next((state for start, end, state in windows if start <= at < end), None)


def compare(truth, predicted):
    if truth is None:
        return None
    return f'{truth}->{predicted or "unknown"}'


def draw(frame, people, boxes, raw, confirmed):
    for person in people:
        x, y, w, h = map(round, person.box)
        cv2.rectangle(frame, (x, y), (x+w, y+h), (220, 190, 50), 2)
    for table, (x, y, w, h) in boxes.items():
        state = confirmed[table] or '?'
        color = {'occupied': (50, 100, 250), 'empty': (60, 210, 90)}.get(state, (160, 160, 160))
        cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
        label = f'T{table} {raw[table] or "?"} / {state}'
        cv2.putText(frame, label, (x, max(y - 5, 18)), cv2.FONT_HERSHEY_SIMPLEX, .5, color, 2)
    return frame


def evaluate(specification, source_dir, pipeline_factory, output, every=1, preview=False):
    output.mkdir(parents=True, exist_ok=True)
    totals = Counter()
    reports = []
    with (output / 'frames.csv').open('w', newline='', encoding='utf-8') as stream:
        csv_writer = csv.writer(stream)
        csv_writer.writerow(('clip', 'second', 'table', 'truth', 'raw', 'confirmation', 'last_confirmed'))
        for clip in specification['clips']:
            boxes = {int(table): settings['region'] for table, settings in clip['tables'].items()}
            truth = {int(table): settings['labels'] for table, settings in clip['tables'].items()}
            seats = {int(table): settings['seats'] for table, settings in clip['tables'].items()
                     if settings.get('seats')}
            pipeline = pipeline_factory(boxes, seats)
            stats = Counter()
            timings = []
            alignment = None
            rejected = 0
            states = {}
            predicted_events = []
            expected_events = []
            for table, windows in truth.items():
                for left, right in zip(windows, windows[1:]):
                    if left[1] == right[0] and left[2] != right[2]:
                        expected_events.append((table, right[0], right[1], right[2]))
            video = None
            try:
                for at, frame in read_frames(source_dir / clip['file'], clip['start'], clip['end'], every):
                    expected_size = clip.get('size')
                    if expected_size and expected_size != [frame.shape[1], frame.shape[0]]:
                        raise ValueError(f'Résolution inattendue : {clip["id"]}')
                    start = time.perf_counter()
                    region = clip.get('reference_region')
                    if region and alignment is None:
                        alignment = Alignment(Alignment.create(frame, region))
                    if alignment is not None and not alignment.good(frame):
                        rejected += 1
                        pipeline.reset()
                        people, raw, confirmed = [], dict.fromkeys(boxes), dict.fromkeys(boxes)
                    else:
                        people, raw, confirmed = pipeline.update(frame, at)
                    timings.append(1000 * (time.perf_counter() - start))
                    for table in boxes:
                        label = truth_at(truth[table], at)
                        for name, value in [('raw', raw[table]), ('state', confirmed[table] or states.get(table))]:
                            comparison = compare(label, value)
                            if comparison:
                                stats[name + ':' + comparison] += 1
                        if confirmed[table] and states.get(table) != confirmed[table]:
                            states[table] = confirmed[table]
                            predicted_events.append((table, round(at, 3), states[table]))
                        csv_writer.writerow((clip['id'], round(at, 3), table, label, raw[table],
                                             confirmed[table], states.get(table)))
                    if preview:
                        annotated = draw(frame, people, boxes, raw, confirmed)
                        width = min(960, frame.shape[1])
                        display = cv2.resize(annotated, (width, round(frame.shape[0] * width / frame.shape[1])))
                        if video is None:
                            video = cv2.VideoWriter(str(output / (clip['id'] + '.mp4')),
                                                    cv2.VideoWriter_fourcc(*'mp4v'), 1 / every,
                                                    (display.shape[1], display.shape[0]))
                            if not video.isOpened():
                                raise RuntimeError('Encodeur MP4 indisponible.')
                        video.write(display)
            finally:
                if video is not None:
                    video.release()
            if not timings:
                raise ValueError(f'Aucune image décodée : {clip["id"]}')
            delays = []
            for table, begin, end, state in expected_events:
                match = next((at for t, at, s in predicted_events if t == table and s == state and begin <= at < end), None)
                delays.append({'table': table, 'state': state, 'at': begin,
                               'delay': round(match - begin, 3) if match is not None else None})
            totals.update(stats)
            reports.append(dict(id=clip['id'], frames=len(timings), rejected_alignment=rejected,
                                median_ms=round(statistics.median(timings), 2),
                                p95_ms=round(sorted(timings)[int(.95 * (len(timings) - 1))], 2),
                                counts=dict(stats), predicted_events=predicted_events, labelled_transitions=delays))
    summary = dict(clips=reports, totals=dict(totals))
    (output / 'metrics.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser(description='Rejouer un manifeste annoté et calculer les métriques.')
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--source-dir', type=Path, default=Path('recordings'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--detector', type=Path, default=Path('models/yolox_s.onnx'))
    parser.add_argument('--model', type=Path)
    parser.add_argument('--crop-only', action='store_true')
    parser.add_argument('--enter', type=float, default=5)
    parser.add_argument('--exit', type=float, default=30)
    parser.add_argument('--stable', type=float, default=1.5,
                        help='Durée minimale de stabilité avant confirmation')
    parser.add_argument('--every', type=float, default=.5)
    parser.add_argument('--preview', action='store_true')
    args = parser.parse_args()
    if not .25 <= args.every <= 2 or min(args.enter, args.exit, args.stable) <= 0 or (args.crop_only and not args.model):
        parser.error('Cadence, seuils ou modèle de découpe invalides.')
    spec = json.loads(args.manifest.read_text(encoding='utf-8-sig'))
    result = evaluate(spec, args.source_dir,
                      lambda boxes, seats: Pipeline(boxes, None if args.crop_only else args.detector,
                                                    args.model, enter=args.enter, exit=args.exit,
                                                    stable=args.stable, seats=seats),
                      args.out, args.every, args.preview)
    print(json.dumps(result['totals'], indent=2))


if __name__ == '__main__':
    main()

