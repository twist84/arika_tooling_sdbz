"""Native menu RNG algorithm; callers supply the 64-bit context state explicitly."""
import ctypes
import arika_backend as backend

MULTIPLIER=0x5851F42D4C957F2D
MASK64=0xffffffffffffffff


def next_rng(state):
    if not isinstance(state,int) or not 0<=state<=MASK64:raise ValueError('RNG state must be an unsigned 64-bit integer')
    value = ctypes.c_uint(0)
    next_state = backend._lib.arika_next_rng(state, ctypes.byref(value))
    return next_state, value.value


class c_native_rng:
    def __init__(self,state):
        next_rng(state);self.m_state=state

    def next(self):
        self.m_state,result=next_rng(self.m_state)
        return result

    def get_state(self):
        return self.m_state


def recover_rng_kernel(elf):
    return dict(address=0x190450,words=elf.words(0x190450,(0x1904b4-0x190450)//4),
        multiply_address=0x195e08,multiply_words=elf.words(0x195e08,(0x195e7c-0x195e08)//4),
        multiplier=MULTIPLIER,increment=1,state_bits=64,output_bits=31,
        context_pointer_address=0x462c50,state_offset=0xa8,
        limits='Algorithm is recovered; context state and calls by other game systems are runtime inputs, not inferred.')
