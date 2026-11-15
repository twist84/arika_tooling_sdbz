"""Native EU-beta sine/cosine *dispatch*; intentionally not a PS2 libm port.

0x1859D8 (cos) and 0x185C78 (sin) compare the absolute float32
argument bits with 0x3F490FD8, invoke 0x182900 for arguments above
that threshold, then dispatch to kernel 0x183DE0 (cos) or 0x184798
(sin) by the returned quadrant & 3. The reducer and polynomial
kernels are NOT implemented here. Their inputs/outputs must come
from a captured call or future instruction-backed implementations.

Keep this pure, bit-oriented model separate from the Qt preview's
math.sin/math.cos approximations until those dependencies are recovered.
"""
import struct


NATIVE_COSINE = 0x001859D8
NATIVE_SINE = 0x00185C78
NATIVE_REDUCER = 0x00182900
NATIVE_COS_KERNEL = 0x00183DE0
NATIVE_SIN_KERNEL = 0x00184798
SMALL_ANGLE_ABS_BITS = 0x3F490FD8


def _u32(value):
    if not isinstance(value, int) or not 0 <= value <= 0xffffffff:
        raise ValueError('expected raw float32 bit pattern (u32)')
    return value


def float_bits(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def float_value(value):
    return struct.unpack('<f', struct.pack('<I', _u32(value)))[0]


def trig_dispatch(function, angle_bits, reduced_quadrant=None):
    """Describe exactly which leaf 0x1859D8/0x185C78 invokes.

    A reduced quadrant must be supplied *only* for a large argument,
    and it must come from 0x182900. There is no host-math fallback.
    Result contains the leaf function address, whether NEG.S follows,
    and the native $a0 selector for the sine kernel. Remainder float
    words [sp+0,sp+4] are intentionally absent from this metadata.
    """
    _u32(angle_bits)
    if function not in (NATIVE_COSINE, NATIVE_SINE):
        raise ValueError('unknown native trig wrapper')
    abs_bits = angle_bits & 0x7fffffff
    if abs_bits <= SMALL_ANGLE_ABS_BITS:
        if reduced_quadrant is not None:
            raise ValueError('small arguments bypass 0x182900')
        return dict(reducer=None,
                    quadrant=None,
                    kernel=(NATIVE_COS_KERNEL if function == NATIVE_COSINE
                            else NATIVE_SIN_KERNEL),
                    negated=False,
                    sine_mode=(0 if function == NATIVE_SINE else None),
                    input_source='original',
                    input_high_bits=angle_bits,
                    input_low_bits=0)

    if not isinstance(reduced_quadrant, int):
        raise ValueError('large angle requires captured reducer quadrant')
    q = reduced_quadrant & 3
    if function == NATIVE_COSINE:
        # q0 +cos, q1 -sin, q2 -cos, q3 +sin
        kernel = (NATIVE_COS_KERNEL if (q & 1) == 0
                  else NATIVE_SIN_KERNEL)
        negate = q in (1, 2)
    else:
        # q0 +sin, q1 +cos, q2 -sin, q3 -cos
        kernel = (NATIVE_SIN_KERNEL if (q & 1) == 0
                  else NATIVE_COS_KERNEL)
        negate = q in (2, 3)
    return dict(reducer=NATIVE_REDUCER,
                quadrant=q,
                kernel=kernel,
                negated=negate,
                sine_mode=(1 if kernel == NATIVE_SIN_KERNEL else None),
                input_source='reducer_sp_0_and_4',
                input_high_bits=None,
                input_low_bits=None)


def apply_native_neg_s(kernel_result_bits, dispatch):
    """Apply the wrapper's NEG.S as a sign-bit flip, preserving -0.0.

    The caller supplies a real native leaf-result word. This function
    never evaluates a sine/cosine polynomial.
    """
    _u32(kernel_result_bits)
    if not isinstance(dispatch, dict) or not isinstance(
            dispatch.get('negated'), bool):
        raise ValueError('invalid native dispatch metadata')
    return kernel_result_bits ^ (0x80000000 if dispatch['negated'] else 0)
