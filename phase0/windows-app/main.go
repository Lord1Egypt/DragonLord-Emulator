// DragonLord for Windows: one portable exe. Everything it needs is created next to it:
//
//	engine\      Google's Android Emulator, platform-tools and the Android system images (downloaded when first needed)
//	instances\   one emulator definition (AVD) per instance
//	shared\      files here are copied into each instance's /sdcard/Shared on request
//	downloads\   verified downloads (kept so a reinstall does not download again)
//	data\        panel access token and dragonlord.log
//
// No WSL, no installer, no registry: the folder can live on any drive or a USB stick.
package main

import (
	"archive/zip"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
)

const version = "0.2.0-preview"

type pkg struct {
	name, url, sha256, into string
	mb                      int
}

// Pinned downloads (Google's SDK repository; SHA-256 computed from copies verified against Google's published SHA-1).
var basePkgs = []pkg{
	{"emulator-windows_x64-16740729.zip", "https://dl.google.com/android/repository/emulator-windows_x64-16740729.zip",
		"625276a1d3ac6b15d00f8aad5e233e7dc3a7cb71435f97d64e3be298399e171d", "engine", 434},
	{"platform-tools_r37.0.2-win.zip", "https://dl.google.com/android/repository/platform-tools_r37.0.2-win.zip",
		"6d93a5e63bc1654b70b7b94bec5c6ab46db113df0265beb314055dd253772b58", "engine", 8},
}

// An Android image an instance can use. "light" is the AOSP build without Google services: less than half the size,
// far less to start at boot. "play" is the full Google Play build.
type imageDef struct {
	key, label, tag, tagDisplay string
	parent, rel                 string // where it unpacks under engine\, and the sysdir written into the AVD
	playstore                   bool
	p                           pkg
}

var images = map[string]imageDef{
	"light": {"light", "Light (Android 16, no Google services)", "default", "Default Android System Image",
		`engine\system-images\android-36\default`, `system-images\android-36\default\x86_64\`, false,
		pkg{"x86_64-36_r02-default.zip", "https://dl.google.com/android/repository/sys-img/android/x86_64-36_r02.zip",
			"e1b9d9fb665001ef27b16e57d8762a2d54aec6bff617e17506edb8676667b9da", `engine\system-images\android-36\default`, 805}},
	"play": {"play", "Google Play (Android 16)", "google_apis_playstore", "Google Play",
		`engine\system-images\android-36-ext19\google_apis_playstore`, `system-images\android-36-ext19\google_apis_playstore\x86_64\`, true,
		pkg{"x86_64-36-ext19_r01.zip", "https://dl.google.com/android/repository/sys-img/google_apis_playstore/x86_64-36-ext19_r01.zip",
			"4792903fcb289751f29b64adb611656eec1b5cb11de599ea086e59607b572112", `engine\system-images\android-36-ext19\google_apis_playstore`, 1838}},
}

const defaultImage = "light"

var base string // folder of the exe

func dir(parts ...string) string { return filepath.Join(append([]string{base}, parts...)...) }

// setup state, shown by the panel as a progress bar while engine or images download
var setup = struct {
	sync.Mutex
	jobs  int // running installs
	step  string
	pct   int
	err   string
	ready bool // engine installed
}{}

func setStep(pct int, format string, a ...any) {
	setup.Lock()
	setup.step, setup.pct = fmt.Sprintf(format, a...), pct
	setup.Unlock()
	log.Print(fmt.Sprintf(format, a...))
}

func fileSHA256(path string) (string, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()
	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}

type progressWriter struct {
	name        string
	total, done int64
	last        int64
	span        [2]int // overall percent range this download covers
}

func (p *progressWriter) Write(b []byte) (int, error) {
	p.done += int64(len(b))
	if p.total > 0 && p.done*50/p.total != p.last {
		p.last = p.done * 50 / p.total
		setStep(p.span[0]+int(int64(p.span[1]-p.span[0])*p.done/p.total), "Downloading %s (%d of %d MB)", p.name, p.done>>20, p.total>>20)
	}
	return len(b), nil
}

func fetch(d pkg, span [2]int) (string, error) {
	dst := dir("downloads", d.name)
	if got, err := fileSHA256(dst); err == nil && got == d.sha256 {
		return dst, nil
	}
	if err := os.MkdirAll(dir("downloads"), 0o755); err != nil {
		return "", err
	}
	resp, err := http.Get(d.url)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("%s: HTTP %s", d.name, resp.Status)
	}
	part := dst + ".part"
	f, err := os.Create(part)
	if err != nil {
		return "", err
	}
	h := sha256.New()
	_, err = io.Copy(io.MultiWriter(f, h, &progressWriter{name: d.name, total: resp.ContentLength, span: span}), resp.Body)
	f.Close()
	if err != nil {
		os.Remove(part)
		return "", err
	}
	if hex.EncodeToString(h.Sum(nil)) != d.sha256 {
		os.Remove(part)
		return "", fmt.Errorf("%s: SHA-256 mismatch, download refused", d.name)
	}
	return dst, os.Rename(part, dst)
}

// unzip extracts into dst, refusing entries that would land outside it.
func unzip(src, dst string) error {
	r, err := zip.OpenReader(src)
	if err != nil {
		return err
	}
	defer r.Close()
	root, _ := filepath.Abs(dst)
	for _, f := range r.File {
		target := filepath.Join(root, filepath.FromSlash(f.Name))
		if target != root && !strings.HasPrefix(target, root+string(os.PathSeparator)) {
			return fmt.Errorf("%s: unsafe path %q", src, f.Name)
		}
		if f.FileInfo().IsDir() {
			if err := os.MkdirAll(target, 0o755); err != nil {
				return err
			}
			continue
		}
		if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
			return err
		}
		in, err := f.Open()
		if err != nil {
			return err
		}
		out, err := os.Create(target)
		if err != nil {
			in.Close()
			return err
		}
		_, err = io.Copy(out, in)
		in.Close()
		if cerr := out.Close(); err == nil {
			err = cerr
		}
		if err != nil {
			return err
		}
	}
	return nil
}

func imageReady(key string) bool {
	_, err := os.Stat(filepath.Join(dir(images[key].parent), ".dragonlord-ok"))
	return err == nil
}

// install downloads and unpacks packages with one overall progress bar. marker is written when everything is in place.
func install(pkgs []pkg, marker string) {
	setup.Lock()
	setup.jobs++
	setup.err = ""
	setup.Unlock()
	defer func() { setup.Lock(); setup.jobs--; setup.Unlock() }()
	total := 0
	for _, p := range pkgs {
		total += p.mb
	}
	done := 0
	for _, p := range pkgs {
		lo, hi := done*95/total, (done+p.mb)*95/total
		path, err := fetch(p, [2]int{lo, hi})
		if err != nil {
			failSetup(err)
			return
		}
		setStep(hi, "Unpacking %s", p.name)
		if err := unzip(path, dir(p.into)); err != nil {
			failSetup(err)
			return
		}
		done += p.mb
	}
	if err := os.WriteFile(marker, []byte(version+"\n"), 0o644); err != nil {
		failSetup(err)
		return
	}
	setStep(100, "Ready")
}

func runSetup() {
	for _, d := range []string{"instances", "shared", "home", "data", "downloads"} {
		os.MkdirAll(dir(d), 0o755)
	}
	if _, err := os.Stat(dir("engine", ".dragonlord-installed")); err != nil {
		install(basePkgs, dir("engine", ".dragonlord-installed"))
	}
	if _, err := os.Stat(dir("engine", ".dragonlord-installed")); err == nil {
		setup.Lock()
		setup.ready = true
		setup.Unlock()
	}
	ensureImage(defaultImage)
}

// ensureImage starts the download of an image if it is missing and reports whether it is usable now.
func ensureImage(key string) bool {
	if imageReady(key) {
		return true
	}
	setup.Lock()
	busy := setup.jobs > 0
	setup.Unlock()
	if !busy {
		im := images[key]
		go install([]pkg{im.p}, filepath.Join(dir(im.parent), ".dragonlord-ok"))
	}
	return false
}

func failSetup(err error) {
	setup.Lock()
	setup.err = err.Error()
	setup.Unlock()
	log.Print("setup failed: ", err)
}

func openBrowser(url string) {
	exec.Command("rundll32", "url.dll,FileProtocolHandler", url).Start()
}

func main() {
	exe, err := os.Executable()
	if err != nil {
		os.Exit(1)
	}
	base = filepath.Dir(exe)
	os.MkdirAll(dir("data"), 0o755)
	if f, err := os.OpenFile(dir("data", "dragonlord.log"), os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644); err == nil {
		log.SetOutput(f) // built as a Windows GUI program: no console, everything goes to the log file
	}
	log.SetFlags(log.LstdFlags)
	log.Printf("DragonLord %s starting in %s", version, base)
	token, err := loadToken(dir("data", "ui-token"))
	if err != nil {
		log.Fatal(err)
	}
	url := fmt.Sprintf("http://127.0.0.1:%d/?t=%s", port, token)
	srv, err := listen()
	if errors.Is(err, errInUse) {
		openBrowser(url) // already running: just show it again
		return
	} else if err != nil {
		log.Fatal(err)
	}
	go runSetup()
	openBrowser(url)
	log.Fatal(serve(srv, token))
}
