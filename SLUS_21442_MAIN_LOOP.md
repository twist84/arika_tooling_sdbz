# SLUS_214.42 - Main Loop Map

## Overview

This document maps the complete main loop of Super Dragon Ball Z (SLUS_214.42), showing the per-frame execution flow from entry point through VBlank wait, object updates, input processing, and rendering.

---

## 1. Top-Level Execution Flow

```
POWER ON
    ↓
PS2 Kernel loads ELF via sceExec
    ↓
Entry Point @ 0x00100008 (file 0x000088)
├─ MMI code (op 0x1C) - not standard MIPS
├─ FPU init: zero $f0-$f31 via mtc1, set FCR31=0
├─ Clear BSS: 0x00500680→0x00640380, then 0x00640380→0x00644380
├─ Set gp = 0x00503070 (runtime BSS, NOT in ELF file)
├─ Syscall 60 → stack pointer
├─ Syscall 61 → unknown
└─ JAL chain: 0x0017F018 → 0x00174F20 → 0x00422630 → J 0x0018C518
    ↓
MAIN LOOP @ 0x0018C518
    │
    ├─ Part A: Object Update Loop (0x0018C518-0x0018C5BC)
    ├─ Part B: VBlank Wait (0x0018C588-0x0018C59C)
    ├─ Part C: Epilogue → 0x00100218 → 0x0017F418 → VBlank Syscall
    │
    ├─ Part D: Input Processing (0x0018C5C8-0x0018C6D4)
    ├─ Part E: Render Loop (0x0018D348+)
    │
    └─ Back to top (frame repeats)
```

---

## 2. Main Loop - Part A: Object Update Loop (0x0018C518-0x0018C5BC)

### Function Prologue (0x0018C518-0x0018C534)

```
0x0018C518: ADDIU $sp, $sp, -48       # Allocate 48 bytes on stack
0x0018C51C: SD   $s4, 0x20($sp)       # Save callee-saved registers
0x0018C520: SD   $s3, 0x18($sp)
0x0018C524: SD   $s0, 0x00($sp)
0x0018C528: SD   $s1, 0x08($sp)
0x0018C52C: SD   $s2, 0x10($sp)
0x0018C530: SD   $ra, 0x28($sp)       # Save return address
0x0018C534: LUI  $s4, 0x0046          # $s4 = gp base (0x00460000)
```

### Object List Iteration (0x0018C538-0x0018C584)

The main loop iterates through a linked list of game objects, calling each object's update method via indirect JALR:

```
0x0018C538: LW   $v0, 0x5158($s4)     # Load object list head from gp+0x5158
0x0018C53C: LW   $s2, 0x0148($v0)     # Load first object node (+0x0148 offset)
0x0018C540: BEQ  $s2, $zero, 0x0018C588 # If null, skip to VBlank check

--- Object Loop (0x0018C548-0x0018C580) ---
0x0018C548: LW   $s0, 0x0004($s2)     # Load object's update function pointer (+0x04)
0x0018C54C: SLL  $zero, $zero, 0      # NOP (delay slot)
0x0018C550: ADDIU $s0, $s0, -1        # Decrement function pointer (check for null)
0x0018C554: unk_op_0x01               # (EE-specific instruction)
0x0018C558: ADDIU $v1, $s2, 8         # Calculate next node offset (+8)
0x0018C55C: R-type funct=0x00          # (likely NOP or related)
0x0018C560: ADDU $s1, $v0, $v1        # Calculate absolute function address
0x0018C564: LW   $v0, 0x0000($s1)     # Load function pointer from node+0
0x0018C568: ADDIU $s1, $s1, -4        # Adjust pointer back
0x0018C56C: JALR $ra, $v0             # *** CALL object update method (INDIRECT) ***
0x0018C570: ADDIU $s0, $s0, -1        # Delay slot
0x0018C574: unk_op_0x01               # (EE-specific instruction)
0x0018C578: LW   $v0, 0x0000($s1)     # Load next function pointer
0x0018C57C: LW   $s2, 0x0000($s2)     # Load next node pointer from node+0
0x0018C580: BNEL $s2, $zero, 0x0018C550 # Loop if more nodes

0x0018C584: LW   $s0, 0x0004($s2)     # Load last object's update pointer
```

### Object Node Structure

Each object in the linked list appears to have this layout:
```
Object Node:
  +0x00: function pointer (update method) - called via JALR
  +0x04: next node pointer (0 = end of list)
  +0x08+: object-specific data
```

The object list head is at `gp+0x5158` (vaddr 0x00465158, file 0x3651D8), which points to the first node at `0x00464E68`.

---

## 3. Main Loop - Part B: VBlank Check (0x0018C588-0x0018C59C)

```
0x0018C588: LW   $a0, 0x5158($s4)     # Load gp+0x5158 again (object list head base)
0x0018C58C: LW   $v0, 0x003C($a0)     # Load VBlank flag at offset 0x3C
0x0018C590: BEQL $v0, $zero, 0x0018C5A4 # If zero, skip VBlank handler
0x0018C594: R-type funct=0x2D          # NOP (delay slot)
0x0018C598: JALR $ra, $v0             # *** CALL VBlank handler (INDIRECT) ***
0x0018C59C: SLL  $zero, $zero, 0      # NOP (delay slot)
```

The VBlank flag at `gp+0x5158+0x3C` is checked each frame. If set, the VBlank handler is called indirectly.

---

## 4. Main Loop - Part C: Epilogue → VBlank Syscall (0x0018C5A4-0x0018C5BC)

```
0x0018C5A4: LD   $s3, 0x18($sp)       # Restore callee-saved registers
0x0018C5A8: LD   $s0, 0x00($sp)
0x0018C5AC: LD   $s1, 0x08($sp)
0x0018C5B0: LD   $s2, 0x10($sp)
0x0018C5B4: LD   $s4, 0x20($sp)
0x0018C5B8: LD   $ra, 0x28($sp)
0x0018C5BC: J    0x00100218           # Jump to kernel/syscall return
0x0018C5C0: ADDIU $sp, $sp, 48        # Delay slot - restore stack
```

### 0x00100218 - Kernel Return Stub (0x00100218-0x00100230)

```
0x00100218: J    0x0017F418           # Jump to VBlank wait function
0x0010021C: R-type funct=0x00          # NOP (delay slot)
0x00100220: ADDIU $v1, $zero, 0x23     # Syscall number 0x23 (35)
0x00100224: SYSCALL                    # Invoke kernel syscall
0x00100228: R-type funct=0x00          # NOP (delay slot)
0x0010022C: R-type funct=0x00          # NOP (delay slot)
0x00100230: LW   $v0, 0x0000($v0)      # Load syscall result
```

### 0x0017F418 - VBlank Wait Wrapper (0x0017F418-0x0017F434)

```
0x0017F418: ADDIU $sp, $sp, -32        # Stack frame
0x0017F41C: SD   $ra, 0x10($sp)        # Save return address
0x0017F420: SD   $s0, 0x00($sp)
0x0017F424: JAL  0x0017F358            # Call VBlank syscall function
0x0017F428: ADDU $s0, $s0, $zero       # Delay slot
0x0017F42C: ADDU $s0, $zero, $s0       # 
0x0017F430: LD   $ra, 0x10($sp)        # Restore
0x0017F434: LD   $s0, 0x00($sp)
0x0017F438: JR   $ra                   # Return to main loop
```

### 0x0017F358 - VBlank Syscall Function (0x0017F358-0x0017F37C)

```
0x0017F358: J    0x0017E7B8            # Jump to kernel VBlank wait
0x0017F35C: R-type funct=0x00          # NOP (delay slot)
0x0017F360: ADDIU $sp, $sp, -64        # Stack frame
...
```

The chain is: Main Loop → 0x00100218 → 0x0017F418 → 0x0017F358 → 0x0017E7B8 (kernel VBlank wait)

---

## 5. Main Loop - Part D: Input Processing (0x0018C5C8-0x0018C6D4)

This second function handles controller input and timing:

```
0x0018C5C8: ADDIU $sp, $sp, -32        # Stack frame
0x0018C5CC: SD   $s1, 0x08($sp)
0x0018C5D0: SD   $s0, 0x00($sp)
0x0018C5D4: SD   $s2, 0x10($sp)
0x0018C5D8: BNE  $s1, $zero, 0x0018C610 # If s1 != 0, skip to input handling
0x0018C5DC: SD   $ra, 0x18($sp)
0x0018C5E0: LUI  $v0, 0x0046           # gp base
0x0018C5E4: LUI  $a1, 0x0019
0x0018C5E8: LW   $a0, 0x5158($v0)      # Load gp+0x5158
0x0018C5EC: ADDIU $a1, $a1, 0xC5C8     # a1 = gp+0xC5C8
0x0018C5F0: LD   $s0, 0x00($sp)        # Restore
0x0018C5F4: LD   $s1, 0x08($sp)
0x0018C5F8: LD   $s2, 0x10($sp)
0x0018C5FC: LD   $ra, 0x18($sp)
0x0018C600: J    0x0018D348            # Jump to render function
0x0018C604: ADDIU $sp, $sp, 32         # Delay slot
```

### Input Processing Path (0x0018C610-0x0018C6D4)

```
0x0018C610: LW   $v1, 0x0054($s1)      # Load controller data (+0x54)
0x0018C614: BNEL $v1, $zero, 0x0018C630 # If controller data != 0, skip setup
0x0018C618: LW   $v0, 0x0038($v1)      # Load from +0x38
0x0018C61C: LUI  $v0, 0x0046           # gp base
0x0018C620: LW   $v1, 0x5158($v0)      # Load gp+0x5158
0x0018C624: SW   $v1, 0x0054($s1)      # Store back at controller offset
0x0018C628: LW   $v0, 0x0038($v1)      # Load from +0x38
0x0018C62C: SLL  $zero, $zero, 0       # NOP (delay slot)

0x0018C630: BNEL $v0, $zero, 0x0018C644 # If v0 != 0, skip timer logic
0x0018C634: unk_op_0x21                # (EE-specific instruction)
0x0018C638: JAL  0x0018C8F0            # CALL VBlank flag setter
0x0018C63C: R-type funct=0x2D           # Delay slot
0x0018C640: unk_op_0x21                # (EE-specific instruction)
0x0018C644: ANDI $v0, $v1, 0x0008      # Check button bit 3 (0x08)
0x0018C648: BEQ  $v0, $zero, 0x0018C6C4 # If not set, skip
0x0018C64C: R-type funct=0x2D           # NOP (delay slot)
0x0018C650: LW   $s2, 0x0010($s1)      # Load timer value (+0x10)
0x0018C654: BEQ  $s2, $zero, 0x0018C6C4 # If timer expired, skip
0x0018C658: R-type funct=0x2D           # NOP (delay slot)
0x0018C65C: LW   $v0, 0x0000($s1)      # Load current time
0x0018C660: ANDI $v1, $v1, 0x0003      # Mask to 2 bits (0-3)
0x0018C664: SW   $s2, 0x0000($s1)      # Store timer value
0x0018C668: BNE  $v1, $zero, 0x0018C690 # If timer not expired (0-3), skip
0x0018C66C: SUBU $s0, $v0, $s2         # Calculate delta time
0x0018C670: BEQ  $zero, $zero, 0x0018C690 # Unconditional branch
0x0018C674: LW   $a0, 0x0014($s1)      # Load input data (+0x14)
0x0018C678: unk_op_0x25                # (EE-specific instruction)
0x0018C67C: ADDIU $v0, $zero, -1       # v0 = -1
0x0018C680: ORI  $v1, $v1, 0x0040      # Set bit 6 in timer
0x0018C684: BEQ  $zero, $zero, 0x0018C6C4 # Unconditional branch
0x0018C688: unk_op_0x29                # (EE-specific instruction)
0x0018C68C: SLL  $zero, $zero, 0       # NOP (delay slot)
0x0018C690: BLEZ $s0, 0x0018C6C0       # If delta time <= 0, done
0x0018C694: SW   $a0, 0x0008($s1)      # Store input data (+0x08)
0x0018C698: LW   $v0, 0x0024($s1)      # Load input function pointer (+0x24)
0x0018C69C: R-type funct=0x2D           # NOP (delay slot)
0x0018C6A0: LW   $a0, 0x001C($s1)      # Load input argument (+0x1C)
0x0018C6A4: JALR $ra, $v0              # *** CALL input handler (INDIRECT) ***
0x0018C6A8: R-type funct=0x2D           # Delay slot
0x0018C6AC: R-type funct=0x2D           # NOP (delay slot)
0x0018C6B0: BLEZ $v1, 0x0018C678       # Loop if timer still active
0x0018C6B4: SUBU $s0, $s0, $v1         # Decrement timer
0x0018C6B8: BGTZ $s0, 0x0018C698       # Loop if timer > 0
0x0018C6BC: ADDU $s2, $s2, $v1         # Add to accumulator
0x0018C6C0: R-type funct=0x2D           # NOP (delay slot)
0x0018C6C4: LD   $s0, 0x00($sp)        # Restore registers
0x0018C6C8: LD   $s1, 0x08($sp)
0x0018C6CC: LD   $s2, 0x10($sp)
0x0018C6D0: LD   $ra, 0x18($sp)
0x0018C6D4: JR   $ra                   # Return
```

---

## 6. Main Loop - Part E: Render Loop (0x0018D348)

```
0x0018D348: ADDIU $sp, $sp, -48        # Stack frame
0x0018D34C: SD   $s2, 0x10($sp)
0x0018D350: ADDIU $s2, $s2, 0x01D8     # $s2 = gp+0x5158+0x01D8
0x0018D354: SD   $s3, 0x18($sp)
0x0018D358: R-type funct=0x2D           # NOP (delay slot)
0x0018D35C: SD   $s4, 0x20($sp)
0x0018D360: ADDU $s4, $a0, $s0         # Calculate render object address
0x0018D364: SD   $s0, 0x00($sp)
0x0018D368: SD   $s1, 0x08($sp)
0x0018D36C: BEQ  $s2, $zero, 0x0018D3B8 # If null, skip render loop
0x0018D370: SD   $ra, 0x28($sp)

--- Render Loop (0x0018D374-0x0018D3B4) ---
0x0018D374: LW   $s0, 0x0004($s2)     # Load render function pointer (+0x04)
0x0018D378: ADDIU $s1, $s1, -1        # Decrement counter
0x0018D37C: R-type funct=0x0B           # (EE-specific)
0x0018D380: LW   $s1, 0x0008($s1)     # Load next node
0x0018D384: R-type funct=0x00           # NOP (delay slot)
0x0018D388: unk_op_0x21                # (EE-specific instruction)
0x0018D38C: BEQL $v0, $zero, 0x0018D3A4 # If null, skip render call
0x0018D390: ADDIU $s1, $s1, -1        # Decrement counter
0x0018D394: JALR $ra, $s4             # *** CALL object render method (INDIRECT) ***
0x0018D398: R-type funct=0x2D           # Delay slot
0x0018D39C: OR   $s3, $s3, $v0        # Accumulate render result
0x0018D3A0: ADDIU $s1, $s1, -1        # Decrement counter
0x0018D3A4: unk_op_0x01                # (EE-specific instruction)
0x0018D3A8: ADDIU $s1, $s1, 0x58       # Advance by 0x58 (88 bytes)
0x0018D3AC: LW   $s2, 0x0000($s2)     # Load next node pointer
0x0018D3B0: BNEL $s2, $zero, 0x0018D378 # Loop if more nodes

0x0018D3B4: LW   $s0, 0x0004($s2)     # Load last render function
0x0018D3B8: ...                        # Continue render pipeline
```

---

## 7. Complete Main Loop Call Graph

```
MAIN LOOP @ 0x0018C518
    │
    ├─ Object Update (0x0018C538-0x0018C584)
    │   ├─ Iterate linked list at gp+0x5158+0x0148
    │   ├─ Each node: +0x00 = update fn ptr, +0x04 = next ptr
    │   ├─ Call via JALR $ra, $v0 (indirect)
    │   └─ Node stride: 0x04 bytes (linked list)
    │
    ├─ VBlank Check (0x0018C588-0x0018C59C)
    │   ├─ Check flag at gp+0x5158+0x3C
    │   └─ Call VBlank handler via JALR $ra, $v0
    │
    ├─ VBlank Wait (0x0018C5BC → 0x00100218 → 0x0017F418 → 0x0017F358 → 0x0017E7B8)
    │   ├─ Syscall via kernel at 0x0017E7B8
    │   └─ Wait for next VBlank interrupt
    │
    ├─ Input Processing (0x0018C5C8-0x0018C6D4)
    │   ├─ Check controller data at +0x54
    │   ├─ Timer-based input processing (0x0003 bitmask)
    │   ├─ Call input handler via JALR $ra, $v0 (+0x24)
    │   └─ Delta time calculation
    │
    └─ Render Loop (0x0018D348+)
        ├─ Iterate render object list at gp+0x5158+0x01D8
        ├─ Each node: +0x00 = render fn ptr, +0x04 = next ptr
        ├─ Node stride: 0x58 (88 bytes)
        └─ Call via JALR $ra, $s4 (indirect)
```

---

## 8. Key Data Structures

### Object List Head (gp+0x5158)
```
Address: 0x00465158 (file 0x3651D8)
Value:   0x00464E68 (first object node)

Object Node Layout:
  +0x00: update function pointer (called via JALR)
  +0x04: next node pointer (0 = end)
  +0x08+: object-specific data
```

### VBlank Flag (gp+0x5158+0x3C)
```
Address: 0x00465194 (file 0x465194 - 0x100000 + 0x80 = 0x365194)
Used:    Checked each frame, if set calls VBlank handler
Set by:  Function at 0x0018C8F0 (SW $v1, 0x003C($a0))
```

### Controller Input (gp+0x5158+0x54)
```
Address: 0x004651AC
Used:    Controller state, checked each frame
Updated: From gp+0x5158+0x38 when zero
```

### Global State at gp+0x1130+ (set by function at 0x0018C6E0)
```
gp+0x1154: SW zero (clear)
gp+0x1158: SW zero (clear)
gp+0x115C: SW $s2 (store timer)
gp+0x1160: SW $s2 (store timer)
gp+0x1164: SW $v1 (store value)
gp+0x1168: SW $v1 (store value)
gp+0x116C: SW zero (clear)
gp+0x1170: SW zero (clear)
gp+0x1174: SW zero (clear)
gp+0x1178: SW zero (clear)
```

---

## 8. Per-Frame Summary

| Phase | Address Range | Operation |
|-------|--------------|-----------|
| Object Update | 0x0018C538-0x0018C584 | Iterate object list, call update via JALR |
| VBlank Check | 0x0018C588-0x0018C59C | Check flag at gp+0x5158+0x3C, call handler |
| VBlank Wait | 0x0018C5BC-0x0017E7B8 | Syscall to kernel, wait for VBlank |
| Input Process | 0x0018C5C8-0x0018C6D4 | Read controller, timer-based input, call handler |
| Render | 0x0018D348+ | Iterate render list, call render via JALR |

---

## 9. Functions Called from Main Loop

| Address | Type | Description |
|---------|------|-------------|
| JALR $ra, $v0 @ 0x0018C56C | Indirect | Object update method (per-object) |
| JALR $ra, $v0 @ 0x0018C598 | Indirect | VBlank handler |
| JALR $ra, $v0 @ 0x0018C6A4 | Indirect | Input handler |
| JALR $ra, $s4 @ 0x0018D394 | Indirect | Object render method (per-object) |
| JAL 0x0018C8F0 @ 0x0018C638 | Direct | VBlank flag setter |
| JAL 0x0017F358 @ 0x0017F424 | Direct | VBlank syscall wrapper |
| J 0x0017E7B8 @ 0x0017F358 | Direct | Kernel VBlank wait |
| J 0x00100218 @ 0x0018C5BC | Direct | Main loop epilogue → kernel return |
| J 0x0018D348 @ 0x0018C604 | Direct | Jump to render function |
