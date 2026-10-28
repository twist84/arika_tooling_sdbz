import copy
from pathlib import Path
import struct
import tempfile
import unittest
from arika_cht import parse_cht, lookup, load_banks, resolve, runtime_motion_name
from arika_actions import resolve_action
from test_arika_import import package_fixture


def fixture():
    data=bytearray(b'\0\0\1\0CHT '+bytes(8)+struct.pack('<I',2))
    data+=b'test'.ljust(32,b'\0')+b'common'.ljust(32,b'\0')
    data+=struct.pack('<18I',0xDEADBEEF,*([0]*17))
    data+=bytes((-len(data))%16)+bytes(32)+b'\xA5'*4000
    data+=struct.pack('<3I',232,2,0x12345678)
    at=len(data);data+=bytes(272)
    struct.pack_into('<IHH',data,at,0xFFFFFFFF,0,0)
    struct.pack_into('<IHH',data,at+136,0xFFFFFFFF,1,1)
    for field in (8,72,104):struct.pack_into('<I',data,at+field,0x12345678)
    child=len(data);data+=bytes(68)
    for field in (36,64):struct.pack_into('<I',data,child+field,1)
    data+=bytes((-len(data))%16)+bytes(64)
    child=len(data);data+=bytes(36);struct.pack_into('<I',data,child+4,1)
    data+=bytes((-len(data))%16)+bytes(32)+bytes(12)
    return data


class ChtTests(unittest.TestCase):
    def test_nested_layout_and_garbage_runtime_pointers(self):
        data=fixture();document=parse_cht(data)
        self.assertEqual(document['byte_size'],len(data))
        self.assertEqual(document['name_table'],['test','common'])
        self.assertEqual(lookup(document,232,0)['child_blocks'],dict(type_68=1,type_36=1,type_32=3,type_12=1))
        self.assertEqual(lookup(document,232,1)['resource_bank'],1)

    def test_truncation_and_corruption(self):
        original=fixture();document=parse_cht(original);record=lookup(document,232,0)
        for end in (19,40,100,len(original)-1):
            with self.assertRaises(ValueError):parse_cht(original[:end])
        for offset,fmt,value in [(16,'I',0xFFFFFFFF),(document['actions'][0]['offset'],'I',1000),
            (document['actions'][0]['offset']+4,'I',0xFFFFFFFF),(record['offset']+4,'H',2)]:
            data=bytearray(original);struct.pack_into('<'+fmt,data,offset,value)
            with self.assertRaises(ValueError):parse_cht(data)
        with self.assertRaises(ValueError):parse_cht(original+b'\0')

    def test_lookup_missing_bounds_and_last_duplicate_wins(self):
        document=parse_cht(fixture())
        for motion,variant in [(1000,0),(-1,0),(1,0),(232,2),(232,-1)]:
            with self.assertRaises(ValueError):lookup(document,motion,variant)
        replacement=copy.deepcopy(document['actions'][0]);replacement['variants']=[]
        document['actions'].append(replacement)
        with self.assertRaises(ValueError):lookup(document,232,0)

    def test_runtime_name_copy_and_exact_case(self):
        self.assertEqual(runtime_motion_name('m01232m0a.mot'),'m01232m0a')
        self.assertEqual(runtime_motion_name('name.part.mot'),'name')
        self.assertEqual(runtime_motion_name('1234567890123456'),'123456789012345')
        self.assertEqual(runtime_motion_name('NAME.MOT'),'NAME')

    def test_resolution_banks_and_missing_names(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'motions.pmt';path.write_bytes(package_fixture())
            banks=load_banks(['0='+str(path)]);document=parse_cht(fixture())
            self.assertEqual(resolve(lookup(document,232,0),banks)['package_index'],0)
            self.assertEqual(resolve(lookup(document,232,1),banks)['status'],'missing_bank')
            self.assertEqual(resolve(dict(motion_name='TEST',resource_bank=0),banks)['status'],'missing_motion')
            with self.assertRaises(ValueError):load_banks(['0='+str(path),'0='+str(path)])
            with self.assertRaises(ValueError):load_banks(['bad'])

    def test_action_segments_keep_flags_and_unresolved_entries(self):
        document=parse_cht(fixture())
        action=dict(slot=55,address=0x1234,records=[dict(motion_id=232,variant=0,flags=0x20000),dict(motion_id=55,variant=0,flags=0x10000)])
        banks={0:dict(path='test.pmt',sha256='hash',names={'test':dict(index=7,name='test.mot')})}
        result=resolve_action(action,document,banks)
        self.assertEqual(result['segments'][0]['binding']['package_index'],7)
        self.assertEqual(result['segments'][0]['flags'],0x20000)
        self.assertEqual(result['segments'][1]['binding']['status'],'missing_cht_entry')


if __name__=='__main__':unittest.main()
