"""Software-only compositing fallback for the native SDBZ menu preview.

The EE's draw *submission order* is recovered from 0x379E60 and
0x378170, but the GS Z-buffer compare/blend rules are not yet fully
decoded. Qt's basic source-over rendering ignores per-sprite depth.
In particular, small sprite 2 (Z=5, x=0..320, y=0..152) is submitted
after the banner (Z=99, x=0..264, y=16..64) and would hide its title.
The provided PCSX2 capture confirms that the title remains visible.

For a 2-D diagnostic preview, use a stable painter order by recovered
depth. Keep the original command queue untouched so equal-depth draws
retain native submission order. This is NOT a GS Z-buffer emulator:
transparent geometry and alpha-test interactions may still differ.
"""


def software_painter_order(commands):
    """Return painter commands back-to-front without changing submission.

    Recovery uses small-to-large depth as the software compositing
    approximation. Python's sort is stable, so equal-depth commands
    preserve the native order (including pending-before-current).
    """
    return sorted(commands, key=lambda command: command['depth'])
