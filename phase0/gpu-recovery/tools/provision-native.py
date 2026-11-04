#!/usr/bin/env python3
"""Prepare an isolated short native Windows directory from verified official archives.

Runs in WSL. No installer, registry/global PATH, driver or OS feature changes.
Requires the pinned downloads and a verified LLVM signature, recorded separately.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import zstandard
from importlib.util import spec_from_file_location, module_from_spec

PACKAGE = Path(__file__).resolve().parents[1]
PHASE = PACKAGE.parent
WORK = PHASE / ".work/gpu-recovery"
DOWNLOADS = WORK / "downloads"
LLVM = "clang+llvm-23.1.5-x86_64-pc-windows-msvc"
RUST = "rust-1.88.0-x86_64-pc-windows-msvc"
ARCHIVES = {
    LLVM + ".tar.zst": "b2be33385ddc86e83511417a060de927ae8b09d1f3017cc3cdce5c73cd5029d7",
    RUST + ".tar.xz": "4c5bafcfbb25a2a3b21cb5934d18c70d370b504b518c0119fda51aee7887e7c2",
}


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def archive_source(source, pin, archive, target):
    if subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip() != pin:
        raise ValueError("Source pin mismatch")
    if subprocess.check_output(["git", "-C", str(source), "diff", "HEAD", "--name-only"], text=True).strip():
        raise ValueError("Source modified")
    subprocess.run(["git", "-C", str(source), "archive", "--format=tar", "--output", str(archive.resolve()), pin], check=True)
    target.mkdir(parents=True)
    with tarfile.open(archive) as t:
        # The WSL CI symlink is unrelated to compilation and native Git cannot
        # represent it consistently. Record that single omission in provenance.
        members = [m for m in t if m.name != ".kokoro/continuous.cfg"]
        t.extractall(target, members=members, filter="data")
    return {"commit": pin, "archive_sha256": digest(archive), "native_path": str(target),
            "nonbuild_ci_symlink_omitted": source.name.startswith("gfxstream")}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--destination", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.destination.exists() or args.output.exists():
        p.error("fresh destination and output directory required")
    args.output.mkdir(parents=True)
    result = {"scope": "Isolated tool/source extraction; native compilation and GPU NOT TESTED", "status": "FAIL"}
    try:
        for name, expected in ARCHIVES.items():
            if digest(DOWNLOADS / name) != expected:
                raise ValueError("Archive checksum mismatch: " + name)
        spec = spec_from_file_location("toolchain_verifier", PACKAGE / "tools/fetch-toolchains.py")
        verifier = module_from_spec(spec)
        spec.loader.exec_module(verifier)
        verifier.verify(DOWNLOADS)
        root = args.destination
        root.mkdir(parents=True)
        tools = root / "tools"
        tools.mkdir()
        with (DOWNLOADS / (LLVM + ".tar.zst")).open("rb") as f:
            # Official archive uses a 1 GiB Zstd window; default decoder limit is lower.
            with zstandard.ZstdDecompressor(max_window_size=2**31).stream_reader(f) as reader:
                with tarfile.open(fileobj=reader, mode="r|") as t:
                    for m in t:
                        parts = Path(m.name).parts
                        if len(parts) > 1 and (parts[1] == "bin" or parts[1:3] == ("lib", "clang")):
                            t.extract(m, tools, filter="data")
        rust = tools / "rust-1.88.0"
        rust.mkdir()
        with tarfile.open(DOWNLOADS / (RUST + ".tar.xz")) as t:
            for m in t:
                parts = Path(m.name).parts
                if len(parts) < 4 or parts[1] not in ("rustc", "cargo", "rust-std-x86_64-pc-windows-msvc"):
                    continue
                relative = Path(*parts[2:])
                target = rust / relative
                if not target.resolve().is_relative_to(rust.resolve()):
                    raise ValueError("Archive path escapes destination")
                if m.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif m.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with t.extractfile(m) as src, target.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
        sources = []
        for source, pin, relative in [
            (PHASE / ".work/gfxstream-gpu-feasibility", "94240f814c0097a63027ae680ea4bec7b0cb25f7", "src/hardware/google/gfxstream"),
            (WORK / "googletest", "52eb8108c5bdec04579160ae17225d66034bd723", "src/external/googletest"),
            (PHASE / ".work/rutabaga-gpu-feasibility", "4f2bcaf71a6497583362ed664d9fe21cc5043049", "src/rutabaga"),
        ]:
            sources.append(archive_source(source, pin, WORK / (source.name + ".tar"), root / relative))
        binaries = []
        for file in [tools / LLVM / "bin/clang-cl.exe", tools / LLVM / "bin/lld-link.exe", rust / "bin/rustc.exe", rust / "bin/cargo.exe"]:
            if not file.exists():
                raise ValueError("Expected tool not extracted: " + str(file))
            binaries.append({"path": str(file), "sha256": digest(file)})
        result.update(status="PASS", binaries=binaries, sources=sources, archives=ARCHIVES,
                      reason="Verified official archive subsets and pinned source archives extracted; no system installation")
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as exc:
        result["reason"] = str(exc)
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
