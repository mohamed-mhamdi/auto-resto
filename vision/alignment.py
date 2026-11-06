"""Check that a static, calibrated patch has stayed in the same camera coordinates."""
import cv2
import numpy as np


class Alignment:
    def __init__(self, reference):
        self.region = reference['region']
        self.points = np.asarray(reference['points'], dtype=np.float32)
        self.descriptors = np.asarray(reference['descriptors'], dtype=np.uint8)
        self.orb = cv2.ORB_create(nfeatures=300, fastThreshold=10)
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING)

    @staticmethod
    def patch(frame, region):
        x, y, w, h = region
        gray = cv2.cvtColor(frame[y:y+h, x:x+w], cv2.COLOR_BGR2GRAY)
        scale = min(1., 640 / max(gray.shape))
        return cv2.resize(gray, (max(1, round(w * scale)), max(1, round(h * scale))))

    @classmethod
    def create(cls, frame, region):
        patch = cls.patch(frame, region)
        points, descriptors = cv2.ORB_create(nfeatures=300, fastThreshold=10).detectAndCompute(patch, None)
        if descriptors is None or len(descriptors) < 18:
            raise ValueError('Choisissez une zone fixe plus grande avec des motifs ou des contours.')
        return {'region': region, 'points': [point.pt for point in points], 'descriptors': descriptors.tolist()}

    def good(self, frame):
        patch = self.patch(frame, self.region)
        points, descriptors = self.orb.detectAndCompute(patch, None)
        if descriptors is None or len(descriptors) < 12:
            return False
        pairs = self.matcher.knnMatch(self.descriptors, descriptors, k=2)
        matches = [pair[0] for pair in pairs if len(pair) == 2 and pair[0].distance < .75 * pair[1].distance]
        if len(matches) < 12:
            return False
        previous = np.asarray([self.points[match.queryIdx] for match in matches])
        current = np.asarray([points[match.trainIdx].pt for match in matches], dtype=np.float32)
        matrix, mask = cv2.estimateAffinePartial2D(previous, current, method=cv2.RANSAC)
        if matrix is None or mask is None or int(mask.sum()) < max(9, .55 * len(matches)):
            return False
        height, width = patch.shape
        corners = np.array([[0, 0], [width, 0], [0, height], [width, height]], dtype=np.float32)
        mapped = cv2.transform(corners[None], matrix)[0]
        return float(np.linalg.norm(mapped - corners, axis=1).max()) <= max(5, .035 * min(width, height))
