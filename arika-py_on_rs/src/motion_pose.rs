//! Sample all MOT2 translation/rotation/scale tracks for a frame in one call.
//! Track order is T, R, S per bone. Each track descriptor is [key_start,
//! key_count] into shared f64 time and vec4 arrays; output is packed TRS10.

const MAX_TRACKS: usize = 300_000;
const MAX_KEYS: usize = 5_000_000;

fn sample_track(
    times: &[f64],
    values: &[f64],
    start: usize,
    count: usize,
    time: f64,
    rotation: bool,
) -> Option<[f64; 4]> {
    if count == 0 { return None; }
    let end = start.checked_add(count)?;
    if end > times.len() || end.checked_mul(4)? > values.len() {
        return None;
    }
    let keys = &times[start..end];
    if keys.iter().any(|v| !v.is_finite()) ||
       keys.windows(2).any(|pair| pair[0] >= pair[1]) {
        return None;
    }
    let key_at = |i: usize| -> [f64; 4] {
        let offset = (start + i) * 4;
        [
            values[offset], values[offset + 1],
            values[offset + 2], values[offset + 3],
        ]
    };
    let (left, right, factor) = if time <= keys[0] {
        (0, 0, 0.0)
    } else if time >= keys[count - 1] {
        (count - 1, count - 1, 0.0)
    } else {
        let upper = keys.partition_point(|&key| key <= time);
        let lower = upper - 1;
        let factor = (time - keys[lower]) / (keys[upper] - keys[lower]);
        (lower, upper, factor)
    };
    let a = key_at(left);
    let b = key_at(right);
    let mut result = [0.0; 4];
    if rotation {
        // Shortest-arc SLERP, using normalized lerp for very close keys.
        let normalize = |q: &mut [f64; 4]| -> Option<()> {
            let norm = q.iter().map(|v| v * v).sum::<f64>().sqrt();
            if !norm.is_finite() || norm <= 1e-12 { return None; }
            for v in q { *v /= norm; }
            Some(())
        };
        let mut a = a;
        let mut b = b;
        normalize(&mut a)?;
        normalize(&mut b)?;
        let dot = a.iter().zip(b.iter()).map(|(x, y)| x * y).sum::<f64>();
        let mut dot = dot.clamp(-1.0, 1.0);
        if dot < 0.0 {
            for v in &mut b { *v = -*v; }
            dot = -dot;
        }
        let (wa, wb) = if left == right {
            (1.0, 0.0)
        } else if dot > 0.9995 {
            (1.0 - factor, factor)
        } else {
            let theta = dot.acos();
            let sin_theta = theta.sin();
            (
                ((1.0 - factor) * theta).sin() / sin_theta,
                (factor * theta).sin() / sin_theta,
            )
        };
        for i in 0..4 { result[i] = a[i] * wa + b[i] * wb; }
        normalize(&mut result)?;
    } else {
        for i in 0..4 { result[i] = a[i] * (1.0 - factor) + b[i] * factor; }
    }
    result.iter().all(|v| v.is_finite()).then_some(result)
}

/// Return 0 on success, -1 for invalid input. No partial output on failure.
#[no_mangle]
pub extern "C" fn arika_motion_sample_pose(
    descriptors: *const u32, track_count: usize,
    key_times: *const f64, key_values: *const f64, key_count: usize,
    time: f64, output: *mut f64,
) -> i32 {
    if track_count == 0 { return 0; }
    if track_count > MAX_TRACKS || track_count % 3 != 0 ||
       key_count > MAX_KEYS || key_count == 0 ||
       descriptors.is_null() || key_times.is_null() ||
       key_values.is_null() || output.is_null() || !time.is_finite() {
        return -1;
    }
    let Some(desc_len) = track_count.checked_mul(2) else { return -1 };
    let Some(value_len) = key_count.checked_mul(4) else { return -1 };
    let descriptors = unsafe { std::slice::from_raw_parts(descriptors, desc_len) };
    let times = unsafe { std::slice::from_raw_parts(key_times, key_count) };
    let values = unsafe { std::slice::from_raw_parts(key_values, value_len) };
    if values.iter().any(|v| !v.is_finite()) {
        return -1;
    }
    let mut poses = Vec::with_capacity(track_count / 3 * 10);
    for index in 0..track_count {
        let start = descriptors[index * 2] as usize;
        let count = descriptors[index * 2 + 1] as usize;
        let Some(value) = sample_track(times, values, start, count, time, index % 3 == 1)
        else { return -1 };
        match index % 3 {
            0 | 2 => poses.extend_from_slice(&value[..3]),
            1 => poses.extend_from_slice(&value),
            _ => unreachable!(),
        }
    }
    debug_assert_eq!(poses.len(), track_count / 3 * 10);
    unsafe { std::ptr::copy_nonoverlapping(poses.as_ptr(), output, poses.len()) };
    0
}

#[cfg(test)]
mod tests {
    use super::*;

    fn run(desc: &[u32], times: &[f64], values: &[[f64; 4]], time: f64) -> Option<[f64; 10]> {
        let flat = values.iter().flatten().copied().collect::<Vec<_>>();
        let mut out = [42.0; 10];
        let status = arika_motion_sample_pose(
            desc.as_ptr(), 3, times.as_ptr(), flat.as_ptr(), times.len(),
            time, out.as_mut_ptr()
        );
        if status == 0 { Some(out) } else {
            assert!(out.iter().all(|&v| v == 42.0));
            None
        }
    }

    #[test]
    fn interpolates_and_clamps_translation_scale() {
        let desc = [0, 2, 2, 1, 3, 2];
        let times = [0.0, 2.0, 0.0, 0.0, 2.0];
        let values = [
            [0.0, 0.0, 0.0, 0.0], [4.0, 6.0, 8.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
            [1.0, 1.0, 1.0, 0.0], [3.0, 5.0, 7.0, 0.0],
        ];
        let pose = run(&desc, &times, &values, 1.0).unwrap();
        assert_eq!(&pose[..3], &[2.0, 3.0, 4.0]);
        assert_eq!(&pose[7..], &[2.0, 3.0, 4.0]);
        assert_eq!(&run(&desc, &times, &values, -3.0).unwrap()[..3], &[0.0, 0.0, 0.0]);
        assert_eq!(&run(&desc, &times, &values, 4.0).unwrap()[..3], &[4.0, 6.0, 8.0]);
    }

    #[test]
    fn samples_quaternion_shortest_path() {
        let desc = [0, 1, 1, 2, 3, 1];
        let times = [0.0, 0.0, 2.0, 0.0];
        let s = std::f64::consts::FRAC_1_SQRT_2;
        let values = [
            [0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 1.0], [0.0, 0.0, -s, -s],
            [1.0, 1.0, 1.0, 0.0],
        ];
        let pose = run(&desc, &times, &values, 1.0).unwrap();
        let expected = (std::f64::consts::PI / 8.0).sin();
        assert!((pose[5] - expected).abs() < 1e-12);
        assert!((pose[6] - (std::f64::consts::PI / 8.0).cos()).abs() < 1e-12);
    }

    #[test]
    fn rejects_unsorted_keys_without_partial_output() {
        let desc = [0, 2, 2, 1, 3, 1];
        let times = [1.0, 1.0, 0.0, 0.0];
        let values = [[0.0,0.0,0.0,1.0];4];
        assert!(run(&desc, &times, &values, 0.5).is_none());
    }
}
