//! Listen-only recorder for real scroll events (trackpad gestures).
//!
//! Installs a passive event tap, writes one JSON line per scroll event, and
//! exits by itself after the given number of seconds. Needs Input Monitoring
//! permission for the launching app.
//!
//! usage: scroll-recorder <seconds> <out_path>
//! line: {"t_ms":..,"dy_px":..,"dy_line":..,"phase":..,"momentum":..,"continuous":..}

use std::ffi::c_void;
use std::fs::File;
use std::io::{BufWriter, Write};
use std::sync::Mutex;
use std::time::Instant;

type CFRef = *const c_void;

#[link(name = "CoreGraphics", kind = "framework")]
extern "C" {
    fn CGEventTapCreate(
        tap: u32,
        place: u32,
        options: u32,
        events_of_interest: u64,
        callback: extern "C" fn(CFRef, u32, CFRef, *mut c_void) -> CFRef,
        user_info: *mut c_void,
    ) -> CFRef;
    fn CGEventTapEnable(tap: CFRef, enable: bool);
    fn CGEventGetIntegerValueField(event: CFRef, field: u32) -> i64;
    fn CGEventGetDoubleValueField(event: CFRef, field: u32) -> f64;
}
#[link(name = "CoreFoundation", kind = "framework")]
extern "C" {
    static kCFRunLoopCommonModes: CFRef;
    static kCFRunLoopDefaultMode: CFRef;
    fn CFMachPortCreateRunLoopSource(alloc: CFRef, port: CFRef, order: i64) -> CFRef;
    fn CFRunLoopGetCurrent() -> CFRef;
    fn CFRunLoopAddSource(rl: CFRef, source: CFRef, mode: CFRef);
    fn CFRunLoopRunInMode(mode: CFRef, seconds: f64, return_after_source: bool) -> i32;
}

const SCROLL_WHEEL: u32 = 22;
const FIELD_LINE_DELTA_1: u32 = 11;
const FIELD_IS_CONTINUOUS: u32 = 88;
const FIELD_POINT_DELTA_1: u32 = 96;
const FIELD_SCROLL_PHASE: u32 = 99;
const FIELD_MOMENTUM_PHASE: u32 = 123;

static OUT: Mutex<Option<BufWriter<File>>> = Mutex::new(None);
static START: Mutex<Option<Instant>> = Mutex::new(None);

extern "C" fn on_event(_proxy: CFRef, kind: u32, event: CFRef, _info: *mut c_void) -> CFRef {
    if kind == SCROLL_WHEEL {
        let t_ms = START.lock().unwrap().unwrap().elapsed().as_secs_f64() * 1000.0;
        let (dy_px, dy_line, phase, momentum, cont) = unsafe {
            (
                CGEventGetDoubleValueField(event, FIELD_POINT_DELTA_1),
                CGEventGetIntegerValueField(event, FIELD_LINE_DELTA_1),
                CGEventGetIntegerValueField(event, FIELD_SCROLL_PHASE),
                CGEventGetIntegerValueField(event, FIELD_MOMENTUM_PHASE),
                CGEventGetIntegerValueField(event, FIELD_IS_CONTINUOUS),
            )
        };
        if let Some(w) = OUT.lock().unwrap().as_mut() {
            let _ = writeln!(
                w,
                "{{\"t_ms\":{:.2},\"dy_px\":{},\"dy_line\":{},\"phase\":{},\"momentum\":{},\"continuous\":{}}}",
                t_ms, dy_px, dy_line, phase, momentum, cont
            );
        }
    }
    event
}

fn main() {
    let a: Vec<String> = std::env::args().collect();
    if a.len() != 3 {
        eprintln!("usage: {} <seconds> <out_path>", a[0]);
        std::process::exit(2);
    }
    let seconds: f64 = a[1].parse().expect("seconds");
    *OUT.lock().unwrap() = Some(BufWriter::new(File::create(&a[2]).expect("out file")));
    *START.lock().unwrap() = Some(Instant::now());
    unsafe {
        // session tap, head insert, listen-only
        let tap = CGEventTapCreate(1, 0, 1, 1u64 << SCROLL_WHEEL, on_event, std::ptr::null_mut());
        if tap.is_null() {
            eprintln!("could not create the event tap: grant Input Monitoring permission");
            std::process::exit(3);
        }
        let source = CFMachPortCreateRunLoopSource(std::ptr::null(), tap, 0);
        CFRunLoopAddSource(CFRunLoopGetCurrent(), source, kCFRunLoopCommonModes);
        CGEventTapEnable(tap, true);
        CFRunLoopRunInMode(kCFRunLoopDefaultMode, seconds, false);
    }
    if let Some(w) = OUT.lock().unwrap().as_mut() {
        let _ = w.flush();
    }
}
