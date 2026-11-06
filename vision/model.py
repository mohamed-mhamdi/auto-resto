import cv2
import numpy as np


SIZE = 128
CLASSES = ('empty', 'occupied')
CELL = 16


def prepare(image):
    height, width = image.shape[:2]
    scale = SIZE / max(height, width)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (max(1, round(width * scale)), max(1, round(height * scale))))
    h, w = resized.shape
    canvas = np.full((SIZE, SIZE), 114, dtype=np.uint8)
    y, x = (SIZE - h) // 2, (SIZE - w) // 2
    canvas[y:y+h, x:x+w] = resized
    dx = cv2.Sobel(canvas, cv2.CV_32F, 1, 0)
    dy = cv2.Sobel(canvas, cv2.CV_32F, 0, 1)
    magnitude, angle = cv2.cartToPolar(dx, dy, angleInDegrees=True)
    bins = ((angle % 180) / 20).astype(int)
    histograms = []
    for y in range(0, SIZE, CELL):
        for x in range(0, SIZE, CELL):
            region = np.s_[y:y+CELL, x:x+CELL]
            histogram = np.bincount(bins[region].ravel(), magnitude[region].ravel(), minlength=9)
            histograms.append(histogram / (np.linalg.norm(histogram) + 1))
    return np.concatenate(histograms).astype(np.float32)


def predict(model, samples, margin):
    scores = samples @ model['weights'] + model['bias']
    return [CLASSES[int(score >= 0)] if abs(score) >= margin else None for score in scores]


def load_model(path):
    with np.load(path, allow_pickle=False) as archive:
        return {key: archive[key] for key in ('weights', 'bias')}
