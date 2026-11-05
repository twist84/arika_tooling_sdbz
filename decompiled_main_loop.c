#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define MEM_SIZE 0x100000
static uint8_t mem[MEM_SIZE];

#define READ32(addr) (*(uint32_t*)(mem + ((addr) & (MEM_SIZE - 1))))
#define WRITE32(addr, val) (*(uint32_t*)(mem + ((addr) & (MEM_SIZE - 1))) = (val))

uint32_t v0, v1, a0, a1, a2, s0, s1, s2, s3, s4, sp, ra;

int decompiled_main(void) {
    sp -= 0x30;
    READ32(sp+0x20) = s4;
    s4 = 0x460000;
    READ32(sp+0x18) = s3;
    READ32(sp) = s0;
    READ32(sp+0x8) = s1;
    READ32(sp+0x10) = s2;
    READ32(sp+0x28) = ra;
    v0 = READ32(s4+0x5158);
    s2 = READ32(v0+0x148);
    s3 = a0;
    if (s2 == 0) {
        a0 = READ32(s4+0x5158);
        v0 = READ32(a0+0x3C);
        a0 = s3;
        if (v0 == 0) {
            s3 = READ32(sp+0x18);
            s0 = READ32(sp);
            s1 = READ32(sp+0x8);
            s2 = READ32(sp+0x10);
            s4 = READ32(sp+0x20);
            ra = READ32(sp+0x28);
            sp += 0x30;
            goto label_0x00100218;
        } else {
            call(v0); /* jalr @ 0x0018C598 */
            a0 = s3;
        }
    } else {
        s0 = READ32(s2+0x4);
        s0 -= 1;
        v1 = s2 + 8;
        if (s0 < 0) {
            s2 = READ32(s2);
            s0 = READ32(s2+0x4);
            while (s2 != 0) {
                s0 -= 1;
                if (s0 < 0) continue;
                v1 = s2 + 8;
                v0 = s0 << 2;
                s1 = v0 + v1;
                v0 = READ32(s1);
                while (s0 >= 0) {
                    s1 -= 4;
                    call(v0); /* jalr @ 0x0018C56C */
                    s0 -= 1;
                    v0 = READ32(s1);
                }
                s2 = READ32(s2);
                s0 = READ32(s2+0x4);
            }
        }
    }
    /* --- unreached block 0x0018C5C4 --- */
    {
        sp -= 0x20;
        READ32(sp+0x8) = s1;
        s1 = a0;
        READ32(sp) = s0;
        READ32(sp+0x10) = s2;
        READ32(sp+0x18) = ra;
        if (s1 != 0) {
            v1 = READ32(s1+0x54);
            v0 = READ32(v1+0x38);
            if (v1 != 0) {
                v1 = READ32(s1+0xC);
                if (v0 != 0) {
                    v0 = v1 & 8;
                } else {
                    a0 = v1;
                    sub_0018C8F0();
                    v1 = READ32(s1+0xC);
                }
            } else {
                v0 = 0x460000;
                v1 = READ32(v0+0x5158);
                WRITE32(s1+0x54, v1);
                v0 = READ32(v1+0x38);
            }
        } else {
            v0 = 0x460000;
            a1 = 0x190000;
            a0 = READ32(v0+0x5158);
            a1 -= 0x3A38;
            s0 = READ32(sp);
            s1 = READ32(sp+0x8);
            s2 = READ32(sp+0x10);
            ra = READ32(sp+0x18);
            sp += 0x20;
            goto label_0x0018D348;
        }
    }
    /* --- unreached block 0x0018C60C --- */
    {
    }
    /* --- unreached block 0x0018C648 --- */
    {
        v0 = 0;
        if (v0 == 0) {
            s0 = READ32(sp);
            s1 = READ32(sp+0x8);
            s2 = READ32(sp+0x10);
            ra = READ32(sp+0x18);
        } else {
            s2 = READ32(s1+0x10);
            a0 = 0;
            if (s2 == 0) {
                ;
            } else {
                v0 = READ32(s1);
                v1 = v1 & 3;
            }
        }
    }
    /* --- unreached block 0x0018C664 --- */
    {
        WRITE32(s1, s2);
        s0 = v0 - s2;
        if (v1 != 0) {
            WRITE32(s1+0x8, a0);
            if (s0 <= 0) {
                v0 = 0;
            } else {
                v0 = READ32(s1+0x24);
                a2 = s0;
                a0 = READ32(s1+0x1C);
                a1 = s2;
                call(v0); /* jalr @ 0x0018C6A4 */
                v1 = v0;
                s0 -= v1;
                if (v1 <= 0) {
                    v1 = READ32(s1+0xC);
                    v0 = -1;
                    v1 = v1 | 0x40;
                } else {
                    s2 += v1;
                    if (s0 > 0) {
                        ;
                    }
                }
            }
        } else {
            a0 = READ32(s1+0x14);
            if (0 == 0) {
                ;
            }
        }
    }
    /* --- unreached block 0x0018C684 --- */
    {
        READ32(s1+0xC) = v1;
        if (0 == 0) {
            ;
        } else {
        }
    }
  return 0;
}
