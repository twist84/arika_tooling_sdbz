import json
from pathlib import Path
import struct
import unittest
from arika_menus import c_elf_image
from arika_menu_startup import c_startup_image
from menu_strip_oracle import c_strip_oracle
from test_arika_menus import elf_fixture


class MenuStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.report=json.loads((Path(__file__).parent/'research/main_menu_map.json').read_text())

    def test_zero_fill_is_mapped_not_unbounded(self):
        data=bytearray(elf_fixture([0x11223344]));struct.pack_into('<I',data,52+20,16)
        raw=c_elf_image(bytes(data));image=c_startup_image(raw)
        self.assertEqual(image.read(0x1002,4),b'\x22\x11\0\0')
        self.assertEqual(image.source_kind(0x1004,4),'startup_zero_fill')
        with self.assertRaises(ValueError):raw.read(0x1004,4)
        with self.assertRaises(ValueError):image.read(0x1010,1)

    def test_initializer_return_delay_slot_write(self):
        words=[0x3c033f80,0x44830000,0x3c040000,0x03e00008,0xe4801040]
        data=bytearray(elf_fixture(words));struct.pack_into('<I',data,52+20,128)
        image=c_startup_image(c_elf_image(bytes(data)));image.run_initializer(0x1000,0)
        self.assertEqual(image.words(0x1040,1),[0x3f800000])
        self.assertEqual(image.source_kind(0x1040,4),'startup_constructor')

    def test_two_initializers_match_native_scalar_execution(self):
        startup=self.report['startup'];first,second=startup['functions']
        kernel=dict(draw_address=first['address'],draw_words=first['words'],clock_address=second['address'],clock_words=second['words'])
        machine=c_strip_oracle(kernel,[0,0,1,1],0,0,1,1,0,[0,0])
        machine.m_registers[28]=self.report['text_lookup']['global_pointer']
        for source in startup['inputs']:machine.write_int(source['address'],source['bits'],4)
        machine.run(first['address']);machine.run(second['address'])
        self.assertEqual(len(startup['writes']),5)
        for write in startup['writes']:self.assertEqual(machine.read_int(write['address'],4),write['bits'])

    def test_companion_heights_and_newly_resolved_geometry(self):
        self.assertEqual([t['y_base'] for t in self.report['shared_companions']['templates']],[320,324,352])
        self.assertEqual(self.report['plain_sprite_geometry']['first_quad_count'],21)
        self.assertEqual(self.report['plain_sprite_geometry']['shared_quad_count'],10)
        self.assertEqual(self.report['shared_companions']['reset_position_initial'],[0,0])
        first=self.report['first_components']['groups']
        self.assertEqual(first[0]['scroll_strip']['startup_origin'],[0,0])
        self.assertEqual(first[4]['scroll_strip']['startup_origin'],[0,134])
        values={v['address']:v['value'] for v in self.report['startup']['position_values']}
        self.assertEqual(values[0x4fdc5c],204);self.assertEqual(values[0x4fdc60],239)

    def test_bad_extent_and_unsupported_initializer_fail(self):
        data=bytearray(elf_fixture([0]));struct.pack_into('<I',data,52+20,0)
        with self.assertRaises(ValueError):c_startup_image(c_elf_image(bytes(data)))
        image=c_startup_image(c_elf_image(elf_fixture([0xffffffff])))
        with self.assertRaises(ValueError):image.run_initializer(0x1000,0)


if __name__=='__main__':unittest.main()
