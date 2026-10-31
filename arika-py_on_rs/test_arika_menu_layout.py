import json
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
from arika_menu_layout import pose_part,layout_svg


class MenuLayoutTests(unittest.TestCase):
    def setUp(self):
        report=json.loads((Path(__file__).parent/'research/main_menu_map.json').read_text())
        self.layout=report['composite_layout']

    def test_all_composites_and_anchor_layouts(self):
        self.assertEqual([len(c['parts']) for c in self.layout['composites']],[7,4,9,8,5,3,2])
        self.assertEqual(self.layout['part_count'],38)
        self.assertEqual(len(self.layout['anchors']),9)
        for composite in self.layout['composites']:
            for part in composite['parts']:
                self.assertEqual(pose_part(composite,part,self.layout['anchors']),part['zero_offset_pose'])

    def test_centered_rect_and_reversed_uv(self):
        c=dict(base_position=[100,200],component_offset_sign=1)
        p=dict(uv_fields=[10,20,40,60],uv_interpretation='xywh',placement=[0,0,2],anchor_mode=0)
        pose=pose_part(c,p,self.layout['anchors'])
        self.assertEqual(pose['bounds'],[80,170,120,230])
        self.assertEqual(pose['uv_endpoints'],[10,20,50,80])
        p.update(uv_fields=[50,80,10,20],uv_interpretation='endpoints')
        reverse=pose_part(c,p,self.layout['anchors'])
        self.assertEqual(reverse['bounds'],pose['bounds'])
        self.assertEqual(reverse['uv_endpoints'],[50,80,10,20])

    def test_animation_offset_sign_and_anchor(self):
        c=dict(base_position=[100,200],component_offset_sign=-1)
        p=dict(uv_fields=[0,0,20,30],uv_interpretation='xywh',placement=[5,6,2],anchor_mode=3)
        pose=pose_part(c,p,self.layout['anchors'],component_offset=(10,20),part_offset=(3,4),component_depth=7)
        self.assertEqual(pose['position'],[98,190,24])
        self.assertEqual(pose['bounds'],[78,190,98,220])
        p['anchor_mode']=9
        with self.assertRaisesRegex(ValueError,'anchor'):pose_part(c,p,self.layout['anchors'])

    def test_svg_is_valid_and_labels_diagnostic_limits(self):
        svg=layout_svg(self.layout)
        root=ET.fromstring(svg)
        self.assertEqual(root.tag,'{http://www.w3.org/2000/svg}svg')
        self.assertEqual(svg.count('sprite parts + overlay +'),7)
        self.assertIn('zero animation offsets',svg)
        self.assertIn('diagram auto-fit',svg)


if __name__=='__main__':unittest.main()
