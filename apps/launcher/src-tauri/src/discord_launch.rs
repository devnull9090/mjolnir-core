//! Starting a game for Discord's pending IPC join. Repeated protocol events
//! must not create a second custom-EXE process while the first is booting.
use std::time::{Duration, Instant};

#[derive(Default)]
pub struct LaunchGuard {
    started: Option<Instant>,
}

impl LaunchGuard {
    pub const fn new() -> Self {
        Self { started: None }
    }

    /// Held under a mutex by the command, including the running check and
    /// launch. A successful spawn gets a short grace period before tasklist
    /// can be expected to see the game (store launchers start it indirectly).
    pub fn start(
        &mut self,
        clock: impl Fn() -> Instant,
        running: impl FnOnce() -> bool,
        launch: impl FnOnce() -> Result<(), String>,
    ) -> Result<bool, String> {
        if running()
            || self
                .started
                .is_some_and(|at| clock().saturating_duration_since(at) < Duration::from_secs(30))
        {
            return Ok(false);
        }
        launch()?;
        self.started = Some(clock());
        Ok(true)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;

    #[test]
    fn running_game_receives_the_ipc_join_without_another_launch() {
        let mut guard = LaunchGuard::default();
        assert_eq!(
            guard.start(Instant::now, || true, || panic!("must not launch")),
            Ok(false)
        );
    }

    #[test]
    fn repeated_invites_during_boot_spawn_once_then_allow_a_later_retry() {
        let mut guard = LaunchGuard::default();
        let now = Instant::now();
        let starts = Cell::new(0);
        let launch = || {
            starts.set(starts.get() + 1);
            Ok(())
        };
        assert_eq!(guard.start(|| now, || false, launch), Ok(true));
        assert_eq!(
            guard.start(|| now + Duration::from_secs(1), || false, launch),
            Ok(false)
        );
        assert_eq!(starts.get(), 1);
        assert_eq!(
            guard.start(|| now + Duration::from_secs(31), || false, launch),
            Ok(true)
        );
        assert_eq!(starts.get(), 2);
    }

    #[test]
    fn failed_launch_can_be_retried_immediately() {
        let mut guard = LaunchGuard::default();
        let now = Instant::now();
        assert_eq!(
            guard.start(|| now, || false, || Err("missing game".into())),
            Err("missing game".into())
        );
        assert_eq!(guard.start(|| now, || false, || Ok(())), Ok(true));
    }

    #[test]
    fn grace_period_begins_after_slow_launch_preparation() {
        let mut guard = LaunchGuard::default();
        let now = Instant::now();
        let time = Cell::new(now);
        assert_eq!(
            guard.start(
                || time.get(),
                || false,
                || {
                    time.set(now + Duration::from_secs(60));
                    Ok(())
                }
            ),
            Ok(true)
        );
        assert_eq!(
            guard.start(
                || now + Duration::from_secs(61),
                || false,
                || panic!("the first game is still booting")
            ),
            Ok(false)
        );
    }
}
