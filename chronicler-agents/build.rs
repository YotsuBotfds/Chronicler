//! Compiler capabilities the crate adapts to.
//!
//! `chronicler_avx512`: the compiler has the stable `avx512f` target feature
//! (Rust 1.89 or later), so the AVX-512 drift kernel is built
//! (`spatial::DriftKernel`). The crate's `rust-version` stays at its
//! dependencies' floor; an older compiler builds the AVX2 and portable
//! kernels only, which give the same results.

use std::process::Command;

fn main() {
    println!("cargo::rerun-if-changed=build.rs");
    println!("cargo::rerun-if-env-changed=RUSTC");
    println!("cargo::rustc-check-cfg=cfg(chronicler_avx512)");
    let rustc = std::env::var("RUSTC").unwrap_or_else(|_| "rustc".to_string());
    let version = Command::new(rustc)
        .arg("--version")
        .output()
        .ok()
        .and_then(|out| String::from_utf8(out.stdout).ok())
        .unwrap_or_default();
    // "rustc 1.97.0 (2d8144b78 2026-07-07)" or "rustc 1.90.0-nightly (...)"
    let mut parts = version
        .split_whitespace()
        .nth(1)
        .unwrap_or("")
        .split(|c: char| !c.is_ascii_digit())
        .map(|p| p.parse::<u32>().unwrap_or(0));
    let (major, minor) = (parts.next().unwrap_or(0), parts.next().unwrap_or(0));
    if (major, minor) >= (1, 89) {
        println!("cargo::rustc-cfg=chronicler_avx512");
    }
}
