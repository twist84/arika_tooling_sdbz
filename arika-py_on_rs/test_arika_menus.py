import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from arika_menus import c_elf_image,neighbor_getter,route_case,analyze_menu,initializer_stores,text_block,elf_global_pointer


def elf_fixture(words):
    data=bytearray(256+4*len(words));data[:7]=b'\x7fELF\x01\x01\x01'
    struct.pack_into('<H',data,18,8);struct.pack_into('<I',data,28,52)
    struct.pack_into('<HH',data,42,32,1)
    struct.pack_into('<8I',data,52,1,256,0x1000,0x1000,len(words)*4,len(words)*4,5,4)
    struct.pack_into('<'+'I'*len(words),data,256,*words)
    return bytes(data)


class MenuResearchTests(unittest.TestCase):
    def test_initializer_recovers_store_in_return_delay_slot(self):
        # LUI v1,0x61; ADDIU a0,gp,-4; JR ra; SW a0,-0x3940(v1).
        elf=c_elf_image(elf_fixture([0x3c030061,0x2784fffc,0x03e00008,0xac64c6c0]))
        self.assertEqual(initializer_stores(elf,0x1000,0x4ff370),
            {0x60c6c0:dict(value=0x4ff36c,instruction=0x100c)})

    def test_initializer_rejects_unknown_and_unbounded_code(self):
        for words in ([0x8c820000],[0x24840001],[0xac640000],[0x10000000]):
            with self.assertRaises(ValueError):initializer_stores(c_elf_image(elf_fixture(words)),0x1000,0,max_instructions=1)
        with self.assertRaisesRegex(ValueError,'bounded return'):
            initializer_stores(c_elf_image(elf_fixture([0,0])),0x1000,0,max_instructions=2)

    def test_counted_help_text_not_c_string(self):
        data=bytearray(elf_fixture([2,0x1010,0x1014,0,0x00656e4f,0x006f7754]))
        block=text_block(c_elf_image(bytes(data)),0x1000)
        self.assertEqual([x['text'] for x in block['lines']],['One','Two'])
        with self.assertRaisesRegex(ValueError,'line count'):text_block(c_elf_image(elf_fixture([0])),0x1000)

    def test_global_pointer_from_reginfo_section(self):
        data=bytearray(elf_fixture([0]));section_offset=len(data);data.extend(bytes(40+24))
        struct.pack_into('<I',data,32,section_offset);struct.pack_into('<HH',data,46,40,1)
        struct.pack_into('<10I',data,section_offset,0,0x70000006,0,0,section_offset+40,24,0,0,4,0)
        struct.pack_into('<I',data,section_offset+60,0x4ff370)
        self.assertEqual(elf_global_pointer(c_elf_image(bytes(data))),0x4ff370)
        struct.pack_into('<I',data,section_offset+20,23)
        with self.assertRaisesRegex(ValueError,'reginfo'):elf_global_pointer(c_elf_image(bytes(data)))

    def test_elf_bounds_and_build_guard(self):
        elf=c_elf_image(elf_fixture([1,2,3,4,5]))
        self.assertEqual(elf.words(0x1000,2),[1,2])
        with self.assertRaises(ValueError):elf.read(0x1000,100)
        with self.assertRaises(ValueError):c_elf_image(b'bad')
        with self.assertRaisesRegex(ValueError,'unsupported ELF'):analyze_menu(elf_fixture([1]))

    def test_neighbor_constants_and_flag_movz(self):
        for word,result in [(0x2402ffff,-1),(0x24020003,3),(0x102d,0)]:
            elf=c_elf_image(elf_fixture([0x03e00008,word,0,0,0]))
            self.assertEqual(neighbor_getter(elf,0x1000)['value'],result)
        elf=c_elf_image(elf_fixture([0x90840710,0x24020002,0x24030001,0x03e00008,0x0064100a]))
        result=neighbor_getter(elf,0x1000)
        self.assertEqual((result['flag_offset'],result['if_clear'],result['if_set']),(1808,1,2))

    def test_routes_read_machine_constants(self):
        elf=c_elf_image(elf_fixture([0x24110005,0x10000007,0x2410002c]))
        self.assertEqual(route_case(elf,0x1000)['next_app_id'],44)
        self.assertEqual(route_case(elf,0x1000)['mode_selector'],5)
        elf=c_elf_image(elf_fixture([0x24110007,0x0c0ca944,0]))
        self.assertEqual(route_case(elf,0x1000)['next_app_id'],46)

    @unittest.skipUnless(shutil.which('g++'),'g++ required for C++ reconstruction comparison')
    def test_cpp_matches_binary_extracted_tables(self):
        root=Path(__file__).parent;report=json.loads((root/'research/main_menu_map.json').read_text())
        checks=[]
        for item in report['menu']['items']:
            checks.append('assert(menu.set_selected(%d));'%item['index'])
            for flag_0 in (False,True):
                for flag_2 in (False,True):
                    for direction,neighbor in enumerate(item['neighbors']):
                        flag=flag_0 if item['index']==0 else flag_2
                        expected=neighbor['value'] if 'value' in neighbor else neighbor['if_set' if flag else 'if_clear']
                        checks.append('assert(menu.get_neighbor(%d,%s,%s)==%d);'%(direction,str(flag_0).lower(),str(flag_2).lower(),expected))
            route=item['route']
            checks.append('assert(menu.get_route(false).mode_selector==%d);'%route['mode_selector'])
            checks.append('assert(menu.get_route(false).next_app_id==%d);'%route['next_app_id'])
        checks+=['assert(menu.get_route(true).next_app_id==3);','assert(menu.get_route(true).mode_selector==-1);','assert(!menu.set_selected(7));','assert(menu.get_neighbor(4,false,false)==-1);']
        for previous in range(7):
            for item in report['menu']['items']:
                for direction,neighbor in enumerate(item['neighbors']):
                    flag=previous==2 if item['index']==0 else previous in (0,1,5)
                    expected=neighbor['value'] if 'value' in neighbor else neighbor['if_set' if flag else 'if_clear']
                    checks+=['assert(menu.set_selected(%d));'%previous,'assert(menu.set_selected(%d));'%item['index'],
                             'assert(menu.get_previous()==%d);'%previous,'assert(menu.get_neighbor(%d)==%d);'%(direction,expected)]
        checks+=['c_main_menu_logic initial;','assert(initial.get_previous()==-1);','assert(initial.get_neighbor(3)==1);',
                 'assert(!initial.move(1));','assert(initial.get_previous()==-1);','assert(initial.move(3));',
                 'assert(initial.get_selected()==1);','assert(initial.get_previous()==0);']
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'check.cpp';exe=Path(tmp)/'check'
            path.write_text('#include "arika_menu_logic.h"\n#include <cassert>\nint main(){c_main_menu_logic menu;\n'+'\n'.join(checks)+'\n}\n')
            subprocess.run(['g++','-std=c++03','-Wall','-Wextra','-pedantic','-I',str(root),str(path),'-o',str(exe)],check=True,capture_output=True)
            subprocess.run([str(exe)],check=True)
