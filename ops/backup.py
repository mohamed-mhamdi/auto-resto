"""Create a consistent copy of SQLite even when the application is running."""
import argparse
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path


def backup(source, destination):
    source, destination = source.resolve(strict=True), destination.resolve()
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=destination.parent, suffix='.sqlite.tmp')
    os.close(handle)
    temp = Path(temporary)
    try:
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as current:
            with closing(sqlite3.connect(temp)) as target:
                current.backup(target)
                if target.execute('PRAGMA quick_check').fetchone() != ('ok',):
                    raise RuntimeError('Le contrôle de la copie SQLite a échoué.')
        # Publish the completed copy without overwriting another backup.
        os.link(temp, destination)
    finally:
        temp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description='Sauvegarder la base SallePilot.')
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    backup(args.source, args.destination)
    print(f'Sauvegarde vérifiée : {args.destination}')


if __name__ == '__main__':
    main()
