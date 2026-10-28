import json
from pathlib import Path
import unittest
from arika_menus import c_elf_image
from arika_menu_layers import setup_calls
from test_arika_menus import elf_fixture


class MenuLayerTests(unittest.TestCase):
    def test_literal_rectangles_use_call_delay_slot(self):
        words=[0x24050002,0x0c0dc978,0,0x8c990000,0x8f390014,
               0x2405000a,0x24060014,0x2407001e,0x0320f809,0x24080028,0x03e00008,0]
        calls=setup_calls(c_elf_image(elf_fixture(words)),0x1000)
        self.assertEqual(calls['resources'],[dict(instruction=0x1004,entry=2)])
        self.assertEqual(calls['rectangles'],[dict(instruction=0x1020,xywh=[10,20,30,40])])

    def test_unknown_arguments_and_branches_fail(self):
        for words in ([0x10000000],[0x8c990000,0x8f390014,0x0320f809,0]):
            with self.assertRaises(ValueError):setup_calls(c_elf_image(elf_fixture(words)),0x1000)
        with self.assertRaisesRegex(ValueError,'bound'):
            setup_calls(c_elf_image(elf_fixture([0])),0x1000,max_instructions=1)

    def test_caller_saved_values_do_not_leak_across_calls(self):
        words=[0x24050002,0x0c0dc978,0,0x8c990000,0x8f390014,
               0x24060014,0x2407001e,0x0320f809,0x24080028,0x03e00008,0]
        with self.assertRaisesRegex(ValueError,'unknown sprite rectangle'):
            setup_calls(c_elf_image(elf_fixture(words)),0x1000)

    def test_direct_jump_and_loop_guard(self):
        words=[0x08000403,0x24050002,0xffffffff,0x0c0dc978,0,0x03e00008,0]
        calls=setup_calls(c_elf_image(elf_fixture(words)),0x1000)
        self.assertEqual(calls['resources'][0]['entry'],2)
        with self.assertRaisesRegex(ValueError,'loop'):
            setup_calls(c_elf_image(elf_fixture([0x08000400,0])),0x1000)

    def test_recovered_layers_keep_unresolved_position_explicit(self):
        report=json.loads((Path(__file__).parent/'research/main_menu_map.json').read_text())
        layout=report['composite_layout'];layers=layout['layers']
        self.assertEqual(len(layers['item_overlays']),7)
        self.assertTrue(all(v['texture_entry']==2 for v in layers['item_overlays']))
        self.assertEqual(sum(len(v['evidence']['rectangles']) for v in layers['shared_setups']),4)
        small=layers['shared_small_components'];self.assertEqual(len(small),7)
        self.assertEqual(small[2]['base_source'],'startup_zero_fill')
        self.assertEqual(small[2]['base_position'],[0,0])
        self.assertEqual(layers['shared_setups'][0]['evidence']['rectangles'][0]['xywh'],[0,0,512,448])
        self.assertEqual(layout['item_overlay_count'],7)
        for c in layout['composites']:
            self.assertEqual(c['item_overlay']['zero_offset_pose']['position'][2],25)


if __name__=='__main__':unittest.main()
