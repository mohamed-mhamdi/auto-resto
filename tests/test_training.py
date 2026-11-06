import sys
import tempfile
import unittest
from pathlib import Path

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vision'))


@unittest.skipIf(cv2 is None, 'OpenCV absent')
class VisionTrainingTest(unittest.TestCase):
    def test_train_save_reload_predict(self):
        from model import load_model, predict, prepare
        from train import train

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            probes = []
            for split, offset in [('train', 0), ('val', 3), ('test', 6)]:
                for label in ('empty', 'occupied'):
                    folder = root / split / label
                    folder.mkdir(parents=True)
                    for index in range(3):
                        shift = (offset + index) % 3
                        image = np.zeros((128, 128, 3), dtype=np.uint8)
                        cv2.rectangle(image, (18, 72), (110, 101), (150 + offset, 150 + offset, 150 + offset), -1)
                        if label == 'occupied':
                            cv2.circle(image, (60 + shift, 36), 12, (230, 230, 230), -1)
                            cv2.rectangle(image, (44 + shift, 48), (76 + shift, 76), (215, 215, 215), -1)
                        _, encoded = cv2.imencode('.jpg', image)
                        (folder / f'{index}.jpg').write_bytes(encoded.tobytes())
                        if split == 'test' and index == 0:
                            probes.append(prepare(image))
            output = root / 'occupancy.npz'
            train(root, output, .2)
            model = load_model(output)
            self.assertEqual(predict(model, np.stack(probes), .2), ['empty', 'occupied'])


