#!/usr/bin/env python3
"""Decode Super Dragon Ball Z SPT program bundles without inventing event timing."""
import argparse
import hashlib
import json
import math
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


def decompile(data, command_names=None):
    """Decompile an SPT bundle into human-readable pseudocode.

    Returns a dict with 'programs' (list of dicts with 'index' and 'lines')
    and 'format' fields.
    """
    doc = parse(data)
    result = {'format': 'ARIKA_SPT_PSEUDO', 'programs': []}

    # Load command names from JSON file if not provided
    if command_names is None:
        cmd_names_path = Path(__file__).parent / 'spt_command_names.json'
        if cmd_names_path.exists():
            try:
                with open(cmd_names_path) as f:
                    cmd_names_data = json.load(f)
                command_names = {int(k): v for k, v in cmd_names_data.get('command_names', {}).items()}
            except Exception:
                command_names = {}

    # Known command names from ELF cross-referencing
    CMD_NAMES = dict(command_names or {})
    CMD_NAMES.update({
        68: 'set_face_and_hair_form',
        69: 'start_character_facial_program',
    })

    # Symbol value to character mapping
    SYM_CHARS = {
        38: '&', 40: '(', 41: ')', 43: '+', 44: ',', 45: '-',
        58: ':', 61: '=', 62: '>', 123: '{', 125: '}',
    }

    # Special symbol values
    SYM_QUESTION = 15677  # 0x3D3D - separator in arg lists
    SYM_QUESTION2 = 15421  # 0x3C3D - possibly <=
    SYM_QUESTION3 = 15933  # 0x3E3D - possibly >=

    def sym_char(v):
        if v in SYM_CHARS:
            return SYM_CHARS[v]
        if 32 <= v < 127:
            return chr(v)
        if v == SYM_QUESTION:
            return '??'
        if v == SYM_QUESTION2:
            return '<=?'
        if v == SYM_QUESTION3:
            return '>=?'
        return '0x%04X' % v

    def float_str(bits):
        f = struct.unpack('<f', struct.pack('<I', bits & 0xFFFFFFFF))[0]
        if math.isnan(f) or math.isinf(f):
            return '0x%08X' % bits
        if f == int(f) and abs(f) < 1e6:
            return str(int(f))
        return '%.6g' % f

    def var_str(idx, vtype):
        tname = 'f' if vtype == 0 else 's' if vtype == 1 else 't%d' % vtype
        return 'v%d:%s' % (idx, tname)

    def cmd_name(cid):
        return CMD_NAMES.get(cid, 'cmd%d' % cid)

    def extra_params(hexstr):
        """Decode extra data bytes into readable parameters."""
        if not hexstr:
            return ''
        bytes_val = bytes.fromhex(hexstr)
        if len(bytes_val) >= 8:
            # Show as four u16 values (animation/frame parameters)
            u1 = struct.unpack('<H', bytes_val[0:2])[0]
            u2 = struct.unpack('<H', bytes_val[2:4])[0]
            u3 = struct.unpack('<H', bytes_val[4:6])[0]
            u4 = struct.unpack('<H', bytes_val[6:8])[0]
            return '%d,%d,%d,%d' % (u1, u2, u3, u4)
        elif len(bytes_val) >= 4:
            v = struct.unpack('<I', bytes_val[0:4])[0]
            return str(v)
        return hexstr

    for prog in doc['programs']:
        tokens = prog['tokens']
        lines = []
        indent = 0
        i = 0

        while i < len(tokens):
            tok = tokens[i]
            t = tok['type']

            # ---------- SYMBOL ----------
            if t == 4:
                sv = tok['payload']
                if sv == 123:  # {
                    lines.append(' ' * indent + '{')
                    indent += 2
                elif sv == 125:  # }
                    indent = max(0, indent - 2)
                    lines.append(' ' * indent + '}')
                elif sv in (58, 61, 40, 41, 44, 43, 45, 62, 60, 38):
                    pass  # handled in context
                else:
                    lines.append(' ' * indent + '/* sym %s */' % sym_char(sv))
                i += 1
                continue

            # ---------- COMMAND ----------
            if t == 2:
                cid = tok['command_id']
                extra = tok.get('extra_hex', '')

                # CMD id=0: variable declaration (followed by VAR)
                if cid == 0 and i + 1 < len(tokens) and tokens[i+1]['type'] == 3:
                    vt = tokens[i+1]['variable_type']
                    vname = var_str(tokens[i+1]['variable_index'], vt)
                    tname = 'float' if vt == 0 else 'string' if vt == 1 else 'type%d' % vt
                    lines.append(' ' * indent + '%s %s' % (tname, vname))
                    i += 2
                    continue

                # CMD id=2: string variable declaration
                if cid == 2 and i + 1 < len(tokens) and tokens[i+1]['type'] == 3:
                    vt = tokens[i+1]['variable_type']
                    vname = var_str(tokens[i+1]['variable_index'], vt)
                    lines.append(' ' * indent + 'string %s' % vname)
                    i += 2
                    continue

                # CMD id=6/7/8: assignment target marker (followed by : + VAR)
                if cid in (6, 7, 8) and i + 2 < len(tokens):
                    if tokens[i+1]['type'] == 4 and tokens[i+1]['payload'] == 58 and tokens[i+2]['type'] == 3:
                        vname = var_str(tokens[i+2]['variable_index'], tokens[i+2]['variable_type'])
                        lines.append(' ' * indent + '%s :=' % vname)
                        i += 3
                        continue

                # Regular command call: CMD id=X ( args )
                # Only scan for arguments if next token is (
                j = i + 1
                args = []
                has_parens = False
                if j < len(tokens) and tokens[j]['type'] == 4 and tokens[j]['payload'] == 40:
                    has_parens = True
                    j += 1
                    while j < len(tokens):
                        tj = tokens[j]['type']
                        if tj == 4:
                            sv = tokens[j]['payload']
                            if sv == 40:  # (
                                j += 1
                                continue
                            if sv in (41, 125):  # ) or }
                                j += 1
                                break
                            if sv == 44:  # ,
                                j += 1
                                continue
                            args.append(sym_char(sv))
                            j += 1
                            continue
                        if tj == 0:  # FLOAT
                            args.append(float_str(tokens[j]['payload']))
                            j += 1
                            continue
                        if tj == 1:  # STRING
                            args.append('"%s"' % tokens[j].get('text', ''))
                            j += 1
                            continue
                        if tj == 3:  # VARIABLE
                            args.append(var_str(tokens[j]['variable_index'], tokens[j]['variable_type']))
                            j += 1
                            continue
                        break

                extra_part = '(%s)' % extra_params(extra) if extra else ''
                call_str = '%s%s(%s)' % (cmd_name(cid), extra_part, ', '.join(args))
                lines.append(' ' * indent + call_str)
                i = j
                continue

            # ---------- VARIABLE ----------
            if t == 3:
                vname = var_str(tok['variable_index'], tok['variable_type'])
                # Check if followed by = (assignment)
                if i + 1 < len(tokens) and tokens[i+1]['type'] == 4 and tokens[i+1]['payload'] == 61:
                    j = i + 2
                    rhs = []
                    while j < len(tokens):
                        tj = tokens[j]['type']
                        if tj == 0:
                            rhs.append(float_str(tokens[j]['payload']))
                        elif tj == 3:
                            # Another VAR starts a new assignment - stop RHS here
                            break
                        elif tj == 4:
                            sv = tokens[j]['payload']
                            if sv in (123, 125, 41):  # { } )
                                break
                            rhs.append(sym_char(sv))
                        elif tj == 2:
                            break
                        else:
                            break
                        j += 1
                    if rhs:
                        lines.append(' ' * indent + '%s = %s' % (vname, ' '.join(rhs)))
                    i = j
                    continue
                else:
                    lines.append(' ' * indent + vname)
                    i += 1
                    continue

            else:
                i += 1
                continue

        result['programs'].append({
            'index': prog['index'],
            'size': prog['size'],
            'variable_count': prog['variable_count'],
            'entry_points': prog['entry_points'],
            'lines': lines,
        })

    return result


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
