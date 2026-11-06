"""Match person detections to calibrated seat areas and preserve ambiguity."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Evidence:
    state: str | None
    people: int


@dataclass(frozen=True)
class Track:
    point: tuple
    origin: tuple
    since: float
    seen: float
    strong_at: float
    hits: int


def covers(box, zone):
    x, y, w, h = box
    rx, ry, rw, rh = zone
    width = max(0, min(x + w, rx + rw) - max(x, rx))
    height = max(0, min(y + h, ry + rh) - max(y, ry))
    return width * height >= .45 * rw * rh


class SeatEvidence:
    def __init__(self, regions, stable_seconds=1.5, strong=.48, seats=None, memory=2.25):
        self.regions = regions
        self.seats = seats or {}
        self.stable_seconds = stable_seconds
        self.strong = strong
        self.memory = memory
        self.reset()

    def reset(self):
        self.last_at = None
        self.tracks = {}

    def update(self, people, now):
        if self.last_at is not None and now - self.last_at > 3:
            self.reset()
        self.last_at = now
        assigned = {table: [] for table in self.regions}
        ambiguous = set()
        for person in people:
            x, y, w, h = person.box
            matches = []
            for table, region in self.regions.items():
                # Narrow seat zones describe the expected head and shoulders of a seated customer.
                anchor = (x + w / 2, y + h * (.18 if table in self.seats else .60))
                ax, ay = anchor
                zones = self.seats.get(table) or [region]
                if any(rx <= ax <= rx + rw and ry <= ay <= ry + rh for rx, ry, rw, rh in zones):
                    matches.append((table, anchor))
                elif any(rx - rw * .1 <= ax <= rx + rw * 1.1 and ry - rh * .1 <= ay <= ry + rh * 1.1
                         for rx, ry, rw, rh in zones):
                    ambiguous.add(table)
                elif table in self.seats and any(covers(person.box, zone) for zone in zones):
                    ambiguous.add(table)
            if len(matches) == 1:
                table, point = matches[0]
                assigned[table].append((point, person.confidence))
            else:
                ambiguous.update(table for table, _ in matches)
        result = {}
        for table, points in assigned.items():
            _, _, width, height = self.regions[table]
            span = max(width, height)
            previous = [track for track in self.tracks.get(table, []) if now - track.seen <= self.memory]
            tracked = []
            for point, confidence in sorted(points, key=lambda value: -value[1]):
                candidates = [(math.dist(point, track.point), i) for i, track in enumerate(previous)]
                distance, index = min(candidates, default=(math.inf, None))
                strong = confidence >= self.strong
                if distance <= max(10, .19 * span):
                    old = previous.pop(index)
                    if math.dist(point, old.origin) <= max(15, .23 * span):
                        tracked.append(Track(point, old.origin, old.since, now,
                                             now if strong else old.strong_at, old.hits + 1))
                        continue
                if strong:
                    tracked.append(Track(point, point, now, now, now, 1))
            tracked.extend(previous)
            self.tracks[table] = tracked
            stable = sum(track.hits >= 2 and track.seen - track.since >= self.stable_seconds
                         and now - track.strong_at <= self.memory for track in tracked)
            state = 'occupied' if stable else None if points or tracked or table in ambiguous else 'empty'
            result[table] = Evidence(state, stable)
        return result


def fuse(primary, local):
    """Only agreeing signals can change a table when a site model is enabled."""
    return primary if primary == local else None
