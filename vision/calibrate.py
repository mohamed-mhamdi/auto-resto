import argparse
import json
from pathlib import Path

import cv2

from alignment import Alignment
from camera import open_camera


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tables', nargs='+', type=int, required=True)
    parser.add_argument('--out', type=Path, default=Path('camera.json'))
    parser.add_argument('--seats', nargs='+', type=int,
                        help='Nombre de zones de sièges pour chaque table, dans le même ordre')
    parser.add_argument('--reference', action='store_true', help='Ajouter une zone fixe pour vérifier le cadrage')
    args = parser.parse_args()
    if any(table < 1 for table in args.tables) or len(set(args.tables)) != len(args.tables):
        parser.error('Les numéros de table doivent être positifs et uniques.')
    counts = args.seats or [0] * len(args.tables)
    if len(counts) != len(args.tables) or any(not 0 <= count <= 12 for count in counts):
        parser.error('Donnez un nombre de 0 à 12 zones par table.')
    camera = open_camera()
    ok, frame = camera.read()
    camera.release()
    if not ok:
        parser.error('Impossible de lire la source.')
    height, width = frame.shape[:2]
    scale = min(1, 1150 / width, 700 / height)
    preview = cv2.resize(frame, (round(width * scale), round(height * scale)))
    def select(title):
        x, y, w, h = cv2.selectROI(title, preview, showCrosshair=True)
        cv2.destroyWindow(title)
        if min(w, h) < 5:
            parser.error('Sélection annulée ou trop petite.')
        left, top = round(x * width / preview.shape[1]), round(y * height / preview.shape[0])
        right = round((x + w) * width / preview.shape[1])
        bottom = round((y + h) * height / preview.shape[0])
        return [left, top, right - left, bottom - top]

    boxes, seats = {}, {}
    reference = None
    try:
        for table, count in zip(args.tables, counts):
            boxes[table] = select(f'Table {table} : selectionner table + chaises, puis Entree')
            if count:
                seats[table] = [select(f'Table {table}, siege {seat + 1} : zone tete et epaules du client assis')
                                for seat in range(count)]
        if args.reference:
            region = select('Reference : choisir un mur fixe avec des motifs, hors passage')
            try:
                reference = Alignment.create(frame, region)
            except ValueError as error:
                parser.error(str(error))
    finally:
        cv2.destroyAllWindows()
    args.out.write_text(json.dumps({'size': [width, height], 'tables': boxes, 'seats': seats, 'reference': reference},
                                  indent=2), encoding='utf-8')
    print(f'Zones enregistrées dans {args.out}.')


if __name__ == '__main__':
    main()

