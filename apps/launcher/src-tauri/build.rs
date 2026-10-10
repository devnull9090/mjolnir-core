fn main() {
    // The unit tests' binary has no application manifest (tauri-build gives
    // its resource to the app's exe alone), so Windows loads the system's
    // Common Controls v5, which lacks TaskDialogIndirect (the dialog plugin
    // imports it), and the tests die before they start (0xc0000139).
    // Delay-loading the DLL leaves the import unresolved until a dialog
    // opens, which no test does. Debug builds only: the shipped exe links as
    // it always has.
    if std::env::var("CARGO_CFG_TARGET_ENV").as_deref() == Ok("msvc")
        && std::env::var("PROFILE").as_deref() == Ok("debug")
    {
        println!("cargo:rustc-link-arg=/DELAYLOAD:comctl32.dll");
        println!("cargo:rustc-link-lib=delayimp");
    }
    tauri_build::build()
}
