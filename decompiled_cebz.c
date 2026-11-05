#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define MEM_SIZE 0x100000
static uint8_t mem[MEM_SIZE];

#define READ32(addr) (*(uint32_t*)(mem + ((addr) & (MEM_SIZE - 1))))
#define WRITE32(addr, val) (*(uint32_t*)(mem + ((addr) & (MEM_SIZE - 1))) = (val))

uint32_t at, v0, v1, a0, a1, a2, a3, t0, t1, t2, s0, s1, s2, sp, ra;

int decompiled_main(void) {
    sp -= 0x40;
    READ32(sp+0x30) = ra;
    READ32(sp+0x20) = s2;
    READ32(sp+0x10) = s1;
    s2 = a1;
    READ32(sp) = s0;
    s1 = 0;
    s0 = a0;
    v0 = (int8_t)READ32(s0+0x104);
    a0 = s0 + 0x104;
    if (v0 != 0) {
        a1 = 0x2F;
        sub_00191EF8();
        a0 = v0 + 1;
        a1 = s2 + 0x20;
        sub_00191638();
        if (v0 != 0) {
            s1 += 1;
            v0 = (s1 < 0x12) ? 1 : 0;
            s0 += 0x48;
            while (v0 != 0) {
                v0 = (int8_t)READ32(s0+0x104);
                if (v0 != 0) goto block_0x0033022C;
                a0 = s0 + 0x104;
                s1 += 1;
                v0 = (s1 < 0x12) ? 1 : 0;
                s0 += 0x48;
                if (0 == 0) break;
                v0 = 0;
                v1 = READ32(s0+0x144);
                v0 = READ32(s2+0x10);
                if (v1 != v0) continue;
                v0 = 1;
            }
        }
    }
    /* --- unreached block 0x00330258 --- */
    {
        ra = READ32(sp+0x30);
        s2 = READ32(sp+0x20);
        s1 = READ32(sp+0x10);
        s0 = READ32(sp);
        sp += 0x40;
        goto *ra;
    }
    /* --- unreached block 0x00330270 --- */
    {
        t2 = 0;
        a3 = 0;
        at = (a1 < 0) ? 1 : 0;
        t2 += 3;
        a3 += 1;
        a2 = 0;
        if (at == 0) goto 0x00330400;
        at = (a1 < 9) ? 1 : 0;
        v0 = a1 + -8;
        if (at != 0) goto 0x003303C0;
        at = (a1 < 0) ? 1 : 0;
        v1 = 0;
        if (at != 0) {
            if (v1 == 0) goto 0x003303C0;
            v1 = a0;
            t0 = READ32(v1);
            t1 = t0 + 0x3FF;
            t0 = (int32_t)t1 >> 0xA;
            if (t1 >= 0) {
                t2 += t0;
                t0 = READ32(v1+0x4);
                t1 = t0 + 0x3FF;
                t0 = (int32_t)t1 >> 0xA;
                if (t1 >= 0) {
                    t2 += t0;
                } else {
                    t0 = t1 + 0x3FF;
                    t0 = (int32_t)t0 >> 0xA;
                }
            } else {
                t0 = t1 + 0x3FF;
                t0 = (int32_t)t0 >> 0xA;
            }
        } else {
            at = 0x7FFF0000;
            at = at | 0xFFFF;
        }
    }
    /* --- unreached block 0x003302AC --- */
    {
        at = (a1 < at) ? 1 : 0;
        if (at == 0) {
            ;
        } else {
            v1 = a3 & 0xFF;
        }
    }
  return 0;
}
