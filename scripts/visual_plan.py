"""Validate the directing contract, not the artistic quality of the decisions."""
from pathlib import Path
import argparse
import json
import sys

ROLES = {'introduce', 'continue', 'build', 'pause', 'contrast', 'resolve', 'peak'}


def check_director(data, meta, required=False):
    profile = data.get('visual_profile') or {}
    if not isinstance(profile, dict):
        raise ValueError('visual_profile must be an object')
    director = profile.get('director')
    if director is None:
        if required:
            raise ValueError('Missing visual_profile.director; plan the song before rendering')
        return ['Legacy page plan: no directing contract; no claim of semantic review']
    if not isinstance(director, dict) or director.get('version') != 1:
        raise ValueError('director.version must be 1')
    if director.get('source_fingerprint') != meta['fingerprint']:
        raise ValueError('Directing plan is stale: review affected decisions and update source_fingerprint')
    brief = director.get('brief', {})
    if not isinstance(brief, dict):
        raise ValueError('director.brief must be an object')
    for key in ('premise', 'emotional_arc', 'evidence_basis'):
        if not isinstance(brief.get(key), str) or not brief[key].strip():
            raise ValueError(f'director.brief.{key} is required')
    if brief['evidence_basis'] not in ('lyrics_only', 'lyrics_and_audio'):
        raise ValueError('evidence_basis must be lyrics_only or lyrics_and_audio')
    if brief['evidence_basis'] == 'lyrics_and_audio':
        evidence = brief.get('audio_evidence')
        if not isinstance(evidence, dict) or any(
                not isinstance(evidence.get(k), str) or not evidence[k].strip()
                for k in ('recording', 'scope')):
            raise ValueError('Audio-based claims need audio_evidence.recording and scope')
    system = director.get('system', {})
    if not isinstance(system, dict):
        raise ValueError('director.system must be an object')
    for key in ('concept', 'palette_logic', 'typography_logic', 'composition_logic', 'motif_logic'):
        if not isinstance(system.get(key), str) or not system[key].strip():
            raise ValueError(f'director.system.{key} is required')
    if not isinstance(system.get('avoid'), list) or any(
            not isinstance(v, str) or not v.strip() for v in system['avoid']):
        raise ValueError('director.system.avoid must be a list of nonempty strings')
    expected = [r['id'] for r in meta['lines']]
    timeline = director.get('timeline')
    if not isinstance(timeline, list) or not timeline:
        raise ValueError('director.timeline must contain ordered phases')
    phase_by_id, owner, covered = {}, {}, []
    for phase in timeline:
        if not isinstance(phase, dict):
            raise ValueError('Every timeline phase must be an object')
        pid = phase.get('id')
        if not isinstance(pid, str) or not pid or pid in phase_by_id:
            raise ValueError('Timeline phase IDs must be nonempty and unique')
        ids = phase.get('line_ids')
        if not isinstance(ids, list) or not ids or any(not isinstance(i, str) for i in ids):
            raise ValueError(f'{pid}: nonempty line_ids required')
        for key in ('state', 'visual_shift', 'reason'):
            if not isinstance(phase.get(key), str) or not phase[key].strip():
                raise ValueError(f'{pid}: {key} required')
        if brief['evidence_basis'] == 'lyrics_only' and any(k in phase for k in ('start_seconds', 'end_seconds', 'bpm')):
            raise ValueError(f'{pid}: lyrics_only plans cannot claim measured timing or BPM')
        phase_by_id[pid] = phase
        covered.extend(ids)
        owner.update({i:pid for i in ids})
    if covered != expected:
        raise ValueError('Timeline must cover every lyric occurrence once in source order')
    assets = data.get('visual_assets') or {}
    if not isinstance(assets, dict):
        raise ValueError('visual_assets must be an object')
    pages = assets.get('pages', [])
    if not isinstance(pages, list) or not pages:
        raise ValueError('Director requires visual_assets.pages as the single storyboard')
    seen, used = {}, []
    for page in pages:
        if not isinstance(page, dict):
            raise ValueError('Every storyboard page must be an object')
        pid = page.get('id')
        if not isinstance(pid, str) or not pid or pid in seen:
            raise ValueError('Storyboard page IDs must be unique nonempty strings')
        ids = page.get('line_ids', [])
        if not isinstance(ids, list) or not ids or any(not isinstance(i,str) or i not in owner for i in ids):
            raise ValueError(f'{pid}: unknown or empty line_ids')
        if page.get('phase_id') not in phase_by_id or any(owner[i] != page['phase_id'] for i in ids):
            raise ValueError(f'{pid}: lines must belong to its declared timeline phase')
        if page.get('role') not in ROLES:
            raise ValueError(f'{pid}: unsupported role')
        for key in ('reason', 'transition'):
            if not isinstance(page.get(key), str) or not page[key].strip():
                raise ValueError(f'{pid}: {key} required')
        focus = page.get('focus_ids', [])
        if not isinstance(focus, list) or any(i not in ids for i in focus):
            raise ValueError(f'{pid}: focus_ids must reference this page')
        repeat = page.get('repeat_of')
        if repeat:
            if not isinstance(repeat, str) or repeat not in seen or not isinstance(page.get('repeat_reason'), str) or not page['repeat_reason'].strip():
                raise ValueError(f'{pid}: repeat_of needs an earlier page and repeat_reason')
        seen[pid] = page
        used.extend(ids)
    if used != expected:
        raise ValueError('Storyboard must cover every lyric occurrence once in source order')
    return []


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.dataload import load_song
    from scripts.pptx_editorial import validate_plan
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('data')
    parser.add_argument('--require-director', action='store_true')
    args = parser.parse_args()
    try:
        data, meta = load_song(args.data)
        warnings = check_director(data, meta, required=args.require_director)
        validate_plan(data, meta)
    except (ValueError, TypeError, KeyError) as exc:
        print(f'VISUAL PLAN ERROR: {exc}')
        return 1
    for warning in warnings:
        print('WARNING:', warning)
    print('VISUAL PLAN STRUCTURE PASS (not a visual or linguistic quality verdict)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
