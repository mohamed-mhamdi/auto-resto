import numpy as np

from camera import crop
from confirmation import Confirmation
from detector import Detector
from evidence import SeatEvidence, fuse
from model import load_model, predict, prepare


class Pipeline:
    def __init__(self, regions, detector_path, crop_model=None, margin=.2, enter=5, exit=30,
                 confidence=.22, strong=.48, stable=1.5, seats=None):
        self.regions = regions
        self.detector = Detector(detector_path, confidence) if detector_path else None
        self.seats = SeatEvidence(regions, stable, strong, seats)
        self.crop_model = load_model(crop_model) if crop_model else None
        self.margin = margin
        self.confirmations = {table: Confirmation(enter, exit) for table in regions}

    def reset(self):
        self.seats.reset()
        for confirmation in self.confirmations.values():
            confirmation.reset()

    def update(self, frame, now):
        people = self.detector.detect(frame) if self.detector else []
        geometry = self.seats.update(people, now) if self.detector else {}
        local = {}
        if self.crop_model is not None:
            batch = np.stack([prepare(crop(frame, box)) for box in self.regions.values()])
            local = dict(zip(self.regions, predict(self.crop_model, batch, self.margin)))
        raw = {}
        for table in self.regions:
            if not self.detector:
                raw[table] = local[table]
            elif self.crop_model is None:
                raw[table] = geometry[table].state
            else:
                raw[table] = fuse(geometry[table].state, local[table])
        confirmed = {table: self.confirmations[table].update(state, now) for table, state in raw.items()}
        return people, raw, confirmed


class FeedWatch:
    """Repeated identical sampled images are treated as a potentially frozen feed."""
    def __init__(self, limit=12):
        self.limit = limit
        self.previous = None
        self.changed = None

    def update(self, frame, now):
        sample = frame[::12, ::12].copy()
        if self.previous is None or not np.array_equal(self.previous, sample):
            self.changed = now
        self.previous = sample
        luminance = sample.mean()
        return now - self.changed < self.limit and 7 < luminance < 248

