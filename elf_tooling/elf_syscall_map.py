#!/usr/bin/env python3
"""
ELF tooling: PS2 EE syscall reference mapper.

Scans the ELF code section for `syscall` instructions, traces backward to find
the syscall number (loaded into $v0 via li/ori/addiu/lui, including lui+ori
pairs), and maps known PS2 EE syscall numbers to names. Outputs a compact
grouped summary plus per-site details.

Inspired by IDAPy-PS2's LabelExecutableSyscalls.py but implemented as a
standalone ELF scanner (no IDA required).

Usage:
    python elf_syscall_map.py [elf]

Defaults:
    elf   = source_data/SLUS_214.42
"""
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mips_disasm import decode_instruction, file_to_vaddr


CODE_START = 0x80
CODE_END = 0x400700
TRACE_BACK = 0x80  # bytes to scan back from a syscall for the number


# PS2 EE user-mode syscall numbers -> names (well-known subset)
EE_SYSCALLS = {
    # Thread management
    0x0000: "ExitThread", 0x0001: "ExitDeleteThread",
    0x0003: "DelayThread", 0x0004: "WakeupThread",
    0x0005: "CancelWakeupThread", 0x0006: "IsWakeupThread",
    0x0007: "DisableDispatch", 0x0008: "EnableDispatch",
    0x0009: "InDisableDispatch", 0x000A: "InEnableDispatch",
    0x000B: "CreateThread", 0x000C: "DeleteThread",
    0x000D: "StartThread", 0x000E: "TerminateThread",
    0x000F: "GetThreadId", 0x0010: "ReferThreadStatus",
    # Synchronization
    0x0011: "CreateSema", 0x0012: "DeleteSema",
    0x0013: "SignalSema", 0x0014: "WaitSema", 0x0015: "PollSema",
    0x0016: "ReferSemaStatus",
    0x0017: "CreateMutex", 0x0018: "DeleteMutex",
    0x0019: "LockMutex", 0x001A: "UnlockMutex",
    0x001B: "PollMutex", 0x001C: "ReferMutexStatus",
    0x001D: "CreateEventFlag", 0x001E: "DeleteEventFlag",
    0x001F: "SetEventFlag", 0x0020: "ClearEventFlag",
    0x0021: "WaitEventFlag", 0x0022: "PollEventFlag",
    0x0023: "ReferEventFlagStatus",
    0x0024: "CreateMailbox", 0x0025: "DeleteMailbox",
    0x0026: "SendMailbox", 0x0027: "ReceiveMailbox",
    0x0028: "PollMailbox", 0x0029: "ReferMailboxStatus",
    0x002A: "CreateMsgBuffer", 0x002B: "DeleteMsgBuffer",
    0x002C: "SendMsgBuffer", 0x002D: "ReceiveMsgBuffer",
    0x002E: "PollMsgBuffer", 0x002F: "ReferMsgBufferStatus",
    # Timers
    0x0030: "CreateTimer", 0x0031: "DeleteTimer",
    0x0032: "SetAlarm", 0x0033: "CancelAlarm",
    0x0034: "ReferTimerStatus", 0x0035: "ReferSystemStatus",
    0x0037: "GetSystemTime", 0x0038: "GetSystemTimeLow",
    0x0039: "CheckTimer",
    # File I/O (sceIo)
    0x0060: "sceIoOpen", 0x0061: "sceIoClose",
    0x0062: "sceIoRead", 0x0063: "sceIoWrite",
    0x0064: "sceIoLseek", 0x0065: "sceIoRemove",
    0x0066: "sceIoMkdir", 0x0067: "sceIoRmdir",
    0x0068: "sceIoDopen", 0x0069: "sceIoDclose",
    0x006A: "sceIoDread", 0x006B: "sceIoDevctl",
    # SIF / RPC
    0x0100: "SifExecModule", 0x0101: "SifExecModuleBuffer",
    0x0102: "SifUnloadModule", 0x0103: "SifInitRpc",
    0x0104: "SifSetRpcQueue", 0x0105: "SifRegisterRpc",
    0x0106: "SifCallRpc", 0x0107: "SifSendRpc",
    0x0108: "SifCheckInitRpc", 0x0109: "SifIopReset",
    0x010A: "SifIopReboot", 0x010B: "SifIopSync",
    # Exec / Debug
    0x0400: "ExecPS2",
    0x1000: "printf",
    # Breakpoint / debug traps (observed in this ELF)
    0xFFFE: "DebugBreak", 0xFFFF: "Breakpoint",
}


def file_to_vaddr(file_off):
    return 0x100000 + (file_off - 0x80)


def vaddr_to_file(vaddr):
    return vaddr - 0x100000 + 0x80


def sign16(n):
    return n - 0x10000 if n & 0x8000 else n


def find_syscalls(data, start=CODE_START, end=CODE_END):
    """Yield (file_off, vaddr, word) for each syscall instruction."""
    for i in range(start, end - 4, 4):
        word = struct.unpack_from('<I', data, i)[0]
        op = (word >> 26) & 0x3F
        if op == 0x00:
            funct = word & 0x3F
            if funct == 0x0C:  # syscall
                yield i, file_to_vaddr(i), word


def trace_syscall_number(data, syscall_file_off,
                          trace_back=TRACE_BACK, code_start=CODE_START):
    """
    Trace backward from a syscall to find the syscall number loaded into $v0.
    Returns (number, description) or (None, None) if not determinable.

    Handles:
      * addiu/ori $v0, zero, imm   -> imm
      * lui $v0, upper             -> upper << 16 (may be followed by ori)
      * addiu/ori $v0, $v0, lower  -> completes a previous lui
    """
    start = max(code_start, syscall_file_off - trace_back)

    # Collect all writes to $v0 in the window, in order.
    writes = []  # list of (file_off, kind, value_or_None)
    off = start
    while off < syscall_file_off:
        if off + 4 > len(data):
            break
        word = struct.unpack_from('<I', data, off)[0]
        op = (word >> 26) & 0x3F
        rt = (word >> 16) & 0x1F
        rs = (word >> 21) & 0x1F
        imm = word & 0xFFFF

        if rt == 2:  # writing to $v0
            if op == 0x0D:  # ori $v0, rs, imm
                if rs == 0:
                    writes.append((off, 'ori', imm))
                elif rs == 2:
                    writes.append((off, 'ori_v0', imm))  # complete a lui
                else:
                    writes.append((off, 'ori', None))  # from register
            elif op == 0x09:  # addiu $v0, rs, imm
                if rs == 0:
                    writes.append((off, 'addiu', imm & 0xFFFF))
                elif rs == 2:
                    writes.append((off, 'addiu_v0', imm & 0xFFFF))
                else:
                    writes.append((off, 'addiu', None))  # from register
            elif op == 0x0F:  # lui $v0, upper
                writes.append((off, 'lui', imm << 16))
        off += 4

    if not writes:
        return None, 'no $v0 write in window'

    # The last write to $v0 before the syscall determines the number.
    last = writes[-1]
    off, kind, value = last

    if kind == 'lui':
        # Look for a following ori/addiu $v0, $v0, lower within the window
        for off2, kind2, val2 in writes:
            if off2 > off and kind2 in ('ori_v0', 'addiu_v0') and val2 is not None:
                value = (value & 0xFFFF0000) | (val2 & 0xFFFF)
                break
        if value is None:
            return value, f'lui $v0,0x{value >> 16:04X}(incomplete)'
        return value, f'lui $v0,0x{value >> 16:04X} + ori 0x{value & 0xFFFF:04X}'

    if value is not None:
        return value, f'{kind} $v0,0x{value:04X}'
    return None, f'{kind} $v0,<register>'


def main():
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(elf_path).read_bytes()

    syscalls = list(find_syscalls(data))
    # Group by syscall number
    by_number = defaultdict(list)
    unidentified = []
    for file_off, vaddr, word in syscalls:
        number, desc = trace_syscall_number(data, file_off)
        if number is None:
            unidentified.append((vaddr, file_off, desc))
        else:
            by_number[number].append((vaddr, file_off, desc))

    print("=" * 72)
    print("PS2 EE SYSCALL REFERENCE MAP")
    print("=" * 72)
    print(f"ELF: {elf_path}")
    print(f"Total syscall instructions found: {len(syscalls)}")
    print(f"Identified by number: {sum(len(v) for v in by_number.values())}")
    print(f"Unidentified (register-based): {len(unidentified)}")
    print()

    print("--- Syscalls by number (count / name / sites) ---")
    if by_number:
        for number in sorted(by_number.keys()):
            sites = by_number[number]
            name = EE_SYSCALLS.get(number, f"syscall 0x{number:04X}")
            print(f"  0x{number:06X} ({name:<20}) x{len(sites)}")
            for vaddr, file_off, desc in sites[:5]:
                print(f"      0x{vaddr:08X} (file 0x{file_off:06X}): {desc}")
            if len(sites) > 5:
                print(f"      ... and {len(sites) - 5} more")
    else:
        print("  (none)")
    print()

    if unidentified:
        print(f"--- Unidentified ({len(unidentified)}) ---")
        print("  (syscall number comes from a register; typical of dispatch tables)")
        sample = unidentified[:10]
        for vaddr, file_off, desc in sample:
            print(f"  0x{vaddr:08X} (file 0x{file_off:06X}): {desc}")
        if len(unidentified) > 10:
            print(f"  ... and {len(unidentified) - 10} more")
    print()


if __name__ == '__main__':
    main()
