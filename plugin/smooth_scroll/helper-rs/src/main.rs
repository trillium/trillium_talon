//! One-shot trackpad-style smooth scroll gesture.
//!
//! Talon launches this and walks away. It plays the whole gesture on its own
//! clock (so Talon's busy main thread cannot delay an event), writes what it
//! measured to the result file, and exits. A hard cap guarantees it never lingers.
//!
//! usage: smooth-scroll-helper replay <recording.jsonl> <gesture_index> <result_path>
//!        (replays a recorded real gesture with its original timing and phases)
//!        smooth-scroll-helper <down|up> <pixels> <frames> <frame_ms> <decay> <min_pixels> <result_path>

use std::ffi::c_void;
use std::fs;
use std::time::{Duration, Instant};

#[link(name = "CoreGraphics", kind = "framework")]
extern "C" {
    fn CGEventCreateScrollWheelEvent2(
        source: *const c_void,
        units: u32,
        wheel_count: u32,
        wheel1: i32,
        wheel2: i32,
        wheel3: i32,
    ) -> *mut c_void;
    fn CGEventSetIntegerValueField(event: *mut c_void, field: u32, value: i64);
    fn CGEventPost(tap: u32, event: *mut c_void);
    fn CGEventCreate(source: *const c_void) -> *mut c_void;
    fn CGEventGetLocation(event: *mut c_void) -> Point;
    fn CGWarpMouseCursorPosition(p: Point) -> i32;
}

#[repr(C)]
#[derive(Clone, Copy)]
struct Point {
    x: f64,
    y: f64,
}

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;

// While parked, every event first checks the pointer is still at the target.
static PARK_TARGET: Mutex<Option<Point>> = Mutex::new(None);
static MOVED: AtomicBool = AtomicBool::new(false);
const PARK_TOLERANCE: f64 = 2.0;
const PARK_CAP_MS: u64 = 500;

fn pointer() -> Point {
    unsafe {
        let e = CGEventCreate(std::ptr::null());
        let p = CGEventGetLocation(e);
        CFRelease(e);
        p
    }
}

fn near(a: Point, b: Point) -> bool {
    (a.x - b.x).abs() <= PARK_TOLERANCE && (a.y - b.y).abs() <= PARK_TOLERANCE
}

/// Warp to `to` and poll until the pointer reads back there; false if it never does.
fn warp_confirmed(to: Point) -> bool {
    let start = Instant::now();
    unsafe {
        CGWarpMouseCursorPosition(to);
    }
    while start.elapsed() < Duration::from_millis(PARK_CAP_MS) {
        if near(pointer(), to) {
            return true;
        }
        std::thread::sleep(Duration::from_millis(1));
    }
    false
}
#[link(name = "CoreFoundation", kind = "framework")]
extern "C" {
    fn CFRelease(cf: *const c_void);
}

// NSEventPhase values for the scroll-phase field.
const PHASE_BEGAN: i64 = 1;
const PHASE_CHANGED: i64 = 4;
const PHASE_ENDED: i64 = 8;
const PHASE_CANCELLED: i64 = 16;
// CGMomentumScrollPhase values for the momentum field.
const MOMENTUM_BEGIN: i64 = 1;
const MOMENTUM_CONTINUE: i64 = 2;
const MOMENTUM_END: i64 = 3;
// CGEventField ids.
const FIELD_IS_CONTINUOUS: u32 = 88;
const FIELD_SCROLL_PHASE: u32 = 99;
const FIELD_MOMENTUM_PHASE: u32 = 123;

const HARD_CAP_MS: f64 = 10_000.0;

fn post(dy: i32, phase: i64, momentum: i64) {
    if let Some(t) = *PARK_TARGET.lock().unwrap() {
        if MOVED.load(Ordering::Relaxed) || !near(pointer(), t) {
            MOVED.store(true, Ordering::Relaxed); // the user took the pointer: stop scrolling
            return;
        }
    }
    unsafe {
        // units 0 = pixels
        let event = CGEventCreateScrollWheelEvent2(std::ptr::null(), 0, 1, dy, 0, 0);
        CGEventSetIntegerValueField(event, FIELD_IS_CONTINUOUS, 1);
        CGEventSetIntegerValueField(event, FIELD_SCROLL_PHASE, phase);
        CGEventSetIntegerValueField(event, FIELD_MOMENTUM_PHASE, momentum);
        CGEventPost(0, event); // HID event tap
        CFRelease(event);
    }
}

/// Sleep to an absolute deadline: coarse sleep, then spin for the last stretch.
fn wait_until(deadline: Instant) {
    let spin = Duration::from_micros(4000);
    let now = Instant::now();
    if deadline > now + spin {
        std::thread::sleep(deadline - now - spin);
    }
    while Instant::now() < deadline {
        std::hint::spin_loop();
    }
}

fn field(line: &str, key: &str) -> f64 {
    let pat = format!("\"{}\":", key);
    let i = line.find(&pat).expect("field") + pat.len();
    let rest = &line[i..];
    let end = rest.find(|c| c == ',' || c == '}').unwrap();
    rest[..end].trim().parse().expect("number")
}

/// +1 plays the recording as captured (it was recorded scrolling "up"); -1 is its exact mirror.
/// Anything else is refused: a misspelt direction must not quietly scroll the other way.
fn direction_sign(direction: &str) -> Option<i32> {
    match direction {
        "up" => Some(1),
        "down" => Some(-1),
        _ => None,
    }
}

/// Turns recorded deltas into whole-pixel events. The remainder of the scaling is
/// carried forward so the gesture's total is exact, and the direction is applied last,
/// so "down" is the negation of "up" event for event.
struct Stepper {
    want: f64,
    sent: i64,
}

impl Stepper {
    fn new() -> Self {
        Stepper { want: 0.0, sent: 0 }
    }

    fn next(&mut self, dy: i32, scale: f64, sign: i32) -> i32 {
        self.want += dy as f64 * scale;
        let step = (self.want.round() as i64 - self.sent) as i32;
        self.sent += step as i64;
        sign * step
    }
}

/// Replay one recorded gesture (events split on >300 ms gaps) with original timing.
fn replay(a: &[String]) {
    let text = fs::read_to_string(&a[2]).expect("recording");
    let idx: usize = a[3].parse().expect("gesture_index");
    let mut gestures: Vec<Vec<(f64, i32, i64, i64)>> = Vec::new();
    let mut last_t = f64::MIN;
    for line in text.lines().filter(|l| !l.trim().is_empty()) {
        let t = field(line, "t_ms");
        let e = (t, field(line, "dy_px").round() as i32, field(line, "phase") as i64, field(line, "momentum") as i64);
        if gestures.is_empty() || t - last_t > 300.0 {
            gestures.push(Vec::new());
        }
        gestures.last_mut().unwrap().push(e);
        last_t = t;
    }
    let g = gestures.get(idx).unwrap_or_else(|| {
        eprintln!("gesture {} not found ({} in file)", idx, gestures.len());
        std::process::exit(2);
    });
    unsafe {
        let warm = CGEventCreateScrollWheelEvent2(std::ptr::null(), 0, 1, 0, 0, 0);
        CGEventSetIntegerValueField(warm, FIELD_IS_CONTINUOUS, 1);
        CFRelease(warm);
    }
    // optional: direction (recording's own direction is "up") and distance scale
    let flip: i32 = match a.get(5) {
        None => 1,
        Some(d) => direction_sign(d).unwrap_or_else(|| {
            eprintln!("direction must be up or down, got {:?}", d);
            std::process::exit(2);
        }),
    };
    let scale: f64 = a.get(6).map(|v| v.parse().expect("scale")).unwrap_or(1.0);
    let stretch: f64 = a.get(7).map(|v| v.parse().expect("stretch")).unwrap_or(1.0);
    // A newer call cut off a gesture that was still playing: close that one out first.
    if a.get(8).map(|v| v == "cancel").unwrap_or(false) {
        post(0, PHASE_CANCELLED, 0);
    }
    let t0 = g[0].0;
    let start = Instant::now();
    let mut stepper = Stepper::new();
    let mut events: Vec<(u64, i32, char)> = Vec::new();
    for (t, dy, phase, momentum) in g {
        wait_until(start + Duration::from_secs_f64((t - t0) * stretch / 1000.0));
        let step = stepper.next(*dy, scale, flip);
        post(step, *phase, *momentum);
        events.push((start.elapsed().as_millis() as u64, step, if *momentum != 0 { 'm' } else { 'f' }));
    }
    if g.last().map(|e| e.2 != PHASE_ENDED && e.3 == 0).unwrap_or(false) {
        post(0, PHASE_ENDED, 0);
    }
    write_result(&a[4], &events);
}

fn write_result(result_path: &str, events: &[(u64, i32, char)]) {
    let gaps: Vec<u64> = events.windows(2).map(|w| w[1].0 - w[0].0).collect();
    let avg = if gaps.is_empty() { 0.0 } else { gaps.iter().sum::<u64>() as f64 / gaps.len() as f64 };
    let total_px: i64 = events.iter().map(|e| e.1 as i64).sum();
    let ev_json: Vec<String> = events
        .iter()
        .map(|(t, dy, tag)| format!("[{},{},\"{}\"]", t, dy, tag))
        .collect();
    let json = format!(
        "{{\"events\":[{}],\"avg_ms\":{:.1},\"min_ms\":{},\"max_ms\":{},\"total_ms\":{},\"total_px\":{}}}",
        ev_json.join(","),
        avg,
        gaps.iter().min().unwrap_or(&0),
        gaps.iter().max().unwrap_or(&0),
        events.last().map(|e| e.0).unwrap_or(0),
        total_px
    );
    let _ = fs::write(result_path, json);
}

/// Sustained scroll: constant speed while the control file keeps being touched
/// (hiss keeps arriving), then release into the usual decaying glide.
/// usage: hold <down|up> <pixels> <frame_ms> <decay> <min_pixels> <control_path> <result_path> [cancel]
fn hold(a: &[String]) {
    let sign: i32 = if a[2] == "down" { -1 } else { 1 };
    let pixels: f64 = a[3].parse().expect("pixels");
    let frame_ms: f64 = a[4].parse().expect("frame_ms");
    let decay: f64 = a[5].parse().expect("decay");
    let min_pixels: f64 = a[6].parse().expect("min_pixels");
    let control = &a[7];
    let grace = Duration::from_millis(300);
    let cap_ms = 30_000.0;
    let touched = || {
        fs::metadata(control).and_then(|m| m.modified()).ok().and_then(|t| t.elapsed().ok())
    };
    unsafe {
        let warm = CGEventCreateScrollWheelEvent2(std::ptr::null(), 0, 1, 0, 0, 0);
        CGEventSetIntegerValueField(warm, FIELD_IS_CONTINUOUS, 1);
        CFRelease(warm);
    }
    if a.get(9).map(|v| v == "cancel").unwrap_or(false) {
        post(0, PHASE_CANCELLED, 0);
    }
    let v0 = pixels / frame_ms;
    let k = -decay.ln() / frame_ms;
    let glide_ms = if pixels > min_pixels && decay > 0.0 && decay < 1.0 {
        frame_ms * (min_pixels / pixels).ln() / decay.ln()
    } else {
        0.0
    };
    let mut events: Vec<(u64, i32, char)> = Vec::new();
    let (mut sent, mut began) = (0i64, false);
    let mut release_ms: Option<f64> = None;
    let start = Instant::now();
    let mut n: u64 = 0;
    loop {
        wait_until(start + Duration::from_secs_f64(n as f64 * frame_ms / 1000.0));
        let t = start.elapsed().as_secs_f64() * 1000.0;
        if release_ms.is_none() && (touched().map(|e| e > grace).unwrap_or(true) || t > cap_ms) {
            release_ms = Some(t);
        }
        match release_ms {
            None => {
                let target = (v0 * t).round() as i64;
                let dy = sign * (target - sent) as i32;
                sent = target;
                post(dy, if began { PHASE_CHANGED } else { PHASE_BEGAN }, 0);
                began = true;
                events.push((t as u64, dy, 'f'));
            }
            Some(tr) => {
                let tau = (t - tr).min(glide_ms);
                let done = t - tr >= glide_ms;
                let target = (v0 * tr + v0 * (1.0 - (-k * tau).exp()) / k).round() as i64;
                let dy = sign * (target - sent) as i32;
                sent = target;
                if events.last().map(|e| e.2 == 'f').unwrap_or(true) {
                    post(0, PHASE_ENDED, 0);
                    post(dy, 0, MOMENTUM_BEGIN);
                } else {
                    post(dy, 0, if done { MOMENTUM_END } else { MOMENTUM_CONTINUE });
                }
                events.push((t as u64, dy, 'm'));
                if done {
                    break;
                }
            }
        }
        n += 1;
    }
    write_result(&a[8], &events);
}

fn main() {
    let mut a: Vec<String> = std::env::args().collect();
    // `--park tx,ty,ox,oy`: scroll with the pointer over (tx,ty), then put it back at (ox,oy).
    let mut park: Option<(Point, Point)> = None;
    if let Some(i) = a.iter().position(|x| x == "--park") {
        let v: Vec<f64> = a[i + 1].split(',').map(|n| n.parse().expect("park coord")).collect();
        park = Some((Point { x: v[0], y: v[1] }, Point { x: v[2], y: v[3] }));
        a.drain(i..=i + 1);
    }
    if let Some((target, _)) = park {
        if !warp_confirmed(target) {
            eprintln!("park: pointer never reached target, not scrolling");
            std::process::exit(4);
        }
        *PARK_TARGET.lock().unwrap() = Some(target);
    }
    run(&a);
    if let Some((target, origin)) = park {
        *PARK_TARGET.lock().unwrap() = None;
        // Restore only if the pointer is still where we put it; otherwise it is the user's.
        if !MOVED.load(Ordering::Relaxed) && near(pointer(), target) {
            warp_confirmed(origin);
        }
    }
}

fn run(a: &[String]) {
    if a.len() >= 9 && a[1] == "hold" {
        return hold(a);
    }
    if (5..=9).contains(&a.len()) && a[1] == "replay" {
        // usage: replay <recording> <gesture_index> <result_path>  (argv: bin replay rec idx result)
        return replay(a);
    }
    if a.len() != 8 {
        eprintln!("usage: {} <down|up> <pixels> <frames> <frame_ms> <decay> <min_pixels> <result_path>", a[0]);
        std::process::exit(2);
    }
    let sign: i32 = if a[1] == "down" { -1 } else { 1 };
    let pixels: f64 = a[2].parse().expect("pixels");
    let frames: f64 = a[3].parse().expect("frames");
    let frame_ms: f64 = a[4].parse().expect("frame_ms");
    let decay: f64 = a[5].parse().expect("decay");
    let min_pixels: f64 = a[6].parse().expect("min_pixels");
    let result_path = &a[7];

    // First use of the event APIs costs tens of ms; pay it before the clock starts.
    unsafe {
        let warm = CGEventCreateScrollWheelEvent2(std::ptr::null(), 0, 1, 0, 0, 0);
        CGEventSetIntegerValueField(warm, FIELD_IS_CONTINUOUS, 1);
        CFRelease(warm);
    }

    // Distance is a function of elapsed time: flat while the "finger" is down,
    // then a decaying glide. A late tick sends more pixels, never a longer gesture.
    let v0 = pixels / frame_ms; // px per ms
    let finger_ms = frames * frame_ms;
    let (glide_ms, k) = if pixels > min_pixels && decay > 0.0 && decay < 1.0 {
        (frame_ms * (min_pixels / pixels).ln() / decay.ln(), -decay.ln() / frame_ms)
    } else {
        (0.0, 1.0)
    };
    let distance_at = |t: f64| -> f64 {
        if t <= finger_ms {
            v0 * t
        } else {
            let tau = (t - finger_ms).min(glide_ms);
            v0 * finger_ms + v0 * (1.0 - (-k * tau).exp()) / k
        }
    };
    let total_ms = (finger_ms + glide_ms).min(HARD_CAP_MS);

    let mut events: Vec<(u64, i32, char)> = Vec::new();
    let (mut sent, mut began, mut ended, mut glide_begun) = (0i64, false, false, false);
    let start = Instant::now();
    let mut n: u64 = 0;
    loop {
        wait_until(start + Duration::from_secs_f64(n as f64 * frame_ms / 1000.0));
        let t_ms = start.elapsed().as_secs_f64() * 1000.0;
        let done = t_ms >= total_ms;
        let target = distance_at(t_ms.min(total_ms)).round() as i64;
        let dy = sign * (target - sent) as i32;
        sent = target;
        let tag;
        if t_ms <= finger_ms && !done {
            post(dy, if began { PHASE_CHANGED } else { PHASE_BEGAN }, 0);
            began = true;
            tag = 'f';
        } else {
            if !ended {
                ended = true;
                post(0, PHASE_ENDED, 0);
            }
            let momentum = if done {
                MOMENTUM_END
            } else if glide_begun {
                MOMENTUM_CONTINUE
            } else {
                MOMENTUM_BEGIN
            };
            glide_begun = true;
            post(dy, 0, momentum);
            tag = 'm';
        }
        events.push((t_ms.round() as u64, dy, tag));
        if done {
            break;
        }
        n += 1;
    }

    write_result(result_path, &events);
}

#[cfg(test)]
mod tests {
    use super::*;

    fn play(dys: &[i32], scale: f64, sign: i32) -> Vec<i32> {
        let mut s = Stepper::new();
        dys.iter().map(|d| s.next(*d, scale, sign)).collect()
    }

    #[test]
    fn down_is_the_exact_negation_of_up() {
        let dys = [1, 4, 3, 2, 3, 2, 4, 2, 5, 3, 6, 3, 8, 4, 7, 3, 10, 2, 1, 1];
        for scale in [0.3, 0.5, 1.0, 1.0 / 3.0, 1.7, 2.5, 4.0] {
            let (up, down) = (play(&dys, scale, 1), play(&dys, scale, -1));
            assert!(up.iter().zip(&down).all(|(u, d)| *u == -*d), "scale {}", scale);
            assert_eq!(up.iter().sum::<i32>() + down.iter().sum::<i32>(), 0);
        }
    }

    #[test]
    fn scaling_keeps_the_total_exact() {
        let dys = [1, 4, 3, 2, 3, 2, 4, 2, 5, 3];
        let total: i32 = dys.iter().sum();
        for scale in [0.3, 1.0, 1.7] {
            assert_eq!(play(&dys, scale, 1).iter().sum::<i32>(), (total as f64 * scale).round() as i32);
        }
    }

    #[test]
    fn only_up_and_down_are_directions() {
        assert_eq!(direction_sign("up"), Some(1));
        assert_eq!(direction_sign("down"), Some(-1));
        assert_eq!(direction_sign("sideways"), None);
        assert_eq!(direction_sign(""), None);
    }
}
