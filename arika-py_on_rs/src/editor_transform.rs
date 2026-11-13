//! f64 editor transform primitives. All quaternions use XYZW, all matrices
//! are 4x4 row-major and multiply column vectors (parent * local).

fn checked<const N: usize>(ptr: *const f64) -> Option<[f64; N]> {
    if ptr.is_null() { return None; }
    let values = std::array::from_fn(|i| unsafe { *ptr.add(i) });
    values.iter().all(|v| v.is_finite()).then_some(values)
}
fn output<const N: usize>(out: *mut f64, result: [f64; N]) -> i32 {
    if out.is_null() || !result.iter().all(|v| v.is_finite()) { return -1; }
    unsafe { std::ptr::copy_nonoverlapping(result.as_ptr(), out, N) };
    0
}
fn euler_quat(e: [f64; 3]) -> [f64; 4] {
    let (sx,cx)=(e[0]*0.5).sin_cos();
    let (sy,cy)=(e[1]*0.5).sin_cos();
    let (sz,cz)=(e[2]*0.5).sin_cos();
    [sx*cy*cz-cx*sy*sz, cx*sy*cz+sx*cy*sz,
     cx*cy*sz-sx*sy*cz, cx*cy*cz+sx*sy*sz]
}
#[no_mangle]
pub extern "C" fn arika_euler_to_quaternion(e: *const f64, out: *mut f64) -> i32 {
    match checked::<3>(e) {
        Some(e) => output(out, euler_quat(e)),
        None => -1,
    }
}
#[no_mangle]
pub extern "C" fn arika_quaternion_to_euler(q: *const f64, out: *mut f64) -> i32 {
    let Some([mut x,mut y,mut z,mut w]) = checked::<4>(q) else {return -1};
    let len=(x*x+y*y+z*z+w*w).sqrt();
    if len <= 1e-12 {return -1;}
    x/=len;y/=len;z/=len;w/=len;
    let sin_pitch=(2.0*(w*y-z*x)).clamp(-1.0,1.0);
    let pitch=sin_pitch.asin();
    let (roll,yaw)=if sin_pitch.abs() >= 1.0-1e-10 {
        ((2.0*(w*x-y*z)).atan2(1.0-2.0*(x*x+z*z)),0.0)
    } else {
        ((2.0*(w*x+y*z)).atan2(1.0-2.0*(x*x+y*y)),
         (2.0*(w*z+x*y)).atan2(1.0-2.0*(y*y+z*z)))
    };
    output(out,[roll,pitch,yaw])
}
#[no_mangle]
pub extern "C" fn arika_quaternion_inverse(q: *const f64, out: *mut f64) -> i32 {
    let Some(q)=checked::<4>(q) else {return -1};
    let length=q.iter().map(|v|v*v).sum::<f64>();
    if length <= 1e-12 {return -1;}
    output(out,[-q[0]/length,-q[1]/length,-q[2]/length,q[3]/length])
}
#[no_mangle]
pub extern "C" fn arika_matrix_multiply(a: *const f64,b: *const f64,out: *mut f64) -> i32 {
    let (Some(a),Some(b))=(checked::<16>(a),checked::<16>(b)) else{return -1};
    let mut m=[0.0;16];
    for r in 0..4 {
        for c in 0..4 {
            m[r*4+c]=(0..4).map(|k|a[r*4+k]*b[k*4+c]).sum();
        }
    }
    output(out,m)
}
#[no_mangle]
pub extern "C" fn arika_matrix_local(
    translation: *const f64, rotation: *const f64, scale: *const f64, out: *mut f64
) -> i32 {
    let (Some(t),Some(q),Some(s))=(
        checked::<3>(translation),checked::<4>(rotation),checked::<3>(scale)
    ) else{return -1};
    let [x,y,z,w]=q;
    let m=[
        (1.0-2.0*(y*y+z*z))*s[0],2.0*(x*y-z*w)*s[1],2.0*(x*z+y*w)*s[2],t[0],
        2.0*(x*y+z*w)*s[0],(1.0-2.0*(x*x+z*z))*s[1],2.0*(y*z-x*w)*s[2],t[1],
        2.0*(x*z-y*w)*s[0],2.0*(y*z+x*w)*s[1],(1.0-2.0*(x*x+y*y))*s[2],t[2],
        0.0,0.0,0.0,1.0,
    ];
    output(out,m)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn euler_singularity_and_inverse() {
        let e=[0.0,std::f64::consts::FRAC_PI_2,0.0];
        let mut q=[0.0;4];
        let mut back=[0.0;3];
        assert_eq!(arika_euler_to_quaternion(e.as_ptr(),q.as_mut_ptr()),0);
        assert_eq!(arika_quaternion_to_euler(q.as_ptr(),back.as_mut_ptr()),0);
        assert!(back[0].abs()<1e-10 && (back[1]-e[1]).abs()<1e-10 && back[2].abs()<1e-10);
        let mut inverse=[0.0;4];
        assert_eq!(arika_quaternion_inverse(q.as_ptr(),inverse.as_mut_ptr()),0);
        assert!((inverse[1]+q[1]).abs()<1e-12);
        assert_eq!(arika_quaternion_inverse([0.0;4].as_ptr(),inverse.as_mut_ptr()),-1);
    }
    #[test]
    fn parent_child_matrix_composition() {
        let t=[2.0,3.0,4.0];let q=[0.0,0.0,0.0,1.0];let s=[2.0,2.0,2.0];
        let child_t=[1.0,0.0,0.0];let one=[1.0;3];
        let mut a=[0.0;16];let mut b=[0.0;16];let mut world=[0.0;16];
        assert_eq!(arika_matrix_local(t.as_ptr(),q.as_ptr(),s.as_ptr(),a.as_mut_ptr()),0);
        assert_eq!(arika_matrix_local(child_t.as_ptr(),q.as_ptr(),one.as_ptr(),b.as_mut_ptr()),0);
        assert_eq!(arika_matrix_multiply(a.as_ptr(),b.as_ptr(),world.as_mut_ptr()),0);
        assert_eq!([world[3],world[7],world[11]],[4.0,3.0,4.0]);
        assert_eq!(arika_matrix_multiply(a.as_ptr(),b.as_ptr(),a.as_mut_ptr()),0);
        assert_eq!(a,world);
    }
}
