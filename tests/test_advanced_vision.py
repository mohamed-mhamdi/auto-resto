import sys
import unittest
from pathlib import Path

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vision'))


@unittest.skipIf(cv2 is None, 'OpenCV absent')
class AdvancedVisionTest(unittest.TestCase):
    def test_seat_excludes_standing_and_tracks_brief_loss(self):
        from detector import Person
        from evidence import SeatEvidence

        regions = {1: [0, 0, 180, 220]}
        seats = {1: [[55, 90, 50, 35]]}
        model = SeatEvidence(regions, seats=seats)
        standing = Person((55, 10, 50, 205), .9)
        seated = Person((55, 82, 50, 145), .9)
        self.assertIsNone(model.update([standing], 0)[1].state)
        self.assertIsNone(model.update([seated], 1)[1].state)
        self.assertEqual(model.update([seated], 2.5)[1].state, 'occupied')
        self.assertEqual(model.update([], 3.5)[1].state, 'occupied')
        self.assertEqual(model.update([], 5)[1].state, 'empty')

    def test_one_person_does_not_start_two_tables(self):
        from detector import Person
        from evidence import SeatEvidence

        model = SeatEvidence({1: [0, 0, 100, 100], 2: [70, 0, 100, 100]})
        person = Person((55, 0, 50, 100), .95)
        self.assertIsNone(model.update([person], 1)[1].state)
        self.assertIsNone(model.update([person], 3)[2].state)

    def test_lost_or_dark_feed_and_camera_motion(self):
        from alignment import Alignment
        from pipeline import FeedWatch

        random = np.random.default_rng(9)
        frame = random.integers(0, 255, (260, 360, 3), dtype=np.uint8)
        watch = FeedWatch()
        self.assertTrue(watch.update(frame, 0))
        self.assertFalse(watch.update(frame, 13))
        self.assertFalse(watch.update(np.zeros_like(frame), 14))
        self.assertTrue(watch.update(frame, 15))
        alignment = Alignment(Alignment.create(frame, [10, 10, 300, 220]))
        self.assertTrue(alignment.good(frame))
        shifted = cv2.warpAffine(frame, np.array([[1, 0, 30], [0, 1, 20]], np.float32), (360, 260))
        self.assertFalse(alignment.good(shifted))
