//! Widen an instance group's broadphase sphere so a transplanted instance can
//! be reached anywhere its new geometry extends.
//!
//!   cargo run -p blam-sbsp --example widen_group -- <payload> <out> <group> <cx> <cy> <cz> <radius>
use blam_sbsp::transplant::set_scalar;

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let mut file = std::fs::read(&a[0]).expect("read");
    let group: usize = a[2].parse().expect("group");
    let p = format!("instance group to instance spheres[{group}]");
    for (path, value) in [
        (format!("{p}.center"), format!("({}, {}, {})", a[3], a[4], a[5])),
        (format!("{p}.radius"), a[6].clone()),
    ] {
        file = set_scalar(&file, &path, &value).unwrap_or_else(|e| panic!("{path}: {e}"));
        println!("  set {path} = {value}");
    }
    std::fs::write(&a[1], &file).expect("write");
    println!("  wrote {}", a[1]);
}
