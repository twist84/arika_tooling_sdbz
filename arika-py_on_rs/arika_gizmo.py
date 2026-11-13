"""Geometry and transform math for Blender-style scene gizmos."""
import math


def _add(a, b):
    return tuple(a[i] + b[i] for i in range(3))


def _sub(a, b):
    return tuple(a[i] - b[i] for i in range(3))


def _mul(v, scalar):
    return tuple(x * scalar for x in v)


def _dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _length(v):
    return math.sqrt(_dot(v, v))


def _normalize(v):
    length = _length(v)
    if length <= 1e-12:
        raise ValueError('gizmo axes must be nonzero')
    return _mul(v, 1.0 / length)


def _square(center, u, v, half):
    u = _mul(_normalize(u), half)
    v = _mul(_normalize(v), half)
    corners = (_add(_add(center, u), v), _add(_sub(center, u), v),
               _sub(_sub(center, u), v), _add(_sub(center, v), u))
    return [(corners[i], corners[(i + 1) % 4]) for i in range(4)]


def _ring(origin, u, v, radius, segments):
    result = []
    previous = None
    for i in range(segments + 1):
        angle = (2.0 * math.pi * i) / segments
        point = _add(origin, _add(_mul(u, radius * math.cos(angle)),
                                  _mul(v, radius * math.sin(angle))))
        if previous is not None:
            result.append((previous, point))
        previous = point
    return result


def _euler_to_quaternion(euler_radians):
    x, y, z = [float(v) * 0.5 for v in euler_radians]
    sx, sy, sz = math.sin(x), math.sin(y), math.sin(z)
    cx, cy, cz = math.cos(x), math.cos(y), math.cos(z)
    return [sx * cy * cz - cx * sy * sz,
            cx * sy * cz + sx * cy * sz,
            cx * cy * sz - sx * sy * cz,
            cx * cy * cz + sx * sy * sz]


def _quaternion_to_euler(q):
    x, y, z, w = q
    length = math.sqrt(x*x + y*y + z*z + w*w)
    if length <= 1e-12:
        raise ValueError('invalid rotation quaternion')
    x, y, z, w = x/length, y/length, z/length, w/length
    sin_pitch = max(-1.0, min(1.0, 2.0 * (w*y - z*x)))
    pitch = math.asin(sin_pitch)

    # At +/-90 degrees of pitch, Euler roll and yaw are not independently
    # defined. Choose yaw=0 for a stable canonical representation rather than
    # letting floating-point noise produce (pi, pi/2, pi) for a pure Y rotation.
    if abs(sin_pitch) >= 1.0 - 1e-10:
        roll = math.atan2(2.0 * (w*x - y*z), 1.0 - 2.0 * (x*x + z*z))
        yaw = 0.0
    else:
        roll = math.atan2(2.0 * (w*x + y*z), 1.0 - 2.0 * (x*x + y*y))
        yaw = math.atan2(2.0 * (w*z + x*y), 1.0 - 2.0 * (y*y + z*z))
    return (roll, pitch, yaw)


def _multiply_quaternions(a, b):
    # Native precision-preserving composition, shared by local/world rotation.
    from arika_backend import quaternion_multiply
    return quaternion_multiply(a, b)


def quaternion_multiply(a, b):
    """Public quaternion product using glTF's [x, y, z, w] layout."""
    return _multiply_quaternions(a, b)


def quaternion_inverse(q):
    length = sum(float(v) * float(v) for v in q)
    if length <= 1e-12:
        raise ValueError('invalid rotation quaternion')
    return [-float(q[0]) / length, -float(q[1]) / length,
            -float(q[2]) / length, float(q[3]) / length]


def quaternion_to_euler(q):
    return _quaternion_to_euler(q)


def quaternion_from_axis_angle(axis, angle):
    axis = _normalize(tuple(float(v) for v in axis))
    half = float(angle) * 0.5
    sine = math.sin(half)
    return [axis[0] * sine, axis[1] * sine, axis[2] * sine, math.cos(half)]


def quaternion_from_matrix(matrix):
    """Extract a quaternion from a 3x3 rotation matrix."""
    m00, m01, m02 = [float(v) for v in matrix[0][:3]]
    m10, m11, m12 = [float(v) for v in matrix[1][:3]]
    m20, m21, m22 = [float(v) for v in matrix[2][:3]]
    trace = m00 + m11 + m22
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        q = [(m21 - m12) / s, (m02 - m20) / s,
             (m10 - m01) / s, 0.25 * s]
    elif m00 > m11 and m00 > m22:
        s = math.sqrt(max(0.0, 1.0 + m00 - m11 - m22)) * 2.0
        q = [0.25 * s, (m01 + m10) / max(s, 1e-12),
             (m02 + m20) / max(s, 1e-12), (m21 - m12) / max(s, 1e-12)]
    elif m11 > m22:
        s = math.sqrt(max(0.0, 1.0 + m11 - m00 - m22)) * 2.0
        q = [(m01 + m10) / max(s, 1e-12), 0.25 * s,
             (m12 + m21) / max(s, 1e-12), (m02 - m20) / max(s, 1e-12)]
    else:
        s = math.sqrt(max(0.0, 1.0 + m22 - m00 - m11)) * 2.0
        q = [(m02 + m20) / max(s, 1e-12), (m12 + m21) / max(s, 1e-12),
             0.25 * s, (m10 - m01) / max(s, 1e-12)]
    length = math.sqrt(sum(v * v for v in q))
    if length <= 1e-12:
        raise ValueError('invalid rotation matrix')
    return [v / length for v in q]


def rotate_euler_local_axis(euler_radians, axis_index, angle):
    """Compose a rotation around the object's local X/Y/Z axis."""
    if axis_index not in (0, 1, 2):
        raise ValueError('axis index must be 0, 1, or 2')
    if len(euler_radians) != 3:
        raise ValueError('expected three Euler angles')
    q = _euler_to_quaternion(euler_radians)
    half = float(angle) * 0.5
    delta = [0.0, 0.0, 0.0, math.cos(half)]
    delta[axis_index] = math.sin(half)
    return _quaternion_to_euler(_multiply_quaternions(q, delta))


def rotate_euler_world_axis(euler_radians, axis, angle):
    """Compose a rotation around an arbitrary world-space axis."""
    if len(euler_radians) != 3 or len(axis) != 3:
        raise ValueError('expected three Euler angles and a 3D axis')
    axis = _normalize(tuple(float(v) for v in axis))
    half = float(angle) * 0.5
    delta = [axis[0] * math.sin(half), axis[1] * math.sin(half),
             axis[2] * math.sin(half), math.cos(half)]
    return _quaternion_to_euler(_multiply_quaternions(delta, _euler_to_quaternion(euler_radians)))


def gizmo_geometry(position, axes, size, mode, segments=48, include_extra=False, view_axes=None):
    """Return world-space line segments grouped by transform handle.

    The legacy default returns only X/Y/Z groups. ``include_extra`` adds the
    Blender-like plane, view-plane, uniform-scale, view-ring and trackball handles.
    Handle keys 0, 1 and 2 correspond to the three axes; other keys are strings.
    """
    if mode == 'transform':
        combined = {}
        for submode in ('move', 'rotate', 'scale'):
            subgeometry = gizmo_geometry(position, axes, size, submode, segments,
                include_extra=include_extra, view_axes=view_axes)
            for handle, lines in subgeometry.items():
                if isinstance(handle, int):
                    name = ('x', 'y', 'z')[handle]
                else:
                    name = handle
                combined[submode + '_' + name] = lines
        return combined
    if mode not in ('move', 'rotate', 'scale'):
        raise ValueError('unknown gizmo mode: %s' % mode)
    if not math.isfinite(size) or size <= 0:
        raise ValueError('gizmo size must be positive and finite')
    if len(axes) != 3:
        raise ValueError('gizmo needs three axes')

    origin = tuple(float(v) for v in position)
    directions = [_normalize(tuple(float(v) for v in axis)) for axis in axes]
    view = [_normalize(tuple(float(v) for v in axis)) for axis in (view_axes or ((1, 0, 0), (0, 1, 0), (0, 0, 1)))]
    result = {0: [], 1: [], 2: []}

    for axis_index, axis in enumerate(directions):
        others = [i for i in range(3) if i != axis_index]
        u, v = directions[others[0]], directions[others[1]]
        lines = result[axis_index]
        endpoint = _add(origin, _mul(axis, size))

        if mode == 'move':
            lines.append((origin, endpoint))
            back = _sub(endpoint, _mul(axis, size * .13))
            side_u = _mul(u, size * .055)
            side_v = _mul(v, size * .055)
            lines.extend(((endpoint, _add(back, side_u)), (endpoint, _sub(back, side_u)),
                          (endpoint, _add(back, side_v)), (endpoint, _sub(back, side_v))))
        elif mode == 'scale':
            lines.append((origin, endpoint))
            lines.extend(_square(endpoint, u, v, size * .065))
        else:
            result[axis_index] = _ring(origin, u, v, size * .82, segments)

    if not include_extra:
        return result

    if mode in ('move', 'scale'):
        for i, j, name in ((0, 1, 'plane_xy'), (0, 2, 'plane_xz'), (1, 2, 'plane_yz')):
            center = _add(origin, _add(_mul(directions[i], size * .25), _mul(directions[j], size * .25)))
            result[name] = _square(center, directions[i], directions[j], size * .105)
        if mode == 'move':
            center = _add(origin, _add(_mul(view[0], size * .15), _mul(view[1], size * .15)))
            result['plane_view'] = _square(center, view[0], view[1], size * .095)
        else:
            center = _add(origin, _add(_mul(view[0], size * .12), _mul(view[1], size * .12)))
            result['uniform'] = _square(center, view[0], view[1], size * .075)
    else:
        result['view'] = _ring(origin, view[0], view[1], size * .98, segments)
        result['trackball'] = _ring(origin, view[0], view[1], size * 1.13, segments)

    return result
