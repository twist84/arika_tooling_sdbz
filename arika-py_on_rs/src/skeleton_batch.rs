//! Batched model skeleton world transforms. A node is packed as
//! [translation xyz, quaternion xyzw, scale xyz] (10 f64 values).
//! Outputs row-major 4x4 matrices in original node order.

use super::editor_transform::{arika_matrix_local, arika_matrix_multiply};

const MAX_BONES: usize = 100_000;

#[no_mangle]
pub extern "C" fn arika_skeleton_world_matrices(
    parents: *const i32,
    transforms: *const f64,
    count: usize,
    output: *mut f64,
) -> i32 {
    if count == 0 {
        return 0;
    }
    if count > MAX_BONES || parents.is_null() || transforms.is_null() || output.is_null() {
        return -1;
    }
    let Some(transform_len) = count.checked_mul(10) else { return -1 };
    let Some(output_len) = count.checked_mul(16) else { return -1 };
    let parents = unsafe { std::slice::from_raw_parts(parents, count) };
    let transforms = unsafe { std::slice::from_raw_parts(transforms, transform_len) };
    if parents.iter().any(|&p| p < -1 || (p >= 0 && p as usize >= count))
        || transforms.iter().any(|v| !v.is_finite())
    {
        return -1;
    }

    // 0 = unseen, 1 = in current ancestor chain, 2 = complete.
    // Iterative chain traversal avoids Rust stack overflow on deep hierarchies.
    let mut states = vec![0u8; count];
    let mut matrices = vec![[0.0f64; 16]; count];
    let mut pending = Vec::new();
    let mut identity = [0.0f64; 16];
    for i in 0..4 { identity[i * 4 + i] = 1.0; }

    for start in 0..count {
        if states[start] == 2 {
            continue;
        }
        let mut current = start;
        loop {
            if states[current] == 2 {
                break;
            }
            if states[current] == 1 {
                return -1; // cycle
            }
            states[current] = 1;
            pending.push(current);
            let parent = parents[current];
            if parent < 0 {
                break;
            }
            current = parent as usize;
        }

        while let Some(index) = pending.pop() {
            let node = &transforms[index * 10..index * 10 + 10];
            let mut local = [0.0f64; 16];
            if arika_matrix_local(
                node.as_ptr(),
                unsafe { node.as_ptr().add(3) },
                unsafe { node.as_ptr().add(7) },
                local.as_mut_ptr(),
            ) != 0 {
                return -1;
            }
            let parent = parents[index];
            let parent_matrix = if parent < 0 {
                &identity
            } else {
                &matrices[parent as usize]
            };
            let mut world = [0.0f64; 16];
            if arika_matrix_multiply(
                parent_matrix.as_ptr(),
                local.as_ptr(),
                world.as_mut_ptr(),
            ) != 0 {
                return -1;
            }
            matrices[index] = world;
            states[index] = 2;
        }
    }

    // No partial output on failure: commit only after validating every node.
    let output = unsafe { std::slice::from_raw_parts_mut(output, output_len) };
    for (i, matrix) in matrices.iter().enumerate() {
        output[i * 16..(i + 1) * 16].copy_from_slice(matrix);
    }
    0
}

#[cfg(test)]
mod tests {
    use super::*;

    fn node(t: [f64; 3], s: [f64; 3]) -> [f64; 10] {
        [t[0],t[1],t[2],0.0,0.0,0.0,1.0,s[0],s[1],s[2]]
    }

    #[test]
    fn child_before_parent_and_multiple_roots() {
        let parents = [1, -1, -1, 0];
        let transforms = [
            node([1.0, 1.0, 1.0], [1.0; 3]),
            node([3.0, 4.0, 5.0], [2.0; 3]),
            node([-10.0, 0.0, 0.0], [1.0; 3]),
            node([2.0, 0.0, 0.0], [1.0; 3]),
        ].concat();
        let mut result = [0.0f64; 64];
        assert_eq!(arika_skeleton_world_matrices(
            parents.as_ptr(), transforms.as_ptr(), 4, result.as_mut_ptr()
        ), 0);
        assert_eq!([result[3],result[7],result[11]], [5.0,6.0,7.0]);
        assert_eq!([result[32+3],result[32+7],result[32+11]], [-10.0,0.0,0.0]);
        assert_eq!([result[48+3],result[48+7],result[48+11]], [9.0,6.0,7.0]);
    }

    #[test]
    fn reject_cycles_invalid_parents_and_nonfinite_values_without_writing() {
        let transforms = [node([0.0;3],[1.0;3]),node([0.0;3],[1.0;3])].concat();
        let mut result = [23.0f64; 32];
        for parents in [[1,0], [2,-1], [-2,-1]] {
            assert_eq!(arika_skeleton_world_matrices(
                parents.as_ptr(), transforms.as_ptr(), 2, result.as_mut_ptr()
            ), -1);
            assert!(result.iter().all(|v| *v == 23.0));
        }
        let mut bad = transforms.clone();
        bad[4] = f64::NAN;
        let parents = [-1,0];
        assert_eq!(arika_skeleton_world_matrices(
            parents.as_ptr(), bad.as_ptr(), 2, result.as_mut_ptr()
        ), -1);
        assert!(result.iter().all(|v| *v == 23.0));
    }

    #[test]
    fn empty_skeleton_is_allowed() {
        assert_eq!(arika_skeleton_world_matrices(
            std::ptr::null(),std::ptr::null(),0,std::ptr::null_mut()
        ), 0);
    }
}
