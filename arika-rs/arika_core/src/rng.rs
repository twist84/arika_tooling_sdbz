//! Native 64-bit menu pseudo-random number generator (LCG).
//! Matches arika_menu_rng.py next_rng and c_native_rng.

pub const MULTIPLIER: u64 = 0x5851F42D4C957F2D;

/// Generate next 64-bit state and 31-bit random integer output.
#[inline]
pub fn next_rng(state: u64) -> (u64, u32) {
    let next_state = state.wrapping_mul(MULTIPLIER).wrapping_add(1);
    let value = ((next_state >> 32) & 0x7FFF_FFFF) as u32;
    (next_state, value)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct NativeRng {
    pub state: u64,
}

impl NativeRng {
    pub fn new(state: u64) -> Self {
        Self { state }
    }

    pub fn next(&mut self) -> u32 {
        let (s, val) = next_rng(self.state);
        self.state = s;
        val
    }

    pub fn state(&self) -> u64 {
        self.state
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_zero_and_one_state_vectors() {
        assert_eq!(next_rng(0), (1, 0));
        assert_eq!(next_rng(1), (0x5851f42d4c957f2e, 1481765933));
    }

    #[test]
    fn test_sequence_progression() {
        let mut rng = NativeRng::new(0);
        assert_eq!(rng.next(), 0);
        assert_eq!(rng.state(), 1);
        assert_eq!(rng.next(), 1481765933);
        assert_eq!(rng.state(), 0x5851f42d4c957f2e);
    }
}

