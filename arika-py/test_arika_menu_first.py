import json
from pathlib import Path
import struct
import unittest
from arika_menu_first import scaled_records,position_source
from arika_menu_layers import setup_calls
from arika_menus import c_elf_image
from test_arika_menus import elf_fixture


class MenuFirstTests(unittest.TestCase):
    def test_decoration_scales_are_two_floats(self):
        payload=struct.pack('<4h4f',474,0,15,26,0,-18,21.5,1)
        words=struct.unpack('<6I',payload)
        record=scaled_records(c_elf_image(elf_fixture(words)),0x1000,1)[0]
        self.assertEqual(record['uv_xywh'],[474,0,15,26])
        self.assertEqual(record['placement'],[0,-18])
        self.assertEqual(record['scale'],[21.5,1])
        self.assertNotIn('anchor_mode',record)

    def test_partial_setup_stops_before_conditional_branch(self):
        elf=c_elf_image(elf_fixture([0x24050009,0x0c0dc978,0,0x10000000,0]))
        result=setup_calls(elf,0x1000,stop_before_branch=True)
        self.assertEqual(result['resources'][0]['entry'],9)
        self.assertEqual(result['stopped_before_branch'],0x100c)
        with self.assertRaises(ValueError):setup_calls(elf,0x1000)

    def test_strip_float_arguments_include_call_delay_slot(self):
        words=[]
        for register,value in [(13,400.0),(14,3150.0)]:
            bits=struct.unpack('<I',struct.pack('<f',value))[0]
            words.extend([0x3c080000|(bits>>16),0x35080000|(bits&65535),0x44880000|(register<<11)])
        words.extend([0x24070001,0x0c0dcffc,0x44806000,0x03e00008,0])
        calls=setup_calls(c_elf_image(elf_fixture(words)),0x1000)
        effect=calls['strip_effects'][0]
        self.assertEqual((effect['orientation'],effect['start'],effect['end'],effect['period']),(1,0,400,3150))

    def test_real_report_counts_and_runtime_position(self):
        report=json.loads((Path(__file__).parent/'research/main_menu_map.json').read_text())['first_components']
        self.assertEqual(len(report['groups']),7)
        self.assertEqual((report['literal_sprite_count'],report['decoration_count'],report['strip_count']),(9,12,4))
        self.assertEqual(report['groups'][0]['base_position']['value'],[0,0])
        self.assertEqual(report['groups'][0]['base_position']['source'],'startup_zero_fill')
        self.assertEqual(report['groups'][4]['decorations'][0]['scale'],[21.5,1])
        self.assertEqual(report['groups'][4]['scroll_strip']['parameters']['period'],2970)
        particles=report['particles']
        self.assertEqual((particles['slot_count'],particles['initial_active_slots'],len(particles['templates'])),(6,5,4))
        self.assertEqual(len(particles['seed_positions']),5)
        self.assertEqual(position_source(c_elf_image(elf_fixture([0,0])),0x2000)['source'],'runtime_memory_unresolved')


if __name__=='__main__':unittest.main()
