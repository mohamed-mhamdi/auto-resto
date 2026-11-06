"""CPU person detection for official raw-output YOLOX ONNX exports."""
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class Person:
    box: tuple
    confidence: float


class Detector:
    def __init__(self, model, threshold=.30):
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        self.session = ort.InferenceSession(str(model), sess_options=options,
                                            providers=['CPUExecutionProvider'])
        self.input = self.session.get_inputs()[0]
        shape = self.input.shape
        if len(shape) != 4 or shape[:2] != [1, 3] or shape[2] != shape[3] or shape[2] not in (416, 640):
            raise ValueError('Export YOLOX à sortie brute requis, avec entrée 416×416 ou 640×640.')
        self.size = shape[2]
        self.threshold = threshold
        grids, strides = [], []
        for stride in (8, 16, 32):
            side = self.size // stride
            yy, xx = np.indices((side, side))
            grids.append(np.stack((xx, yy), axis=-1).reshape(-1, 2))
            strides.append(np.full((side * side, 1), stride))
        self.grid = np.concatenate(grids)
        self.stride = np.concatenate(strides)

    def detect(self, image):
        height, width = image.shape[:2]
        ratio = min(self.size / width, self.size / height)
        rw, rh = max(1, int(width * ratio)), max(1, int(height * ratio))
        canvas = np.full((self.size, self.size, 3), 114, dtype=np.uint8)
        canvas[:rh, :rw] = cv2.resize(image, (rw, rh))
        tensor = np.ascontiguousarray(canvas.transpose(2, 0, 1)[None], dtype=np.float32)
        output = self.session.run(None, {self.input.name: tensor})[0][0]
        if output.shape != (len(self.grid), 85):
            raise ValueError('Sortie YOLOX inattendue.')
        scores = output[:, 4] * output[:, 5]
        selected = scores >= self.threshold
        if not selected.any():
            return []
        centers = (output[selected, :2] + self.grid[selected]) * self.stride[selected]
        dimensions = np.exp(np.clip(output[selected, 2:4], -10, 10)) * self.stride[selected]
        top = np.maximum((centers - dimensions / 2) / ratio, 0)
        bottom = np.minimum((centers + dimensions / 2) / ratio, [width, height])
        boxes = np.column_stack((top, bottom - top))
        valid = np.min(boxes[:, 2:], axis=1) >= 4
        boxes = boxes[valid].tolist()
        scores = scores[selected][valid].tolist()
        indices = cv2.dnn.NMSBoxes(boxes, scores, 0., .45)
        return [Person(tuple(boxes[index]), scores[index]) for index in np.asarray(indices).ravel().astype(int)]
