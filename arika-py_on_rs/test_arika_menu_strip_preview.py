import json
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
from arika_menu_layout import f32
from arika_menu_strip_preview import HALF_PI,strip_basis,command_quad,quad_trace,animated_svg
from menu_rotation_oracle import native_matrix


class MenuStripPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(__file__).parent
        cls.report=json.loads((cls.root/'research/main_menu_map.json').read_text())
        cls.kernel=cls.report['strip_rotation_kernels'];cls.anchors=cls.report['composite_layout']['anchors']

    def test_both_angles_match_interpreted_native_vu_basis(self):
        for angle in (0,HALF_PI):
            basis=strip_basis(angle,self.kernel['polynomial']);matrix=native_matrix(self.kernel,angle)
            self.assertEqual(basis['x_axis'],matrix[0][:2]);self.assertEqual(basis['y_axis'],matrix[1][:2])

    def test_rotation_direction_and_anchor(self):
        command=dict(piece=0,uv_xywh=[412,0,100,20],position=[132,86],depth=0,rotation=HALF_PI,anchor_mode=3)
        quad=command_quad(command,self.anchors,self.kernel)
        self.assertEqual(quad['bounds'],[132,86,152,186])
        self.assertEqual(quad['uv_endpoints'],[412,0,512,20])

    def test_all_9441_example_commands_match_native_matrix_transform(self):
        matrices={angle:native_matrix(self.kernel,angle) for angle in (0,HALF_PI)};count=0
        for item in (2,6):
            trace=json.loads((self.root/('examples/menu_strip_item%d_trace.json'%item)).read_text())
            for frame in trace['frames']:
                for command in frame['commands']:
                    actual=command_quad(command,self.anchors,self.kernel)
                    matrix=matrices[command['rotation']];uv=command['uv_xywh'];expected=[]
                    for a,b in self.anchors[command['anchor_mode']]['vertices']:
                        x=f32(a*uv[2]);y=f32(b*uv[3]);row=[]
                        for i in (0,1):
                            transformed=f32(f32(x*matrix[0][i])+f32(y*matrix[1][i]))
                            row.append(f32(transformed+command['position'][i]))
                        expected.append(row)
                    self.assertEqual(actual['vertices'],expected);count+=1
        self.assertEqual(count,9441)

    def test_svg_discrete_timeline_and_missing_piece_visibility(self):
        source=json.loads((self.root/'examples/menu_strip_item2_trace.json').read_text())
        source['frames']=source['frames'][:2];source['frames'][0]['commands']=[]
        trace=quad_trace(source,self.report);svg=animated_svg(trace,stride=1,ticks_per_second=2)
        root=ET.fromstring(svg);namespace={'s':'http://www.w3.org/2000/svg'}
        animations=root.findall('.//s:animate',namespace)
        self.assertEqual(len(animations),4)
        self.assertTrue(all(a.attrib['calcMode']=='discrete' and a.attrib['dur']=='1s' for a in animations))
        self.assertTrue(all(a.attrib['keyTimes']=='0;0.5;1' for a in animations))
        self.assertIn('visibility="hidden"',svg)
        self.assertIn('No textures or native frame timing',svg)

    def test_invalid_trace_rotation_and_rate(self):
        with self.assertRaises(ValueError):strip_basis(0.5,self.kernel['polynomial'])
        source=json.loads((self.root/'examples/menu_strip_item2_trace.json').read_text())
        source['elf_sha256']='wrong'
        with self.assertRaises(ValueError):quad_trace(source,self.report)
        trace=dict(item=2,frames=[dict(tick=0,quads=[])])
        with self.assertRaises(ValueError):animated_svg(trace,stride=0)
        with self.assertRaises(ValueError):animated_svg(trace,ticks_per_second=0)


if __name__=='__main__':unittest.main()
