"""Scene-state and provenance failure tests, using self-authored example text."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.dataload import load_song, compute_fingerprint
from scripts.pptx_editorial import visual_fingerprint, validate_plan, wrap_units
from scripts.pptx_scene import render_scene, validate_scene_plan, layer_state
from scripts.scene_evidence import collect, sha

ROOT=Path(__file__).resolve().parents[1]
EXAMPLE=ROOT/'examples/scene-return/data.json'


class SceneTests(unittest.TestCase):
    def setUp(self):
        self.data,self.meta=load_song(EXAMPLE)
        self.assets=self.data['visual_assets']
        self.page=self.assets['pages'][0]

    def test_complete_example(self):
        pages,_=validate_plan(self.data,self.meta)
        self.assertEqual(len(pages),4)
        self.assertEqual([len(p['line_ids']) for p in pages],[1,2,1,2])

    def test_narrow_column_keeps_tail_and_ruby_units_together(self):
        units=[{'base':x,'ruby':''} for x in 'あいうえおか']
        rows=wrap_units(units,40,201,avoid_short_tail=True)
        self.assertEqual([u for row in rows for u in row],units)
        self.assertEqual([len(r) for r in rows],[3,3])

    def test_deterministic_pixels_and_progress_changes(self):
        a=render_scene(self.assets,self.page,(640,360)).tobytes()
        other=copy.deepcopy(self.page);other['scene']['progress']=1
        b=render_scene(self.assets,other,(640,360)).tobytes()
        self.assertNotEqual(a,b)
        self.assertEqual(a,render_scene(self.assets,self.page,(640,360)).tobytes())

    def test_wash_seed_is_independent_of_page_order(self):
        self.assets['objects']['cup']['primitives']=[{'kind':'wash','points':[[-100,-90],[120,0],[-50,150]],'fill':'AA5533','seed':12,'smooth':True}]
        a=render_scene(self.assets,self.page,(640,360)).tobytes()
        render_scene(self.assets,self.assets['pages'][-1],(640,360))
        self.assertEqual(a,render_scene(self.assets,self.page,(640,360)).tobytes())

    def test_missing_or_hidden_anchor(self):
        for anchor in ('missing','rain'):
            d=copy.deepcopy(self.data);d['visual_assets']['pages'][-1]['visual_link']['anchor']=anchor
            with self.subTest(anchor=anchor),self.assertRaisesRegex(ValueError,'anchor'):
                validate_scene_plan(d)

    def test_overlap_needs_opaque_reading_surface(self):
        self.page['scene']['viewport']=[0,0,1,1]
        with self.assertRaisesRegex(ValueError,'surface'):
            validate_scene_plan(self.data)
        self.page['surface']=self.page['background']
        self.assertTrue(validate_scene_plan(self.data))

    def test_invalid_camera_and_geometry(self):
        for bad in (float('nan'),float('inf'),True,0):
            d=copy.deepcopy(self.data);d['visual_assets']['pages'][0]['scene']['camera']=[500,500,bad]
            with self.subTest(value=bad),self.assertRaises(ValueError):validate_scene_plan(d)
        self.page['text_zone']=[.8,.2,.4,.6]
        with self.assertRaisesRegex(ValueError,'fit canvas'):validate_scene_plan(self.data)

    def test_invalid_frame_order(self):
        self.assets['scene_library']['room']['layers'][0]['frames']=[{'at':.7,'x':4},{'at':.2,'x':5}]
        with self.assertRaisesRegex(ValueError,'increase'):validate_scene_plan(self.data)

    def test_interp_and_explicit_state(self):
        l={'x':100,'frames':[{'at':0,'x':200},{'at':1,'x':400}]}
        self.assertEqual(layer_state(l,.5)['x'],300)
        self.assertEqual(layer_state(l,.5,{'x':23})['x'],23)

    def test_visual_edit_invalidates_only_visual_fingerprint(self):
        old=visual_fingerprint(self.data);content=compute_fingerprint(self.meta['lines'])
        self.page['scene']['progress']=.85
        self.assertNotEqual(old,visual_fingerprint(self.data))
        self.assertEqual(content,compute_fingerprint(self.meta['lines']))

    def test_evidence_rejects_stale_plan_deck_and_pixels(self):
        # Minimal fixtures test the evidence binding, not a renderer simulation.
        with tempfile.TemporaryDirectory() as temp:
            t=Path(temp);deck=t/'test.pptx';deck.write_bytes(b'test fixture')
            manifest={'preview':False,'data_fingerprint':self.meta['fingerprint'],
                'visual_fingerprint':visual_fingerprint(self.data),'pptx_sha256':sha(deck),
                'slides':5,'pages':[{'page_id':p['id'],'line_ids':p['line_ids']} for p in self.assets['pages']]}
            for i in range(1,6):(t/f'slide_{i:03}.png').write_bytes(b'fixture pixels')
            receipt={'pptx_sha256':sha(deck),'slide_count':5,'images':{p.name:sha(p) for p in t.glob('slide_*.png')}}
            deck.with_suffix('.manifest.json').write_text(json.dumps(manifest))
            (t/'render_receipt.json').write_text(json.dumps(receipt))
            collect(EXAMPLE,deck,t)
            manifest['visual_fingerprint']='stale'
            deck.with_suffix('.manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'Stale'):collect(EXAMPLE,deck,t)
            manifest['visual_fingerprint']=visual_fingerprint(self.data)
            deck.with_suffix('.manifest.json').write_text(json.dumps(manifest))
            deck.write_bytes(b'new deck')
            with self.assertRaisesRegex(ValueError,'same PPTX'):collect(EXAMPLE,deck,t)
            deck.write_bytes(b'test fixture');(t/'slide_001.png').write_bytes(b'changed pixels')
            with self.assertRaisesRegex(ValueError,'hashes'):collect(EXAMPLE,deck,t)


if __name__=='__main__':unittest.main()
