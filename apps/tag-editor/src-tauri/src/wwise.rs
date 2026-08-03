//! Recovering readable names for Wwise media.
//!
//! Wwise names its media by numeric short ID, so a browser over the `.pak`
//! archives can only show `1000519664.wem`. The readable names are in the
//! IoStore side: each cooked `UAkAudioEvent` package carries, in its name map,
//! the event's own name, the `Media/<bucket>/<id>.wem` paths it plays, and the
//! original `.wav` source paths the sound designer authored.
//!
//! Pairing an individual media ID to an individual `.wav` needs the export
//! blob, which is not parsed. Naming a media file by the event that plays it
//! is enough to make the list readable, and is what this builds.

use std::collections::HashMap;

/// One named Wwise event and the source files behind it.
#[derive(Debug)]
pub struct Event {
    /// e.g. `Play_AMB_ENV_A15_ComputerBeeps_A`.
    pub name: String,
    /// Package path, for opening the event asset itself.
    pub package: String,
    /// Original authored sources, e.g.
    /// `Environment\A15\Positionals\AMB_ENV_A15_ComputerBeeps_A_01.wav`.
    pub sources: Vec<String>,
}

/// Media short ID to the events that play it.
#[derive(Debug, Default)]
pub struct NameIndex {
    pub events: Vec<Event>,
    by_media: HashMap<u32, Vec<u32>>,
}

impl NameIndex {
    /// Events that play one media file, most specific first.
    pub fn events_for(&self, media_id: u32) -> impl Iterator<Item = &Event> {
        self.by_media
            .get(&media_id)
            .map(|v| v.as_slice())
            .unwrap_or(&[])
            .iter()
            .filter_map(|i| self.events.get(*i as usize))
    }

    /// A single display label for one media file: the event that plays it, or
    /// `None` when nothing claims it.
    pub fn label_for(&self, media_id: u32) -> Option<&str> {
        // The shortest name, ties broken alphabetically, so a media file that
        // several events share gets one stable label rather than pak order.
        self.events_for(media_id)
            .min_by_key(|e| (e.name.len(), &e.name))
            .map(|e| e.name.as_str())
    }

    pub fn media_named(&self) -> usize {
        self.by_media.len()
    }

    /// Fold one package's name map into the index.
    ///
    /// `package_path` is the full cooked path; its stem is the event name.
    /// Returns true when the package actually referenced media.
    pub fn add_package(&mut self, package_path: &str, names: &[String]) -> bool {
        let media: Vec<u32> = names.iter().filter_map(|n| media_id(n)).collect();
        if media.is_empty() {
            return false;
        }
        let stem = package_path
            .rsplit('/')
            .next()
            .unwrap_or(package_path)
            .trim_end_matches(".uasset");
        // The event name is in the name map too; prefer that spelling, falling
        // back to the file stem if the map does not repeat it.
        let name = names
            .iter()
            .find(|n| n.as_str() == stem)
            .cloned()
            .unwrap_or_else(|| stem.to_string());
        let sources: Vec<String> = names
            .iter()
            .filter(|n| n.to_ascii_lowercase().ends_with(".wav"))
            .cloned()
            .collect();

        let at = self.events.len() as u32;
        self.events.push(Event {
            name,
            package: package_path.to_string(),
            sources,
        });
        for id in media {
            self.by_media.entry(id).or_default().push(at);
        }
        true
    }
}

/// The numeric short ID of a `Media/<bucket>/<id>.wem` name-map entry.
fn media_id(name: &str) -> Option<u32> {
    let rest = name.strip_prefix("Media/")?;
    let file = rest.rsplit('/').next()?;
    file.strip_suffix(".wem")?.parse().ok()
}

/// The short ID a `.wem` path in the sound catalog refers to.
pub fn media_id_of_path(short: &str) -> Option<u32> {
    let file = short.rsplit('/').next()?;
    file.strip_suffix(".wem")?.parse().ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn names(v: &[&str]) -> Vec<String> {
        v.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn media_ids_come_from_the_media_paths_only() {
        assert_eq!(media_id("Media/10/1060715316.wem"), Some(1_060_715_316));
        assert_eq!(media_id("Media/8/17154256.wem"), Some(17_154_256));
        // Everything else in the name map must be ignored.
        assert_eq!(media_id("2581487812.bnk"), None);
        assert_eq!(media_id("Environment\\A15\\Beeps_01.wav"), None);
        assert_eq!(media_id("Play_AMB_ENV_A15_ComputerBeeps_A"), None);
        assert_eq!(media_id("Media/10/notanumber.wem"), None);
    }

    #[test]
    fn a_package_names_every_media_it_references() {
        let mut idx = NameIndex::default();
        let added = idx.add_package(
            "/Game/Audio/Ambience/WwiseEvents/Play_Beeps_A.uasset",
            &names(&[
                "2581487812.bnk",
                "Environment\\A15\\Beeps_A_01.wav",
                "Environment\\A15\\Beeps_A_02.wav",
                "Media/10/1060715316.wem",
                "Media/11/118025064.wem",
                "Play_Beeps_A",
                "SFX",
            ]),
        );
        assert!(added);
        assert_eq!(idx.label_for(1_060_715_316), Some("Play_Beeps_A"));
        assert_eq!(idx.label_for(118_025_064), Some("Play_Beeps_A"));
        assert_eq!(idx.label_for(999), None);
        assert_eq!(idx.media_named(), 2);
        assert_eq!(idx.events[0].sources.len(), 2);
    }

    #[test]
    fn a_package_with_no_media_is_not_indexed() {
        let mut idx = NameIndex::default();
        assert!(!idx.add_package("/Game/Audio/Foo.uasset", &names(&["Foo", "SFX"])));
        assert!(idx.events.is_empty());
    }

    #[test]
    fn the_event_name_falls_back_to_the_file_stem() {
        let mut idx = NameIndex::default();
        idx.add_package(
            "/Game/Audio/WwiseEvents/Play_Only_In_Path.uasset",
            &names(&["Media/1/5.wem"]),
        );
        assert_eq!(idx.label_for(5), Some("Play_Only_In_Path"));
    }

    #[test]
    fn the_shortest_event_wins_when_several_play_one_media() {
        let mut idx = NameIndex::default();
        idx.add_package(
            "/Game/Audio/WwiseEvents/Play_Weapon_Fire_Single_Long.uasset",
            &names(&["Media/1/42.wem"]),
        );
        idx.add_package(
            "/Game/Audio/WwiseEvents/Play_Weapon_Fire.uasset",
            &names(&["Media/1/42.wem"]),
        );
        assert_eq!(idx.label_for(42), Some("Play_Weapon_Fire"));
        assert_eq!(idx.events_for(42).count(), 2);
    }

    #[test]
    fn a_catalog_path_yields_its_short_id() {
        assert_eq!(
            media_id_of_path("Media/English(US)/12/100018565.wem"),
            Some(100_018_565)
        );
        assert_eq!(media_id_of_path("Italian/1005569379.bnk"), None);
    }
}
