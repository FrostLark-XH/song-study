"""Bind whole-song visual comparisons to the actual data, plan, deck and render.

No automatic aesthetic verdict. Uses an existing complete render; never silently
substitutes a new or approximate render. Outputs are for a reviewer to inspect.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.dataload import load_song
from scripts.pptx_editorial import validate_plan, visual_fingerprint
from scripts.render_preview import contact_sheet


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def collect(data_path, pptx_path, render_dir):
    data, meta = load_song(data_path)
    pages, _ = validate_plan(data, meta)
    deck, render = Path(pptx_path), Path(render_dir)
    manifest = json.loads(deck.with_suffix('.manifest.json').read_text(encoding='utf8'))
    receipt = json.loads((render/'render_receipt.json').read_text(encoding='utf8'))
    if manifest.get('preview'):
        raise ValueError('Whole-song evidence requires a full deck, not --preview')
    if manifest.get('data_fingerprint') != meta['fingerprint'] or manifest.get('visual_fingerprint') != visual_fingerprint(data):
        raise ValueError('Stale content or visual plan: rebuild before collecting evidence')
    if manifest.get('pptx_sha256') != sha(deck) or receipt.get('pptx_sha256') != sha(deck):
        raise ValueError('Deck, manifest and render receipt must identify the same PPTX')
    if [p['page_id'] for p in manifest['pages']] != [p['id'] for p in pages]:
        raise ValueError('Manifest page order differs from plan')
    for actual, planned in zip(manifest['pages'],pages):
        if actual['line_ids'] != planned['line_ids']:
            raise ValueError('Manifest line coverage differs from plan')
    expected = len(pages)+1
    if manifest['slides'] != expected or receipt['slide_count'] != expected:
        raise ValueError('Incomplete slide count')
    images = [render/f'slide_{i:03}.png' for i in range(1,expected+1)]
    if not all(p.is_file() for p in images):
        raise ValueError('Missing rendered slide')
    if receipt.get('images') != {p.name:sha(p) for p in images}:
        raise ValueError('Rendered image hashes differ or receipt is old; render again')
    return data, meta, pages, manifest, receipt, images


def generate(data_path, pptx_path, render_dir, output):
    data, meta, pages, manifest, receipt, images = collect(data_path,pptx_path,render_dir)
    out = Path(output);out.mkdir(parents=True,exist_ok=True)
    labels=['S01 cover']+[f'S{i+2:02d} {p["id"]}' for i,p in enumerate(pages)]
    contact_sheet(images,out/'01_whole_song.png',labels,cell_w=480)
    by_id={p['id']:i+1 for i,p in enumerate(pages)}
    phases=data['visual_profile']['director']['timeline']
    phase_indices=[]
    outputs=['01_whole_song.png']
    for n,phase in enumerate(phases,1):
        indices=[i+1 for i,p in enumerate(pages) if p['phase_id']==phase['id']]
        if not indices:continue
        phase_indices.append(indices[0])
        filename=f'phase_{n:02d}.png'
        contact_sheet([images[i] for i in indices],out/filename,[labels[i] for i in indices],cell_w=640,columns=2)
        outputs.append(filename)
    contact_sheet([images[i] for i in phase_indices],out/'02_phase_overview.png',[labels[i] for i in phase_indices],cell_w=640)
    outputs.append('02_phase_overview.png')
    # All explicit return pairs; don't cherry-pick only the most varied one.
    pairs=[]
    for p in pages:
        if p.get('repeat_of'):pairs.extend([by_id[p['repeat_of']],by_id[p['id']]])
    if pairs:
        contact_sheet([images[i] for i in pairs],out/'03_all_returns.png',[labels[i] for i in pairs],cell_w=640,columns=2)
        outputs.append('03_all_returns.png')
    ends=[1,len(images)-1] if len(images)>2 else [0,len(images)-1]
    contact_sheet([images[i] for i in ends],out/'04_opening_ending.png',[labels[i] for i in ends],cell_w=800,columns=2)
    outputs.append('04_opening_ending.png')
    report={'data_fingerprint':meta['fingerprint'],'visual_fingerprint':visual_fingerprint(data),
        'pptx_sha256':sha(pptx_path),'backend':receipt['backend'],'slide_count':len(images),
        'source_line_count':len(meta['lines']),'phase_count':len(phases),'return_pairs':len(pairs)//2,
        'rendered_images':{p.name:sha(p) for p in images},
        'comparison_images':{name:sha(out/name) for name in outputs},
        'visual_review':'pending: review actual pixels and record inspected pages separately',
        'reading_warnings':manifest['reading_warnings'],
        'evidence_basis':data['visual_profile']['director']['brief']['evidence_basis']}
    (out/'evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('data');parser.add_argument('pptx');parser.add_argument('render_dir')
    parser.add_argument('--output',required=True)
    a=parser.parse_args()
    result=generate(a.data,a.pptx,a.render_dir,a.output)
    print(f"Evidence: {result['slide_count']} slides, {result['source_line_count']} lyric occurrences; visual review remains separate")
