#!/usr/bin/env python3
"""Decode Super Dragon Ball Z SPT program bundles without inventing event timing."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
from arika_models import require
from arika_import import write_output
from arika_actions import c_elf_reader, REFERENCE_SHA256


def parse(data):
    require(len(data)>=4,'truncated SPT bundle')
    count,=struct.unpack_from('<I',data)
    require(0<count<=1024 and 4+count*4<=len(data),'invalid SPT program directory')
    sizes=struct.unpack_from('<'+'I'*count,data,4)
    at=4+count*4;programs=[]
    for index,size in enumerate(sizes):
        require(size>=28 and at+size<=len(data),'invalid SPT program extent')
        reserved,variables,length,*entries=struct.unpack_from('<7I',data,at)
        require(size==28+length,'SPT bytecode size mismatch')
        start=at+28;end=at+size;cursor=start;tokens=[]
        while cursor<end:
            require(cursor+5<=end,'truncated SPT token')
            offset=cursor-start;kind,value=struct.unpack_from('<BI',data,cursor);cursor+=5
            require(kind<6,'unsupported SPT token type')
            token=dict(offset=offset,type=kind,payload=value)
            if kind==0:
                token['float_bits_hex']='%08x'%value
            elif kind==1:
                require(cursor+value+1<=end,'truncated SPT string')
                raw=data[cursor:cursor+value+1];cursor+=value+1
                require(raw[-1]==0,'unterminated SPT string')
                token['string_bytes_hex']=raw.hex()
                token['text']=raw[:-1].decode('cp932',errors='replace')
            elif kind==2:
                length_extra=value>>16
                require(cursor+length_extra<=end,'truncated SPT command data')
                token.update(command_id=value&65535,extra_hex=data[cursor:cursor+length_extra].hex())
                cursor+=length_extra
            elif kind==3:
                token.update(variable_index=value&65535,variable_type=value>>16)
            elif kind==4:
                token['symbol']=chr(value) if 32<=value<127 else None
            token['byte_length']=cursor-start-offset
            tokens.append(token)
        boundaries={t['offset'] for t in tokens}|{size-28}
        require(all(e in boundaries for e in entries),'SPT entry point is not a token boundary')
        programs.append(dict(index=index,file_offset=at,size=size,reserved=reserved,variable_count=variables,
                             bytecode_size=size-28,entry_points=entries,tokens=tokens))
        at=end
    return dict(format='ARIKA_SPT',source_sha256=hashlib.sha256(data).hexdigest(),programs=programs,
                trailing_hex=data[at:].hex())


def rebuild(document):
    require(document.get('format')=='ARIKA_SPT','expected ARIKA_SPT document')
    bodies=[]
    for program in document['programs']:
        code=bytearray()
        for token in program['tokens']:
            require(token['offset']==len(code),'token offsets changed; control-flow relocation is unsupported')
            kind=token['type'];value=token['payload']
            code.extend(struct.pack('<BI',kind,value))
            if kind==1:
                raw=bytes.fromhex(token['string_bytes_hex'])
                require(len(raw)==value+1 and raw[-1]==0,'string length must match its token payload')
                code.extend(raw)
            elif kind==2:
                raw=bytes.fromhex(token['extra_hex'])
                require(len(raw)==value>>16,'command extra length mismatch')
                code.extend(raw)
            require(len(code)-token['offset']==token['byte_length'],'token size changed')
        require(len(code)==program['bytecode_size'],'program length changed')
        body=struct.pack('<7I',program['reserved'],program['variable_count'],len(code),*program['entry_points'])+code
        require(len(body)==program['size'],'program size changed')
        bodies.append(body)
    result=struct.pack('<I',len(bodies))+struct.pack('<'+'I'*len(bodies),*[len(b) for b in bodies])+b''.join(bodies)+bytes.fromhex(document['trailing_hex'])
    parse(result)
    return result


def registry(data):
    require(hashlib.sha256(data).hexdigest()==REFERENCE_SHA256,'command registry requires the reference ELF')
    reader=c_elf_reader(data);commands=[]
    for pc in range(0x2F9DB8,0x2FAD48,4):
        word,=struct.unpack('<I',reader.read(pc,4))
        if word>>26!=3:continue
        target=(word&0x3ffffff)*4
        if target==0x2F41D0:continue
        commands.append(dict(command_id=len(commands),constructor=target,registration_call=pc))
    require(len(commands)==77,'unexpected command registration count')
    # These names describe verified behavior; original source names are unknown.
    commands[68].update(behavior='set_face_and_hair_form',handler=0x2F6980,native=0x2E19F0)
    commands[69].update(behavior='start_character_facial_program',handler=0x2F6AA0,native=0x2E1BF0)
    return dict(format='ARIKA_SPT_COMMANDS',elf_sha256=REFERENCE_SHA256,commands=commands)


def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True)
    q=s.add_parser('json');q.add_argument('input');q.add_argument('output')
    q=s.add_parser('import-json');q.add_argument('original');q.add_argument('edited');q.add_argument('output')
    q=s.add_parser('registry');q.add_argument('elf');q.add_argument('output')
    args=p.parse_args()
    try:
        if args.command=='json':
            data=parse(Path(args.input).read_bytes());body=json.dumps(data,indent=2,ensure_ascii=False).encode();inputs=[args.input]
        elif args.command=='registry':
            body=json.dumps(registry(Path(args.elf).read_bytes()),indent=2).encode();inputs=[args.elf]
        else:
            original=Path(args.original).read_bytes();edited=json.loads(Path(args.edited).read_text(encoding='utf-8'))
            require(edited['source_sha256']==hashlib.sha256(original).hexdigest(),'edited script belongs to another source')
            before=parse(original)
            require(len(before['programs'])==len(edited['programs']),'program count changed')
            for a,b in zip(before['programs'],edited['programs']):
                require((a['size'],a['entry_points'],a['variable_count'])==(b['size'],b['entry_points'],b['variable_count']),'program layout changed')
            body=rebuild(edited);inputs=[args.original,args.edited]
        write_output(args.output,body,inputs);print('Wrote '+args.output)
    except (ValueError,OSError,KeyError,TypeError,struct.error) as error:
        print('error: '+str(error),file=sys.stderr);return 1
    return 0


if __name__=='__main__':sys.exit(main())
