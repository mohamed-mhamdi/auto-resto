class Confirmation:
    def __init__(self, enter=5, exit=30, max_gap=3):
        self.delays = {'occupied': enter, 'empty': exit}
        self.max_gap = max_gap
        self.reset()

    def reset(self):
        self.state = None
        self.since = None
        self.last = None

    def update(self, state, now):
        if state is None:
            self.reset()
            return None
        if self.state != state or self.last is None or now - self.last > self.max_gap:
            self.state, self.since = state, now
        self.last = now
        return state if now - self.since >= self.delays[state] else None
