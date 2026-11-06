import argparse
from pathlib import Path

import cv2
import numpy as np

from model import CLASSES, predict, prepare


def load(path):
    features, labels = [], []
    for label, name in enumerate(CLASSES):
        files = sorted(file for file in (path / name).glob('*')
                       if file.suffix.lower() in ('.png', '.jpg', '.jpeg'))
        if not files:
            raise ValueError(f'Aucune image dans {path / name}')
        for file in files:
            image = cv2.imdecode(np.frombuffer(file.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError(f'Image illisible : {file}')
            features.append(prepare(image))
            labels.append(label)
    return np.stack(features), np.array(labels, dtype=np.int32)


def evaluate(model, features, labels, margin):
    matrix = np.zeros((2, 3), dtype=int)
    for label, prediction in zip(labels, predict(model, features, margin)):
        matrix[label, 2 if prediction is None else CLASSES.index(prediction)] += 1
    score = (np.diag(matrix[:, :2]) / matrix.sum(axis=1)).mean()
    return score, matrix.tolist()


def train(dataset, output, margin):
    features, labels = load(dataset / 'train')
    validation = load(dataset / 'val')
    counts = np.bincount(labels)
    best = None
    weights_by_class = len(labels) / (2 * counts)
    for penalty in (.0001, .001, .01):
        weights = np.zeros(features.shape[1], dtype=np.float32)
        bias = 0.
        for step in range(400):
            logits = np.clip(features @ weights + bias, -25, 25)
            errors = (1 / (1 + np.exp(-logits)) - labels) * weights_by_class[labels]
            weights -= .15 * (features.T @ errors / len(labels) + penalty * weights)
            bias -= .15 * errors.mean()
        model = {'weights': weights, 'bias': bias}
        score, matrix = evaluate(model, *validation, margin)
        print(f'Régularisation={penalty} · rappel moyen {score:.1%} · {matrix}')
        if best is None or score > best[0]:
            best = score, model
    with output.open('wb') as file:
        np.savez(file, **best[1])
    if (dataset / 'test').exists():
        score, matrix = evaluate(best[1], *load(dataset / 'test'), margin)
        print(f'Test · rappel moyen {score:.1%} · {matrix}')
    print('Matrice : lignes vide/occupée, colonnes vide/occupée/incertaine.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('dataset', type=Path)
    parser.add_argument('--out', type=Path, default=Path('occupancy.npz'))
    parser.add_argument('--margin', type=float, default=.2)
    args = parser.parse_args()
    if not 0 <= args.margin <= 5:
        parser.error('Marge entre 0 et 5 requise.')
    train(args.dataset, args.out, args.margin)


if __name__ == '__main__':
    main()

