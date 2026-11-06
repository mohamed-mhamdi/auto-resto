"""Conservative standing-person veto from MediaPipe world landmarks."""
import cv2
import numpy as np


def angle(first, joint, last):
    a, b = first - joint, last - joint
    length = np.linalg.norm(a) * np.linalg.norm(b)
    if length < 1e-6:
        return None
    return float(np.degrees(np.arccos(np.clip(np.dot(a, b) / length, -1., 1.))))


class Posture:
    def __init__(self, model):
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        self.session = ort.InferenceSession(str(model), sess_options=options,
                                            providers=['CPUExecutionProvider'])
        input = self.session.get_inputs()[0]
        if input.shape != [1, 256, 256, 3]:
            raise ValueError('Export MediaPipe Pose OpenCV Zoo 256×256 requis.')
        self.input_name = input.name
        outputs = {tuple(output.shape): output.name for output in self.session.get_outputs()}
        self.outputs = [outputs[(1, 195)], outputs[(1, 1)], outputs[(1, 117)]]

    def angles(self, image, box):
        x, y, w, h = box
        if min(w, h) < 40:
            return []
        size = max(w, h) * 1.20
        scale = 256 / size
        left = x + w / 2 - size / 2
        top = y + h / 2 - size / 2
        matrix = np.array([[scale, 0, -left * scale], [0, scale, -top * scale]], dtype=np.float32)
        patch = cv2.warpAffine(image, matrix, (256, 256))
        pixels = cv2.cvtColor(patch, cv2.COLOR_BGR2RGB).astype(np.float32)[None] / 255
        coords, presence, world = self.session.run(self.outputs, {self.input_name: pixels})
        if presence.item() < .75:
            return []
        landmarks = coords.reshape(-1, 5)
        points = world.reshape(-1, 3)
        visibility = 1 / (1 + np.exp(-np.clip(landmarks[:, 3], -30, 30)))
        angles = []
        for shoulder, hip, knee in ((11, 23, 25), (12, 24, 26)):
            if min(visibility[[shoulder, hip, knee]]) >= .50:
                value = angle(points[shoulder], points[hip], points[knee])
                if value is not None:
                    angles.append(value)
        return angles

    def standing(self, image, box):
        angles = self.angles(image, box)
        return len(angles) == 2 and min(angles) >= 150


def main():
    import argparse
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vision'))
    from benchmark import read_frames
    from detector import Detector

    parser = argparse.ArgumentParser(description='Inspecter la disponibilité des angles de hanche sur une vidéo.')
    parser.add_argument('video', type=Path)
    parser.add_argument('pose_model', type=Path)
    parser.add_argument('--start', type=float, required=True)
    parser.add_argument('--end', type=float, required=True)
    args = parser.parse_args()
    detector = Detector('models/yolox_s.onnx', .35)
    posture = Posture(args.pose_model)
    observations = full = standing = 0
    for at, frame in read_frames(args.video, args.start, args.end, .5):
        for person in detector.detect(frame):
            angles = posture.angles(frame, person.box)
            observations += 1
            full += len(angles) == 2
            standing += len(angles) == 2 and min(angles) >= 150
    print(f'{observations} détections de personne, {full} avec deux angles exploitables, {standing} classées debout.')


if __name__ == '__main__':
    main()
