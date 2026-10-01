#!/usr/bin/env python3
"""Read-only song summary and selectors. Does not verify source or language."""
import argparse
import json
import sys
from collections import Counter

from dataload import load_song

CHECKS = ('song_version', 'lyric_text', 'reading_translation', 'structure', 'render', 'visual')


def select_records(records, field, value):
    selected = [r for r in records if r.get(field) == value]
    if not selected:
        raise ValueError(f'Unknown {field}: {value}')
    if field == 'id' and len(selected) != 1:
        raise ValueError(f'Duplicate line ID: {value}; fix data before editing')
    return selected


def context(data, meta, line=None, section=None):
    verification = data.get('verification') or {}
    if not isinstance(verification, dict):
        verification = {}
    line_states = verification.get('lines') or {}
    if not isinstance(line_states, dict):
        line_states = {}
    if line is not None or section is not None:
        records = select_records(meta['lines'], 'id' if line is not None else 'section', line if line is not None else section)
        return {'title': data.get('title'), 'language': meta['language'],
                'lines': [dict(r, verification_entry=line_states.get(r['id'])) for r in records]}
    lyric_ver = verification.get('lyrics') or {}
    if not isinstance(lyric_ver, dict):
        lyric_ver = {}
    profile = data.get('visual_profile') or {}
    if not isinstance(profile, dict):
        profile = {}
    director = profile.get('director') or {}
    if not isinstance(director, dict):
        director = {}
    assets = data.get('visual_assets') or {}
    if not isinstance(assets, dict):
        assets = {}
    checks = verification.get('checks') or {}
    if not isinstance(checks, dict):
        checks = {}
    def matches(stored):
        return stored == meta['fingerprint'] if stored else None
    ids = Counter(r['id'] for r in meta['lines'])
    return {
        'title': data.get('title'), 'schema_version': data.get('schema_version'),
        'language': meta['language'], 'language_explicit': meta['language_explicit'],
        'occurrences': len(meta['lines']),
        'sections': [{'name': name, 'lines': len(rows)} for name, rows in meta['sections']],
        'derived_id_count': meta['derived_id_count'],
        'duplicate_ids': [lid for lid, count in ids.items() if count > 1],
        'fingerprint': meta['fingerprint'],
        'verification_fingerprint_matches': matches(verification.get('fingerprint')),
        'checks': {key: checks.get(key) for key in CHECKS},
        'per_line_entries': sum(r['id'] in line_states for r in meta['lines']),
        'text_compared': lyric_ver.get('text_compared'),
        'lyric_sources': lyric_ver.get('sources', []),
        'sources_lyrics': data.get('sources_lyrics', []),
        'learning_counts': {key: len(data.get(key) or []) for key in ('bg_paras', 'vocab_table', 'grammar_points', 'culture_notes', 'singing_tips')},
        'visual': {'render_version': profile.get('renderVersion'),
                   'director_present': bool(director),
                   'director_fingerprint_matches': matches(director.get('source_fingerprint')),
                   'pages': len(assets.get('pages') or [])},
        'notice': 'Existing records only; entries and matching fingerprints do not prove verification.'
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('data', help='Path to data.json')
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument('--line', help='Exact persistent line ID')
    selector.add_argument('--section', help='Exact section name')
    args = parser.parse_args()
    try:
        data, meta = load_song(args.data)
        result = context(data, meta, args.line, args.section)
    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        print(f'song_context: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
