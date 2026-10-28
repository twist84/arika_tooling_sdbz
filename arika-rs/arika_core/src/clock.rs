//! Scalar native MOT2 clock controller.
//! Matches arika_clock.py c_native_clock exactly.

use crate::error::{ArikaError, Result};
use serde::{Deserialize, Serialize};

pub const ACTIVE: u32 = 0x01000000;
pub const PAUSED: u32 = 0x04000000;
pub const DIRTY: u32 = 0x02000000;
pub const WRAPPED: u32 = 0x08000000;
pub const REVERSE: u32 = 0x00020000;
pub const LOOP: u32 = 0x00010000;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClockSnapshot {
    pub position: f32,
    pub sample_time: f32,
    pub start_time: f32,
    pub end_time: f32,
    pub baseline: f32,
    pub speed: f32,
    pub stop_timer: f32,
    pub blend_total: f32,
    pub blend_remaining: f32,
    pub blend_weight: f32,
    pub carry: f32,
    pub wrap_fraction: Option<f32>,
    pub active: bool,
    pub flags: u32,
    pub advanced: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NativeClock {
    pub frame_period: f32,
    pub start: f32,
    pub end: f32,
    pub speed: f32,
    pub baseline: f32,
    pub position: f32,
    pub blend_total: f32,
    pub blend_remaining: f32,
    pub stop_timer: f32,
    pub scale_channels: usize,
    pub flags: u32,
    pub initialization_tick: Option<ClockSnapshot>,
}

impl NativeClock {
    pub fn new(
        fps: f32,
        frame_count: u16,
        start_frame: f32,
        end_frame: f32,
        speed: f32,
        blend: f32,
        reverse: bool,
        loop_mode: bool,
        stop_after: f32,
        scale_channels: usize,
        inherited_blend: Option<(f32, f32)>,
    ) -> Result<Self> {
        if !fps.is_finite()
            || !start_frame.is_finite()
            || !end_frame.is_finite()
            || !speed.is_finite()
            || !blend.is_finite()
            || !stop_after.is_finite()
        {
            return Err(ArikaError::Other("nonfinite clock setup".into()));
        }
        if fps <= 0.0 || frame_count == 0 {
            return Err(ArikaError::Other("invalid clock motion timing".into()));
        }

        let frame_period = 1.0f32 / fps;
        if frame_period <= 0.0 || !frame_period.is_finite() {
            return Err(ArikaError::Other("invalid float32 frame period".into()));
        }

        let last = (frame_count - 1) as f32;
        let start_f = start_frame.max(0.0).min(last);
        let end_f = if end_frame < 0.0 {
            last
        } else {
            end_frame.min(last)
        };

        if end_f < start_f {
            return Err(ArikaError::Other(
                "reversed frame range is unsupported".into(),
            ));
        }

        let start = start_f * frame_period;
        let end = end_f * frame_period;
        let speed = speed.max(0.01f32);
        let baseline = if reverse {
            end + frame_period
        } else {
            start - frame_period
        };
        let position = baseline;

        let mut blend_total = blend.max(0.0);
        let mut blend_remaining = blend_total;
        if blend < 0.0 {
            if let Some((total, remaining)) = inherited_blend {
                if total.is_finite() && remaining.is_finite() && total >= 0.0 && remaining <= total {
                    blend_total = total;
                    blend_remaining = remaining;
                } else {
                    return Err(ArikaError::Other("invalid inherited blend".into()));
                }
            }
        }

        let stop_timer = stop_after;
        let mut flags = ACTIVE | DIRTY;
        if reverse {
            flags |= REVERSE;
        }
        if loop_mode {
            flags |= LOOP;
        }
        if scale_channels != 0 {
            flags |= 0x100;
        }

        if (!reverse && start == baseline) || (reverse && end == baseline) {
            return Err(ArikaError::Other(
                "unrepresentable clock baseline".into(),
            ));
        }

        let mut clock = Self {
            frame_period,
            start,
            end,
            speed,
            baseline,
            position,
            blend_total,
            blend_remaining,
            stop_timer,
            scale_channels,
            flags,
            initialization_tick: None,
        };

        if stop_timer == 0.0 || end <= start {
            clock.initialization_tick = Some(clock.step(frame_period));
        }

        Ok(clock)
    }

    pub fn snapshot(
        &self,
        carry: f32,
        wrap_fraction: Option<f32>,
        advanced: bool,
    ) -> ClockSnapshot {
        let weight = if self.blend_remaining > 0.0 && self.blend_total > 0.0 {
            1.0 - (self.blend_remaining / self.blend_total)
        } else {
            1.0
        };
        let sample_time = self.position.max(self.start).min(self.end);

        ClockSnapshot {
            position: self.position,
            sample_time,
            start_time: self.start,
            end_time: self.end,
            baseline: self.baseline,
            speed: self.speed,
            stop_timer: self.stop_timer,
            blend_total: self.blend_total,
            blend_remaining: self.blend_remaining,
            blend_weight: weight,
            carry,
            wrap_fraction,
            active: (self.flags & ACTIVE) != 0,
            flags: self.flags,
            advanced,
        }
    }

    pub fn step(&mut self, delta: f32) -> ClockSnapshot {
        if !delta.is_finite() {
            return self.snapshot(0.0, None, false);
        }
        if (self.flags & ACTIVE) == 0 {
            return self.snapshot(delta, None, false);
        }
        if (self.flags & PAUSED) != 0 || delta <= 0.0 {
            return self.snapshot(0.0, None, false);
        }

        let mut scaled = delta * self.speed;
        let mut carry = 0.0f32;
        let mut overshoot = 0.0f32;
        let mut finished = false;
        let mut fraction = None;

        if self.stop_timer > 0.0 {
            self.stop_timer -= scaled;
            if self.stop_timer <= 0.0 {
                overshoot = -self.stop_timer;
                carry = overshoot / self.speed;
                scaled += self.stop_timer;
                finished = true;
            }
        }

        if self.blend_remaining > 0.0 {
            self.blend_remaining -= scaled;
            if self.blend_remaining <= 0.0 {
                if self.scale_channels == 0 {
                    self.flags &= !0x100;
                }
                self.flags |= DIRTY;
            }
        }

        let reverse = (self.flags & REVERSE) != 0;
        if reverse {
            self.position -= scaled;
        } else {
            self.position += scaled;
        }

        if (self.flags & LOOP) != 0 {
            let period = if reverse {
                self.baseline - self.start
            } else {
                self.end - self.baseline
            };
            if period > 0.0 {
                for _ in 0..100000 {
                    let outside = if reverse {
                        self.position < self.start
                    } else {
                        self.position > self.end
                    };
                    if !outside {
                        break;
                    }
                    self.flags |= WRAPPED;
                    let updated = if reverse {
                        self.position + period
                    } else {
                        self.position - period
                    };
                    if updated == self.position {
                        break;
                    }
                    self.position = updated;
                }
            }
        } else {
            let at_end = if reverse {
                self.position <= self.start
            } else {
                self.position >= self.end
            };
            if at_end {
                let extra = if reverse {
                    self.start - self.position
                } else {
                    self.position - self.end
                };
                carry = (overshoot + extra) / self.speed;
                self.position = if reverse { self.start } else { self.end };
                finished = true;
            }
        }

        if (self.flags & WRAPPED) != 0 {
            if reverse && self.position > self.end {
                fraction = Some((self.position - self.end) / self.frame_period);
            } else if !reverse && self.position < self.start {
                fraction = Some(1.0 - (self.start - self.position) / self.frame_period);
            }
        }

        if finished {
            self.flags &= 0xF;
        }
        self.flags &= !DIRTY;

        self.snapshot(carry, fraction, true)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_forward_setup_and_first_tick() {
        let mut clock = NativeClock::new(2.0, 3, 0.0, -1.0, 1.0, 0.0, false, false, -1.0, 0, None)
            .expect("clock");
        assert_eq!(clock.snapshot(0.0, None, false).position, -0.5);
        assert_eq!(clock.step(0.5).position, 0.0);
        assert_eq!(clock.step(0.5).position, 0.5);
        let state = clock.step(0.5);
        assert_eq!(state.position, 1.0);
        assert!(!state.active);
        assert_eq!(state.carry, 0.0);
    }

    #[test]
    fn test_carry_is_in_wall_delta_units() {
        let mut clock = NativeClock::new(2.0, 3, 0.0, -1.0, 2.0, 0.0, false, false, -1.0, 0, None)
            .expect("clock");
        let state = clock.step(1.0);
        assert_eq!(state.position, 1.0);
        assert_eq!(state.carry, 0.25);
        assert_eq!(clock.step(0.125).carry, 0.125);
    }

    #[test]
    fn test_reverse() {
        let mut clock = NativeClock::new(2.0, 3, 0.0, -1.0, 1.0, 0.0, true, false, -1.0, 0, None)
            .expect("clock");
        assert_eq!(clock.step(0.5).position, 1.0);
        let state = clock.step(2.0);
        assert_eq!((state.position, state.carry), (0.0, 1.0));
        assert!(!state.active);
    }

    #[test]
    fn test_loop_boundary_gap_fraction() {
        let mut clock = NativeClock::new(2.0, 3, 0.0, -1.0, 1.0, 0.0, false, true, -1.0, 0, None)
            .expect("clock");
        let state = clock.step(1.6);
        assert!((state.flags & WRAPPED) != 0);
        assert!((state.wrap_fraction.unwrap() - 0.2).abs() < 1e-6);
        assert_eq!(state.sample_time, 0.0);

        let mut rev = NativeClock::new(2.0, 3, 0.0, -1.0, 1.0, 0.0, true, true, -1.0, 0, None)
            .expect("clock");
        let rev_state = rev.step(1.6);
        assert!((rev_state.wrap_fraction.unwrap() - 0.8).abs() < 1e-6);
    }

    #[test]
    fn test_blend_countdown() {
        let mut clock = NativeClock::new(2.0, 100, 0.0, -1.0, 2.0, 1.0, false, false, -1.0, 0, None)
            .expect("clock");
        clock.flags |= 0x100;
        let state = clock.step(0.25);
        assert_eq!((state.blend_remaining, state.blend_weight), (0.5, 0.5));
        let state2 = clock.step(0.3);
        assert_eq!(state2.blend_weight, 1.0);
        assert_eq!(state2.flags & 0x100, 0);
    }
}

