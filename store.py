import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, path, wait_seconds=300):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.wait_seconds = wait_seconds
        with self.transaction() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tables (
                    id INTEGER PRIMARY KEY, state TEXT NOT NULL DEFAULT 'free',
                    changed REAL NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 0,
                    manual_until REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS visits (
                    id INTEGER PRIMARY KEY, table_id INTEGER NOT NULL REFERENCES tables(id),
                    seated REAL NOT NULL, acknowledged REAL, served REAL,
                    departed REAL, ready REAL, alerted REAL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_open_visit
                    ON visits(table_id) WHERE ready IS NULL;
                CREATE TABLE IF NOT EXISTS cameras (
                    id INTEGER PRIMARY KEY REFERENCES tables(id), seen REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY, table_id INTEGER REFERENCES tables(id),
                    action TEXT NOT NULL, at REAL NOT NULL, source TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS vision_changes (
                    id INTEGER PRIMARY KEY, table_id INTEGER NOT NULL REFERENCES tables(id),
                    at REAL NOT NULL, observation TEXT, staff_state TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS vision_by_time ON vision_changes(at);
            """)
            columns = {row['name'] for row in db.execute('PRAGMA table_info(cameras)')}
            if 'observation' not in columns:
                db.execute('ALTER TABLE cameras ADD COLUMN observation TEXT')

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                db.execute('BEGIN IMMEDIATE')
                yield db
        finally:
            db.close()

    def seed(self, count, demo=False):
        with self.transaction() as db:
            initial = db.execute('SELECT COUNT(*) FROM tables').fetchone()[0] == 0
            db.executemany('INSERT OR IGNORE INTO tables(id) VALUES (?)',
                           [(i,) for i in range(1, count + 1)])
            if initial and demo:
                now = time.time()
                for table, action, age in [(1, 'seat', 410), (3, 'seat', 125),
                                           (4, 'seat', 650), (4, 'serve', 390),
                                           (6, 'seat', 530), (6, 'leave', 75)]:
                    if table <= count:
                        self._transition(db, table, action, 'demo', now - age)

    def _transition(self, db, table, action, source, now, revision=None):
        row = db.execute('SELECT * FROM tables WHERE id=?', (table,)).fetchone()
        if row is None:
            raise ValueError('Table inconnue.')
        if revision is not None and revision != row['revision']:
            raise Conflict('La table a changé. Réessayez après actualisation.')
        state = row['state']
        transitions = {
            ('free', 'seat'): 'waiting',
            ('waiting', 'ack'): 'acknowledged',
            ('waiting', 'serve'): 'served',
            ('acknowledged', 'serve'): 'served',
            ('waiting', 'leave'): 'cleaning',
            ('acknowledged', 'leave'): 'cleaning',
            ('served', 'leave'): 'cleaning',
            ('cleaning', 'ready'): 'free',
            ('cleaning', 'restore'): 'waiting',
        }
        target = transitions.get((state, action))
        if source == 'vision' and (now < row['manual_until'] or target is None):
            return
        if target is None:
            raise Conflict('Action indisponible dans cet état.')
        if action == 'seat':
            db.execute('INSERT INTO visits(table_id,seated) VALUES (?,?)', (table, now))
        elif action == 'restore':
            visit = db.execute('SELECT acknowledged,served FROM visits WHERE table_id=? AND ready IS NULL',
                               (table,)).fetchone()
            target = 'served' if visit['served'] is not None else 'acknowledged' if visit['acknowledged'] is not None else 'waiting'
            db.execute('UPDATE visits SET departed=NULL WHERE table_id=? AND ready IS NULL', (table,))
        elif action == 'serve':
            db.execute('UPDATE visits SET served=?, acknowledged=COALESCE(acknowledged,?) '
                       'WHERE table_id=? AND ready IS NULL', (now, now, table))
        else:
            column = {'ack': 'acknowledged', 'leave': 'departed', 'ready': 'ready'}[action]
            db.execute(f'UPDATE visits SET {column}=? WHERE table_id=? AND ready IS NULL',
                       (now, table))
        manual_until = now + 90 if source == 'staff' and action in ('seat', 'leave', 'ready', 'restore') else row['manual_until']
        db.execute('UPDATE tables SET state=?,changed=?,revision=revision+1,manual_until=? WHERE id=?',
                   (target, now, manual_until, table))
        db.execute('INSERT INTO events(table_id,action,at,source) VALUES (?,?,?,?)',
                   (table, action, now, source))

    def action(self, table, action, revision):
        with self.transaction() as db:
            self._transition(db, table, action, 'staff', time.time(), revision)

    def observe(self, observations, automatic=True, automatic_departure=True):
        with self.transaction() as db:
            now = time.time()
            for table, state in observations.items():
                prior = db.execute('SELECT seen,observation FROM cameras WHERE id=?', (table,)).fetchone()
                db.execute('INSERT INTO cameras(id,seen,observation) VALUES (?,?,?) '
                           'ON CONFLICT(id) DO UPDATE SET seen=excluded.seen,observation=excluded.observation',
                           (table, now, state))
                if prior is None or prior['observation'] != state or now - prior['seen'] > 15:
                    db.execute('INSERT INTO vision_changes(table_id,at,observation,staff_state) '
                               'SELECT id,?,?,state FROM tables WHERE id=?', (now, state, table))
                if automatic and (state == 'occupied' or (state == 'empty' and automatic_departure)):
                    self._transition(db, table, 'seat' if state == 'occupied' else 'leave', 'vision', now)

    def vision_log(self, since):
        with self.transaction() as db:
            return list(map(dict, db.execute('SELECT table_id,at,observation,staff_state FROM vision_changes '
                                             'WHERE at>=? ORDER BY id', (since,)).fetchall()))

    def record_alerts(self):
        with self.transaction() as db:
            self._record_alerts(db, time.time())

    def _record_alerts(self, db, now):
        late = db.execute('SELECT id,table_id FROM visits WHERE departed IS NULL '
                          'AND acknowledged IS NULL AND alerted IS NULL AND seated<=?',
                          (now - self.wait_seconds,)).fetchall()
        for visit in late:
            db.execute('UPDATE visits SET alerted=? WHERE id=?', (now, visit['id']))
            db.execute("INSERT INTO events(table_id,action,at,source) VALUES (?,'alert',?,'system')",
                       (visit['table_id'], now))

    def snapshot(self):
        now = time.time()
        with self.transaction() as db:
            self._record_alerts(db, now)
            tables = db.execute("""
                SELECT t.id,t.state,t.changed,t.revision,v.seated,v.alerted,
                    CASE WHEN c.seen>=? THEN 1 ELSE 0 END AS online, c.observation
                FROM tables t LEFT JOIN visits v ON t.id=v.table_id AND v.ready IS NULL
                LEFT JOIN cameras c ON t.id=c.id ORDER BY t.id
            """, (now - 15,)).fetchall()
            history = db.execute('SELECT table_id,action,at,source FROM events ORDER BY id DESC LIMIT 30').fetchall()
            return dict(now=now, wait=self.wait_seconds, tables=list(map(dict, tables)),
                        history=list(map(dict, history)))

    def visits(self, since=0):
        with self.transaction() as db:
            return list(map(dict, db.execute('SELECT * FROM visits WHERE seated>=? ORDER BY seated DESC',
                                             (since,)).fetchall()))
