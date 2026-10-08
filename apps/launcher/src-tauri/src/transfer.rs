//! Byte counts for the Updates screen: how much has come down the wire and
//! how much has gone to disk, per update, so it can draw a bar for each row
//! and a speed graph over the whole run.
//!
//! The installers do not take a reporter. A command that wants its bytes
//! counted runs its work inside [`scoped`], and every download or write on
//! that thread reports under the task it named — including a dependency that
//! `install_one` pulls in on the way, which nobody had to thread a callback
//! through. Outside a scope every call here is a no-op, so the same code runs
//! unchanged for tests and for callers that never asked.
//!
//! The webview computes the speeds. This only says how many bytes so far,
//! which is the one thing it cannot know.

use std::cell::RefCell;
use std::io::{self, Read};
use std::time::{Duration, Instant};

use serde::Serialize;
use tauri::{AppHandle, Emitter};

/// Often enough for a smooth bar, rare enough not to flood the event bus.
const EMIT_EVERY: Duration = Duration::from_millis(100);

#[derive(Clone, Serialize)]
struct Transfer {
    task: String,
    /// Downloaded so far, across every file the task has fetched.
    received: u64,
    /// What `received` is heading for, while every size is known.
    total: Option<u64>,
    /// Written to disk so far.
    written: u64,
}

struct Sink {
    app: AppHandle,
    task: String,
    /// Files already finished: their bytes and their sizes.
    finished: u64,
    finished_total: u64,
    /// The file coming down now.
    current: u64,
    current_total: Option<u64>,
    written: u64,
    last: Option<Instant>,
}

impl Sink {
    fn emit(&mut self, force: bool) {
        let now = Instant::now();
        if !force && self.last.is_some_and(|t| now - t < EMIT_EVERY) {
            return;
        }
        self.last = Some(now);
        let _ = self.app.emit(
            "transfer",
            Transfer {
                task: self.task.clone(),
                received: self.finished + self.current,
                total: self.current_total.map(|t| self.finished_total + t),
                written: self.written,
            },
        );
    }
}

thread_local! {
    static SINK: RefCell<Option<Sink>> = const { RefCell::new(None) };
}

fn with(f: impl FnOnce(&mut Sink)) {
    SINK.with(|s| {
        if let Some(sink) = s.borrow_mut().as_mut() {
            f(sink);
        }
    });
}

/// Clears the sink however the scope ends: these run on a pooled blocking
/// thread, and a panic must not leave the next job reporting as this one.
struct Clear;

impl Drop for Clear {
    fn drop(&mut self) {
        with(|s| s.emit(true));
        SINK.with(|s| s.borrow_mut().take());
    }
}

/// Run `f` with its downloads and writes reported as `task`. No task, no
/// reporting.
pub fn scoped<T>(app: &AppHandle, task: Option<String>, f: impl FnOnce() -> T) -> T {
    let Some(task) = task else { return f() };
    SINK.with(|s| {
        *s.borrow_mut() = Some(Sink {
            app: app.clone(),
            task,
            finished: 0,
            finished_total: 0,
            current: 0,
            current_total: None,
            written: 0,
            last: None,
        })
    });
    let _clear = Clear;
    with(|s| s.emit(true));
    f()
}

/// Read a response body to the end, counting it. `each` hears the running
/// byte count after every chunk, for callers with progress of their own.
pub fn read_body(
    mut body: impl Read,
    total: Option<u64>,
    mut each: impl FnMut(u64),
) -> io::Result<Vec<u8>> {
    with(|s| {
        s.current = 0;
        s.current_total = total;
    });
    // Capped: a lying Content-Length must not reserve gigabytes up front.
    let mut out = Vec::with_capacity(total.unwrap_or(0).min(256 << 20) as usize);
    let mut buf = vec![0u8; 64 * 1024];
    loop {
        let n = body.read(&mut buf)?;
        if n == 0 {
            break;
        }
        out.extend_from_slice(&buf[..n]);
        let got = out.len() as u64;
        each(got);
        with(|s| {
            s.current = got;
            s.emit(false);
        });
    }
    with(|s| {
        s.finished += s.current;
        s.finished_total += s.current_total.unwrap_or(s.current);
        s.current = 0;
        s.current_total = Some(0);
        s.emit(true);
    });
    Ok(out)
}

/// Count `bytes` written to disk.
pub fn wrote(bytes: u64) {
    with(|s| {
        s.written += bytes;
        s.emit(false);
    });
}
