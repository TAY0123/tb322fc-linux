// SPDX-License-Identifier: GPL-3.0-only
// G9 2026 vendor motor command, verified on official 0.10-derived firmware.
// Input stays in evdev; this source only opens USB interface 4 for output.
use std::{
    collections::BTreeMap,
    error::Error,
    ffi::CString,
    time::{Duration, Instant},
};

use evdev::{EventSummary, FFEffectData, FFEffectKind};
use hidapi::HidDevice;
use packed_struct::types::SizedInteger;

use crate::{
    input::{
        capability::Capability,
        event::native::NativeEvent,
        output_capability::OutputCapability,
        output_event::OutputEvent,
        source::{
            haptic_gain_level, InputError, OutputError, SourceInputDevice, SourceOutputDevice,
        },
    },
    udev::device::UdevDevice,
};

pub const VID: u16 = 0x3537;
pub const PID: u16 = 0x1136;
pub const INTERFACE: i32 = 4;
const REFRESH: Duration = Duration::from_millis(100);
const DESCRIPTOR: &[u8] = &[
    0x06, 0x7a, 0xff, 0x09, 0x01, 0xa1, 0x01, 0x09, 0x02, 0xa1, 0x00, 0x09, 0x03, 0x15, 0x00, 0x25,
    0xff, 0x75, 0x08, 0x95, 0x40, 0x81, 0x02, 0x09, 0x05, 0x91, 0x02, 0xc0, 0xc0,
];

/// Zero is the unnumbered hidraw report ID. The device times out each nonzero
/// motor after 250 ms; a live source refreshes at 100 ms and shutdown sends zero.
fn motor_report(left: u16, right: u16) -> [u8; 7] {
    let l = (left >> 8) as u8;
    let r = (right >> 8) as u8;
    let mut packet = [0, 4, l, u8::from(l != 0), r, u8::from(r != 0), 0];
    packet[6] = packet[1..6].iter().fold(0u8, |sum, x| sum.wrapping_add(*x));
    packet
}

#[derive(Debug)]
struct Effect {
    data: FFEffectData,
    play: Option<(Instant, u32)>,
}

#[derive(Debug)]
struct RumbleState {
    effects: BTreeMap<i16, Effect>,
    direct: (u16, u16),
    gain: u16,
}

impl Default for RumbleState {
    fn default() -> Self {
        Self {
            effects: BTreeMap::new(),
            direct: (0, 0),
            gain: u16::MAX,
        }
    }
}

impl RumbleState {
    fn validate(data: &FFEffectData) -> Result<(), OutputError> {
        if !matches!(data.kind, FFEffectKind::Rumble { .. }) {
            return Err("G9 supports FF_RUMBLE effects only".into());
        }
        if data.trigger.button != 0 {
            return Err("G9 rumble does not support hardware button triggers".into());
        }
        Ok(())
    }

    fn upload(&mut self, data: FFEffectData) -> Result<i16, OutputError> {
        Self::validate(&data)?;
        let id = (0..64)
            .find(|id| !self.effects.contains_key(id))
            .ok_or("Maximum G9 FF effects uploaded")?;
        self.effects.insert(id, Effect { data, play: None });
        Ok(id)
    }

    fn update(&mut self, id: i16, data: FFEffectData) -> Result<(), OutputError> {
        Self::validate(&data)?;
        self.effects
            .get_mut(&id)
            .ok_or("Unknown G9 FF effect")?
            .data = data;
        Ok(())
    }

    fn play(&mut self, id: i16, repeats: i32, now: Instant) -> Result<(), OutputError> {
        let effect = self.effects.get_mut(&id).ok_or("Unknown G9 FF effect")?;
        effect.play = (repeats > 0).then_some((now, repeats.max(0) as u32));
        Ok(())
    }

    fn sample(&mut self, now: Instant) -> (u16, u16) {
        let (mut left, mut right) = (u64::from(self.direct.0), u64::from(self.direct.1));
        for effect in self.effects.values_mut() {
            let Some((started, repeats)) = effect.play else {
                continue;
            };
            let elapsed = now.saturating_duration_since(started).as_millis();
            let delay = u128::from(effect.data.replay.delay);
            let length = u128::from(effect.data.replay.length);
            // evdev length 0 means continuous playback, after the initial delay.
            let on = if length == 0 {
                elapsed >= delay
            } else {
                let cycle = delay + length;
                if elapsed >= cycle * u128::from(repeats) {
                    effect.play = None;
                    false
                } else {
                    elapsed % cycle >= delay
                }
            };
            if on {
                if let FFEffectKind::Rumble {
                    strong_magnitude,
                    weak_magnitude,
                } = effect.data.kind
                {
                    left += u64::from(strong_magnitude);
                    right += u64::from(weak_magnitude);
                }
            }
        }
        let scale = |x: u64| ((x.min(65535) * u64::from(self.gain)) / 65535) as u16;
        (scale(left), scale(right))
    }
}

pub struct LegionG9Rumble {
    device: HidDevice,
    state: RumbleState,
    last: Option<([u8; 7], Instant)>,
}

impl std::fmt::Debug for LegionG9Rumble {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("LegionG9Rumble")
            .field("state", &self.state)
            .finish()
    }
}

impl LegionG9Rumble {
    pub fn new(info: UdevDevice) -> Result<Self, Box<dyn Error + Send + Sync>> {
        if (info.id_vendor(), info.id_product(), info.interface_number()) != (VID, PID, INTERFACE) {
            return Err("Not a G9 2026 vendor motor interface".into());
        }
        let api = hidapi::HidApi::new()?;
        let device = api.open_path(&CString::new(info.devnode())?)?;
        let mut descriptor = [0u8; 256];
        let size = device.get_report_descriptor(&mut descriptor)?;
        if &descriptor[..size] != DESCRIPTOR {
            return Err("Unexpected G9 vendor report descriptor".into());
        }
        device.set_blocking_mode(false)?;
        Ok(Self {
            device,
            state: RumbleState::default(),
            last: None,
        })
    }

    fn send(&mut self, packet: [u8; 7], now: Instant) -> Result<(), OutputError> {
        let written = self.device.write(&packet).map_err(|e| e.to_string())?;
        if written != packet.len() {
            return Err(format!("Short G9 motor write: {written}/{}", packet.len()).into());
        }
        log::trace!("G9 motor output: {packet:02x?}");
        self.last = Some((packet, now));
        Ok(())
    }

    fn flush(&mut self, now: Instant) -> Result<(), OutputError> {
        let (left, right) = self.state.sample(now);
        let packet = motor_report(left, right);
        let needed = self.last.as_ref().is_none_or(|(previous, at)| {
            *previous != packet
                || ((packet[2] != 0 || packet[4] != 0)
                    && now.saturating_duration_since(*at) >= REFRESH)
        });
        if needed {
            self.send(packet, now)?;
        }
        Ok(())
    }

    fn direct(&mut self, left: u16, right: u16, now: Instant) -> Result<(), OutputError> {
        // A direct stream replaces prior evdev playback; zero always stops it.
        for effect in self.state.effects.values_mut() {
            effect.play = None;
        }
        self.state.direct = (left, right);
        self.flush(now)
    }
}

impl Drop for LegionG9Rumble {
    fn drop(&mut self) {
        let _ = self.device.write(&motor_report(0, 0));
    }
}

impl SourceInputDevice for LegionG9Rumble {
    fn poll(&mut self) -> Result<Vec<NativeEvent>, InputError> {
        // Drain vendor replies without forwarding them as input; read errors
        // also detect unplug. No gamepad reports are read from this interface.
        let mut reply = [0u8; 64];
        for _ in 0..8 {
            if self
                .device
                .read_timeout(&mut reply, 0)
                .map_err(|e| e.to_string())?
                == 0
            {
                break;
            }
        }
        self.flush(Instant::now()).map_err(|e| e.to_string())?;
        Ok(vec![])
    }

    fn get_capabilities(&self) -> Result<Vec<Capability>, InputError> {
        Ok(vec![])
    }
}

impl SourceOutputDevice for LegionG9Rumble {
    fn get_output_capabilities(&self) -> Result<Vec<OutputCapability>, OutputError> {
        Ok(vec![
            OutputCapability::ForceFeedback,
            OutputCapability::ForceFeedbackUpload,
            OutputCapability::ForceFeedbackErase,
        ])
    }

    fn write_event(&mut self, event: OutputEvent) -> Result<(), OutputError> {
        let now = Instant::now();
        let with_gain = |speed: u16, gain: i8| {
            haptic_gain_level(gain, 65535.0, f64::from(speed) * 100.0 / 65535.0).clamp(0.0, 65535.0)
                as u16
        };
        match event {
            OutputEvent::GenericRumble {
                strong_magnitude,
                weak_magnitude,
            } => self.direct(strong_magnitude, weak_magnitude, now),
            OutputEvent::DualSense(report) => {
                if report.use_rumble_not_haptics || report.enable_improved_rumble_emulation {
                    self.direct(
                        u16::from(report.rumble_emulation_left) * 257,
                        u16::from(report.rumble_emulation_right) * 257,
                        now,
                    )?;
                }
                Ok(())
            }
            OutputEvent::TriggerVibration(report) => self.direct(
                with_gain(report.left_speed.to_primitive(), report.left_gain),
                with_gain(report.right_speed.to_primitive(), report.right_gain),
                now,
            ),
            OutputEvent::TriggerVibrationExtended(report) => {
                let r = report.combined_rumble();
                self.direct(
                    with_gain(r.left_speed.to_primitive(), r.left_gain),
                    with_gain(r.right_speed.to_primitive(), r.right_gain),
                    now,
                )
            }
            OutputEvent::Evdev(event) => {
                if let EventSummary::ForceFeedback(_, code, value) = event.destructure() {
                    if code.0 == 0x60 {
                        // FF_GAIN
                        self.state.gain = value.clamp(0, 65535) as u16;
                    } else {
                        self.state.direct = (0, 0);
                        self.state.play(code.0 as i16, value, now)?;
                    }
                    self.flush(now)?;
                }
                Ok(())
            }
            // Grip motors support ordinary rumble, not trackpad/trigger haptics.
            _ => Ok(()),
        }
    }

    fn upload_effect(&mut self, effect: FFEffectData) -> Result<i16, OutputError> {
        self.state.upload(effect)
    }
    fn update_effect(&mut self, id: i16, effect: FFEffectData) -> Result<(), OutputError> {
        self.state.update(id, effect)?;
        self.flush(Instant::now())
    }
    fn erase_effect(&mut self, id: i16) -> Result<(), OutputError> {
        self.state.effects.remove(&id);
        self.flush(Instant::now())
    }
    fn stop(&mut self) -> Result<(), OutputError> {
        self.state = RumbleState::default();
        self.send(motor_report(0, 0), Instant::now())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use evdev::{FFReplay, FFTrigger};

    fn effect(left: u16, right: u16, delay: u16, length: u16) -> FFEffectData {
        FFEffectData {
            direction: 0,
            trigger: FFTrigger {
                button: 0,
                interval: 0,
            },
            replay: FFReplay { delay, length },
            kind: FFEffectKind::Rumble {
                strong_magnitude: left,
                weak_magnitude: right,
            },
        }
    }

    #[test]
    fn hardware_verified_packets_and_checksum_wrap() {
        assert_eq!(motor_report(0x6000, 0), [0, 4, 96, 1, 0, 0, 101]);
        assert_eq!(motor_report(0, 0x6000), [0, 4, 0, 0, 96, 1, 101]);
        assert_eq!(motor_report(0, 0), [0, 4, 0, 0, 0, 0, 4]);
        assert_eq!(motor_report(65535, 65535), [0, 4, 255, 1, 255, 1, 4]);
    }

    #[test]
    fn delay_duration_repeats_and_expiration() {
        let mut s = RumbleState::default();
        let t = Instant::now();
        let id = s.upload(effect(1000, 2000, 20, 50)).unwrap();
        s.play(id, 2, t).unwrap();
        for (ms, expected) in [
            (0, (0, 0)),
            (19, (0, 0)),
            (20, (1000, 2000)),
            (69, (1000, 2000)),
            (70, (0, 0)),
            (90, (1000, 2000)),
            (139, (1000, 2000)),
            (140, (0, 0)),
        ] {
            assert_eq!(
                s.sample(t + Duration::from_millis(ms)),
                expected,
                "at {ms} ms"
            );
        }
        assert!(s.effects[&id].play.is_none());
    }

    #[test]
    fn continuous_effect_stop_update_and_erase() {
        let mut s = RumbleState::default();
        let t = Instant::now();
        let id = s.upload(effect(5000, 7000, 0, 0)).unwrap();
        s.play(id, 1, t).unwrap();
        assert_eq!(s.sample(t + Duration::from_secs(120)), (5000, 7000));
        s.update(id, effect(8000, 9000, 0, 0)).unwrap();
        assert_eq!(s.sample(t), (8000, 9000));
        s.play(id, 0, t).unwrap();
        assert_eq!(s.sample(t), (0, 0));
        s.play(id, 1, t).unwrap();
        s.effects.remove(&id);
        assert_eq!(s.sample(t), (0, 0));
    }

    #[test]
    fn overlapping_effects_saturate_gain_and_stop_individually() {
        let mut s = RumbleState::default();
        let t = Instant::now();
        let a = s.upload(effect(40000, 1000, 0, 100)).unwrap();
        let b = s.upload(effect(40000, 2000, 0, 100)).unwrap();
        s.play(a, 1, t).unwrap();
        s.play(b, 1, t).unwrap();
        assert_eq!(s.sample(t), (65535, 3000));
        s.gain = 32767;
        assert_eq!(s.sample(t), (32767, 1499));
        s.gain = 65535;
        s.play(a, 0, t).unwrap();
        assert_eq!(s.sample(t), (40000, 2000));
    }

    #[test]
    fn bounds_and_unsupported_effects() {
        let mut s = RumbleState::default();
        for id in 0..64 {
            assert_eq!(s.upload(effect(0, 0, 0, 1)).unwrap(), id);
        }
        assert!(s.upload(effect(0, 0, 0, 1)).is_err());
        assert!(s.play(64, 1, Instant::now()).is_err());
        let mut invalid = effect(0, 0, 0, 1);
        invalid.kind = FFEffectKind::Damper;
        assert!(s.update(0, invalid).is_err());
    }
}
