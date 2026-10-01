"""Focused contracts for ID-bound visual pages and punctuation ruby alignment."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.pptx_editorial import validate_plan, wrap_units, _names
from scripts.pptx_furigana import align_reading

class EditorialTests(unittest.TestCase):
    def setUp(self):
        self.meta={'lines':[{'id':'a','section':'Verse','jp':'空'}, {'id':'b','section':'Verse','jp':'空'}]}
        self.page={'id':'p1','line_ids':['a','b'],'background':'FFFFFF','ink':'112233','secondary':'445566','accent':'2345AB','reason':'A quiet opening','layout':'left'}
        self.data={'visual_assets':{'pages':[self.page]}}
    def test_order_and_occurrence(self):
        validate_plan(self.data,self.meta)
        self.page['line_ids']=['b','a']
        with self.assertRaises(ValueError):validate_plan(self.data,self.meta)
    def test_duplicate_occurrence(self):
        self.page['line_ids']=['a','a']
        with self.assertRaises(ValueError):validate_plan(self.data,self.meta)
    def test_unknown_id(self):
        self.page['line_ids']=['a','missing']
        with self.assertRaises(ValueError):validate_plan(self.data,self.meta)
    def test_low_annotation_contrast(self):
        self.page['secondary']='EEEEEE'
        with self.assertRaises(ValueError):validate_plan(self.data,self.meta)
    def test_nonfinite_and_out_of_range_geometry(self):
        for field,value in [('font_size',float('inf')),('vertical',-1),('gap',-20),('font_size',True)]:
            with self.subTest(field=field,value=value):
                data=copy.deepcopy(self.data)
                data['visual_assets']['pages'][0][field]=value
                with self.assertRaises(ValueError):validate_plan(data,self.meta)
    def test_bad_motif(self):
        self.page['motifs']=[{'type':'invented','reason':'test'}]
        with self.assertRaises(ValueError):validate_plan(self.data,self.meta)
    def test_punctuation_anchor(self):
        units=align_reading('嗚呼、いつもの様に','Aa, itsumo no you ni')
        self.assertEqual(''.join(x['base'] for x in units),'嗚呼、いつもの様に')
        self.assertIn({'base':'嗚呼','ruby':'ああ'},units)
        self.assertIn({'base':'様','ruby':'よう'},units)
    def test_punctuation_before_another_kanji(self):
        units=align_reading('嗚呼、感じたままに描く','Aa, kanjita mama ni egaku')
        self.assertIn({'base':'嗚呼','ruby':'ああ'},units)
        self.assertTrue(any(u['ruby'] for u in units if '描' in u['base']))
    def test_katakana_and_syllabic_n(self):
        self.assertIn({'base':'見','ruby':'み'},align_reading('見ないフリしていても','Minai furi shiteitemo'))
        self.assertTrue(any(u['ruby'] for u in align_reading('そんな気持ち','Sonna kimochi')))
    def test_wrapping_preserves_units(self):
        units=[{'base':'未来','ruby':'みらい'},{'base':'を','ruby':''},{'base':'描','ruby':'えが'},{'base':'く','ruby':''}]
        rows=wrap_units(units,50,150)
        self.assertEqual([x for row in rows for x in row],units)
    def test_cover_no_duplicate_artist(self):
        self.assertEqual(_names({'title':'群青 — YOASOBI','info_rows':[['演唱者','YOASOBI（Ayase × ikura）']]}),('群青','YOASOBI'))

if __name__=='__main__':unittest.main()
