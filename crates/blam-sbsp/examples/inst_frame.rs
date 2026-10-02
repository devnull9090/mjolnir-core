//! Print instances' frames, boxes and definitions.
//!
//!   cargo run -p blam-sbsp --example inst_frame -- <payload> <instance>...
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&a[0]).expect("read");
    for s in &a[1..] {
        let i: usize = s.parse().unwrap();
        let (e, _) = blam_sbsp::transplant::donor_element(&file, "instanced geometry instances", i)
            .expect("instance");
        let f = |o: usize| f32::from_le_bytes(e[o..o + 4].try_into().unwrap());
        println!(
            "instance {i}: def {} scale {:.3} fwd ({:.3},{:.3},{:.3}) left ({:.3},{:.3},{:.3}) up ({:.3},{:.3},{:.3}) pos ({:.2},{:.2},{:.2}) box x[{:.1},{:.1}] y[{:.1},{:.1}] z[{:.1},{:.1}]",
            i16::from_le_bytes([e[52], e[53]]), f(0), f(4), f(8), f(12), f(16), f(20), f(24), f(28), f(32), f(36), f(40), f(44), f(48),
            f(76), f(80), f(84), f(88), f(92), f(96)
        );
    }
}
