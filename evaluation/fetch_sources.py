"""Download attributed evaluation sources, verify their hashes, and normalize video."""
import argparse
import hashlib
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--out', type=Path, default=Path('recordings'))
    parser.add_argument('--only', nargs='+', help='Identifiants des sources à traiter')
    args = parser.parse_args()
    sources = json.loads(Path(__file__).with_name('sources.json').read_text(encoding='utf-8'))
    selected = [source for source in sources if not args.only or source['id'] in args.only]
    if args.only and {source['id'] for source in selected} != set(args.only):
        parser.error('Identifiant de source inconnu.')
    args.out.mkdir(parents=True, exist_ok=True)
    for source in selected:
        stem = source['id']
        original = args.out / (stem + '.webm')
        if not original.exists():
            partial = original.with_suffix('.webm.part')
            request = urllib.request.Request(source['url'], headers={'User-Agent': 'SallePilotEvaluation/2.0 (manual reproducibility run)'})
            print(f'Téléchargement : {source["title"]}', flush=True)
            with urllib.request.urlopen(request, timeout=60) as stream, partial.open('wb') as output:
                shutil.copyfileobj(stream, output)
            if digest(partial) != source['sha256']:
                raise ValueError(f'Intégrité invalide pour {partial}.')
            partial.replace(original)
        if digest(original) != source['sha256']:
            raise ValueError(f'Intégrité invalide pour {original}.')
        video = args.out / (stem + '.mp4')
        if not video.exists():
            temporary = video.with_suffix('.part.mp4')
            quality = '22' if stem in ('spring-court', 'cheese-mites', 'kehlsteinhaus', 'cdc-chair', 'cdc-walk') else '23'
            subprocess.run([args.ffmpeg, '-v', 'error', '-y', '-i', str(original), '-an',
                            '-vf', 'fps=8,scale=640:-2', '-c:v', 'libx264', '-preset', 'ultrafast',
                            '-crf', quality, str(temporary)], check=True)
            temporary.replace(video)
        print(f'Prêt : {video}', flush=True)


if __name__ == '__main__':
    main()
