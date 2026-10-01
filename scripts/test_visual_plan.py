"""Focused failure checks for source-bound directing plans."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.dataload import load_song, compute_fingerprint
from scripts.pptx_editorial import validate_plan, build_editorial
from scripts.visual_plan import check_director

EXAMPLES = Path(__file__).resolve().parents[1] / 'examples'


class DirectingTests(unittest.TestCase):
    def setUp(self):
        self.data, self.meta = load_song(EXAMPLES / 'city-call' / 'data.json')
        self.director = self.data['visual_profile']['director']

    def test_complete_examples_and_nonuniform_grouping(self):
        for name in ('quiet-window', 'city-call'):
            data, meta = load_song(EXAMPLES / name / 'data.json')
            self.assertEqual(check_director(data, meta, required=True), [])
            pages, _ = validate_plan(data, meta)
            self.assertEqual(sorted(len(p['line_ids']) for p in pages), [1, 2, 3])

    def test_text_edit_invalidates_plan_before_replacing_output(self):
        self.meta['lines'][0]['zh'] += '（修改）'
        self.meta['fingerprint'] = compute_fingerprint(self.meta['lines'])
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'existing.pptx'
            output.write_bytes(b'previous result')
            with self.assertRaisesRegex(ValueError, 'stale'):
                build_editorial(self.data, self.meta, output)
            self.assertEqual(output.read_bytes(), b'previous result')

    def test_legacy_warns_but_new_plan_requires_director(self):
        del self.data['visual_profile']['director']
        self.assertEqual(len(check_director(self.data, self.meta)), 1)
        with self.assertRaisesRegex(ValueError, 'Missing'):
            check_director(self.data, self.meta, required=True)

    def test_timeline_order_and_repeated_occurrences(self):
        # Identical words have independent IDs and both must remain covered.
        self.assertEqual(self.meta['lines'][0]['jp'], self.meta['lines'][4]['jp'])
        self.assertNotEqual(self.meta['lines'][0]['id'], self.meta['lines'][4]['id'])
        self.director['timeline'][2]['line_ids'][0] = 'city-01'
        with self.assertRaisesRegex(ValueError, 'Timeline must cover'):
            check_director(self.data, self.meta)

    def test_page_phase_and_whole_storyboard_coverage(self):
        pages = self.data['visual_assets']['pages']
        pages[1]['phase_id'] = 'call'
        with self.assertRaisesRegex(ValueError, 'declared timeline phase'):
            check_director(self.data, self.meta)
        pages[1]['phase_id'] = 'cross'
        pages[1]['line_ids'].pop()
        with self.assertRaisesRegex(ValueError, 'Storyboard must cover'):
            check_director(self.data, self.meta)

    def test_repeated_page_needs_prior_reference_and_reason(self):
        page = self.data['visual_assets']['pages'][2]
        for field, value in (('repeat_of', 'unknown-page'), ('repeat_reason', ' ')):
            data = copy.deepcopy(self.data)
            data['visual_assets']['pages'][2][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'repeat_of'):
                check_director(data, self.meta)
        page['repeat_of'] = page['id']
        with self.assertRaises(ValueError):
            check_director(self.data, self.meta)

    def test_text_only_plan_cannot_claim_measured_timing(self):
        self.director['timeline'][0]['bpm'] = 120
        with self.assertRaisesRegex(ValueError, 'lyrics_only'):
            check_director(self.data, self.meta)

    def test_audio_basis_requires_identifiable_recording_and_scope(self):
        self.director['brief']['evidence_basis'] = 'lyrics_and_audio'
        for record in (None, 'listened', {'recording':'original'}):
            self.director['brief']['audio_evidence'] = record
            with self.subTest(record=record), self.assertRaisesRegex(ValueError, 'audio_evidence'):
                check_director(self.data, self.meta)
        self.director['brief']['audio_evidence'] = {'recording':'user-provided demo', 'scope':'first verse'}
        self.assertEqual(check_director(self.data, self.meta), [])

    def test_malformed_blocks_report_contract_errors(self):
        for key, value in (('brief', []), ('system', None), ('timeline', ['bad phase'])):
            data = copy.deepcopy(self.data)
            data['visual_profile']['director'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                check_director(data, self.meta)

    def test_render_spec_rejects_unsupported_typeface_and_four_lines(self):
        page = self.data['visual_assets']['pages'][1]
        page['typeface'] = 'handwritten'
        with self.assertRaisesRegex(ValueError, 'typeface'):
            validate_plan(self.data, self.meta)
        page['typeface'] = 'sans'
        page['line_ids'].append('city-04')
        with self.assertRaisesRegex(ValueError, '1–3'):
            validate_plan(self.data, self.meta)


if __name__ == '__main__':
    unittest.main()
