// DragonLord for Windows: one portable exe. Everything it needs is created next to it:
//
//	engine\      Google's Android Emulator, platform-tools and the Android system image (downloaded on first run)
//	instances\   one emulator definition (AVD) per instance
//	shared\      files here are copied into each instance's /sdcard/Shared on request
//	downloads\   verified downloads (kept so a reinstall does not download again)
//	data\        panel access token
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
	"time"
)

const version = "0.1.1-preview"

// Pinned downloads (Google's SDK repository; SHA-256 computed from copies verified against Google's published SHA-1).
var downloads = []struct {
	name, url, sha256, into string
}{
	{"emulator-windows_x64-16740729.zip", "https://dl.google.com/android/repository/emulator-windows_x64-16740729.zip",
		"625276a1d3ac6b15d00f8aad5e233e7dc3a7cb71435f97d64e3be298399e171d", "engine"},
	{"platform-tools_r37.0.2-win.zip", "https://dl.google.com/android/repository/platform-tools_r37.0.2-win.zip",
		"6d93a5e63bc1654b70b7b94bec5c6ab46db113df0265beb314055dd253772b58", "engine"},
	{"x86_64-36-ext19_r01.zip", "https://dl.google.com/android/repository/sys-img/google_apis_playstore/x86_64-36-ext19_r01.zip",
		"4792903fcb289751f29b64adb611656eec1b5cb11de599ea086e59607b572112", sysImageParent},
}

const sysImageParent = `engine\system-images\android-36-ext19\google_apis_playstore`
const sysImageRel = `system-images\android-36-ext19\google_apis_playstore\x86_64\`

var base string // folder of the exe

func dir(parts ...string) string { return filepath.Join(append([]string{base}, parts...)...) }

// setup state, shown by the panel while the first run downloads
var setup = struct {
	sync.Mutex
	done bool
	step string
	err  string
}{}

func setStep(format string, a ...any) {
	setup.Lock()
	setup.step = fmt.Sprintf(format, a...)
	setup.Unlock()
	log.Print(setup.step)
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
}

func (p *progressWriter) Write(b []byte) (int, error) {
	p.done += int64(len(b))
	if p.total > 0 && p.done*20/p.total != p.last {
		p.last = p.done * 20 / p.total
		setStep("downloading %s: %d%% of %d MB", p.name, p.done*100/p.total, p.total>>20)
	}
	return len(b), nil
}

func fetch(name, url, want string) (string, error) {
	dst := dir("downloads", name)
	if got, err := fileSHA256(dst); err == nil && got == want {
		return dst, nil
	}
	if err := os.MkdirAll(dir("downloads"), 0o755); err != nil {
		return "", err
	}
	resp, err := http.Get(url)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("%s: HTTP %s", name, resp.Status)
	}
	part := dst + ".part"
	f, err := os.Create(part)
	if err != nil {
		return "", err
	}
	h := sha256.New()
	_, err = io.Copy(io.MultiWriter(f, h, &progressWriter{name: name, total: resp.ContentLength}), resp.Body)
	f.Close()
	if err != nil {
		os.Remove(part)
		return "", err
	}
	if hex.EncodeToString(h.Sum(nil)) != want {
		os.Remove(part)
		return "", fmt.Errorf("%s: SHA-256 mismatch, download refused", name)
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

func runSetup() {
	marker := dir("engine", ".dragonlord-installed")
	if _, err := os.Stat(marker); err != nil {
		for _, d := range downloads {
			path, err := fetch(d.name, d.url, d.sha256)
			if err != nil {
				failSetup(err)
				return
			}
			setStep("unpacking %s", d.name)
			if err := unzip(path, dir(d.into)); err != nil {
				failSetup(err)
				return
			}
		}
		if err := os.WriteFile(marker, []byte(version+"\n"), 0o644); err != nil {
			failSetup(err)
			return
		}
	}
	for _, d := range []string{"instances", "shared", "home", "data"} {
		os.MkdirAll(dir(d), 0o755)
	}
	setup.Lock()
	setup.done, setup.step = true, "ready"
	setup.Unlock()
	log.Print("engine ready")
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
		log.Fatal(err)
	}
	base = filepath.Dir(exe)
	log.SetFlags(log.Ltime)
	fmt.Printf("DragonLord %s for Windows\nfolder: %s\n", version, base)
	os.MkdirAll(dir("data"), 0o755)
	token, err := loadToken(dir("data", "ui-token"))
	if err != nil {
		log.Fatal(err)
	}
	url := fmt.Sprintf("http://127.0.0.1:%d/?t=%s", port, token)
	srv, err := listen()
	if errors.Is(err, errInUse) {
		fmt.Println("DragonLord is already running; opening its page")
		openBrowser(url)
		time.Sleep(time.Second)
		return
	} else if err != nil {
		log.Fatal(err)
	}
	go runSetup()
	fmt.Println("panel:", url)
	fmt.Println("keep this window open while you use DragonLord; closing it stops the panel (running emulators keep running)")
	openBrowser(url)
	log.Fatal(serve(srv, token))
}
