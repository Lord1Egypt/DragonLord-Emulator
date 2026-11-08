package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

type Instance struct {
	Name   string `json:"name"`
	Number int    `json:"number"`
	RAM    int    `json:"ram"`
	CPUs   int    `json:"cpus"`
	Disk   int    `json:"disk"`
	Res    string `json:"res"`
	DPI    int    `json:"dpi"`
	Image  string `json:"image"`
	Root   bool   `json:"root"`
	// Profile only records which preset the form used (light, balanced, power); the values themselves are stored above.
	Profile string `json:"profile"`
	// filled in for the panel
	Running bool   `json:"running"`
	Busy    string `json:"busy,omitempty"`
	// Progress and Phase describe a start, stop or clone in progress (an estimate from elapsed time and what this
	// instance needed last time; the emulator reports no percentage)
	Progress int    `json:"progress"`
	Phase    string `json:"phase,omitempty"`
	Adb      string `json:"adb"`
	Gapps    bool   `json:"gapps"`
}

var (
	nameOK = regexp.MustCompile(`^[A-Za-z0-9_-]{1,32}$`)
	resOK  = regexp.MustCompile(`^(\d{3,4})x(\d{3,4})$`)
	mu     sync.Mutex
	busy   = map[string]string{}
	since  = map[string]time.Time{}
)

func avdDir(name string) string { return dir("instances", name+".avd") }
func consolePort(n int) int     { return 5554 + 2*(n-1) }
func serial(n int) string       { return fmt.Sprintf("emulator-%d", consolePort(n)) }
func adbExe() string            { return dir("engine", "platform-tools", "adb.exe") }

// Our own adb server port: WSL forwards localhost:5037 to its own adb server, which cannot see Windows emulators.
const adbPort = "5038"

func emuEnv() []string {
	return append(os.Environ(), "ANDROID_SDK_ROOT="+dir("engine"), "ANDROID_HOME="+dir("engine"),
		"ANDROID_AVD_HOME="+dir("instances"), "ANDROID_EMULATOR_HOME="+dir("home"), "ANDROID_USER_HOME="+dir("home"),
		"ANDROID_ADB_SERVER_PORT="+adbPort)
}

func adb(args ...string) (string, error) { return adbTimeout(60*time.Second, args...) }

// adbTimeout bounds an adb call: a hung adb server must never block the panel.
func adbTimeout(d time.Duration, args ...string) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), d)
	defer cancel()
	cmd := hide(exec.CommandContext(ctx, adbExe(), args...))
	cmd.Env = emuEnv()
	out, err := cmd.CombinedOutput()
	return strings.TrimSpace(string(out)), err
}

func load(name string) (*Instance, error) {
	if !nameOK.MatchString(name) {
		return nil, errors.New("instance name: 1-32 letters, digits, - or _")
	}
	b, err := os.ReadFile(filepath.Join(avdDir(name), "dragonlord.json"))
	if err != nil {
		return nil, fmt.Errorf("no such instance: %s", name)
	}
	var in Instance
	if err := json.Unmarshal(b, &in); err != nil {
		return nil, err
	}
	return &in, nil
}

func running(in *Instance) bool {
	c, err := net.DialTimeout("tcp", fmt.Sprintf("127.0.0.1:%d", consolePort(in.Number)), 300*time.Millisecond)
	if err != nil {
		return false
	}
	c.Close()
	return true
}

func list() []*Instance {
	paths, _ := filepath.Glob(dir("instances", "*.avd", "dragonlord.json"))
	var out []*Instance
	for _, p := range paths {
		name := strings.TrimSuffix(filepath.Base(filepath.Dir(p)), ".avd")
		if in, err := load(name); err == nil {
			if in.Image == "" {
				in.Image = "play" // instances made by 0.1.x
			}
			in.Running, in.Adb, in.Gapps = running(in), serial(in.Number), images[in.Image].playstore
			mu.Lock()
			in.Busy = busy[name]
			t0 := since[name]
			mu.Unlock()
			if in.Busy != "" {
				in.Progress, in.Phase = progress(in, t0)
			}
			out = append(out, in)
		}
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Name < out[j].Name })
	return out
}

// writeAVD writes a new instance's emulator definition.
func writeAVD(in *Instance) error {
	im := images[in.Image]
	m := resOK.FindStringSubmatch(in.Res)
	w, _ := strconv.Atoi(m[1])
	h, _ := strconv.Atoi(m[2])
	orient := "portrait"
	if w > h {
		orient = "landscape"
	}
	cfg := strings.Join([]string{
		"AvdId=" + in.Name, "avd.ini.displayname=" + in.Name, "avd.ini.encoding=UTF-8",
		fmt.Sprintf("PlayStore.enabled=%t", im.playstore), "abi.type=x86_64", "hw.cpu.arch=x86_64",
		fmt.Sprintf("hw.cpu.ncore=%d", in.CPUs), fmt.Sprintf("hw.ramSize=%d", in.RAM), "vm.heapSize=512",
		fmt.Sprintf("disk.dataPartition.size=%dM", in.Disk),
		"image.sysdir.1=" + im.rel, "tag.id=" + im.tag, "tag.display=" + im.tagDisplay,
		"hw.gpu.enabled=yes", "hw.gpu.mode=host",
		fmt.Sprintf("hw.lcd.width=%d", w), fmt.Sprintf("hw.lcd.height=%d", h), fmt.Sprintf("hw.lcd.density=%d", in.DPI),
		"hw.initialOrientation=" + orient, "hw.keyboard=yes", "hw.mainKeys=no", "hw.accelerometer=yes",
		"hw.audioInput=no", "hw.camera.back=none", "hw.camera.front=none", "showDeviceFrame=no",
		"fastboot.forceColdBoot=no", "",
	}, "\r\n")
	if err := os.WriteFile(filepath.Join(avdDir(in.Name), "config.ini"), []byte(cfg), 0o644); err != nil {
		return err
	}
	return writeIni(in)
}

// writeIni points the emulator at the instance folder. It holds an absolute path, so it is rewritten on every start
// (the folder may have moved to another drive). config.ini is left alone after creation: the emulator adds its own
// keys to it, and rewriting it makes the emulator discard its quick-boot snapshot ("different AVD configuration").
func writeIni(in *Instance) error {
	ini := "avd.ini.encoding=UTF-8\r\npath=" + avdDir(in.Name) + "\r\ntarget=android-36\r\n"
	return os.WriteFile(dir("instances", in.Name+".ini"), []byte(ini), 0o644)
}

func create(in *Instance) error {
	if !nameOK.MatchString(in.Name) {
		return errors.New("instance name: 1-32 letters, digits, - or _")
	}
	if in.RAM < 2048 || in.RAM > 16384 || in.CPUs < 1 || in.CPUs > 16 || in.Disk < 6144 || in.Disk > 262144 || in.DPI < 120 || in.DPI > 640 {
		return errors.New("limits: RAM 2048-16384 MB, CPU 1-16, drive 6144-262144 MB (the emulator raises smaller data disks to 6 GB), density 120-640")
	}
	if m := resOK.FindStringSubmatch(in.Res); m == nil {
		return errors.New("screen must look like 1280x800")
	}
	if in.Image == "" {
		in.Image = defaultImage
	}
	if _, ok := images[in.Image]; !ok {
		return errors.New("unknown image")
	}
	if in.Root && images[in.Image].playstore {
		return errors.New("root needs the Light image (the Google Play image is a locked build)")
	}
	if in.Profile != "light" && in.Profile != "balanced" && in.Profile != "power" {
		in.Profile = "light"
	}
	mu.Lock()
	defer mu.Unlock()
	if _, err := os.Stat(avdDir(in.Name)); err == nil {
		return fmt.Errorf("instance exists: %s", in.Name)
	}
	used := map[int]bool{}
	paths, _ := filepath.Glob(dir("instances", "*.avd", "dragonlord.json"))
	for _, p := range paths { // read the files directly: list() takes the same lock
		if o, err := load(strings.TrimSuffix(filepath.Base(filepath.Dir(p)), ".avd")); err == nil {
			used[o.Number] = true
		}
	}
	for n := 1; n <= 16; n++ {
		if !used[n] {
			in.Number = n
			break
		}
	}
	if in.Number == 0 {
		return errors.New("at most 16 instances")
	}
	if err := os.MkdirAll(avdDir(in.Name), 0o755); err != nil {
		return err
	}
	b, _ := json.MarshalIndent(Instance{Name: in.Name, Number: in.Number, RAM: in.RAM, CPUs: in.CPUs, Disk: in.Disk, Res: in.Res, DPI: in.DPI, Image: in.Image, Profile: in.Profile, Root: in.Root}, "", "  ")
	if err := os.WriteFile(filepath.Join(avdDir(in.Name), "dragonlord.json"), b, 0o644); err != nil {
		return err
	}
	return writeAVD(in)
}

func setBusy(name, state string) bool {
	mu.Lock()
	defer mu.Unlock()
	if state != "" && busy[name] != "" && !(busy[name] == "starting" && state == "stopping") {
		return false
	}
	if state == "" {
		delete(busy, name)
		delete(since, name)
	} else {
		if busy[name] != state {
			since[name] = time.Now()
		}
		busy[name] = state
	}
	return true
}

func start(in *Instance) error {
	if running(in) {
		return errors.New("already running")
	}
	if !waitReleased(in, 90*time.Second) {
		return errors.New("the previous run of this instance is still shutting down; try again in a moment")
	}
	if in.Image == "" {
		in.Image = "play"
	}
	if !ensureImage(in.Image) {
		return errors.New("the " + images[in.Image].label + " image is still downloading; wait for the progress bar to finish")
	}
	if err := writeIni(in); err != nil {
		return err
	}
	if !setBusy(in.Name, "starting") {
		return fmt.Errorf("%s is busy", in.Name)
	}
	log, err := os.Create(filepath.Join(avdDir(in.Name), "emulator-log.txt"))
	if err != nil {
		setBusy(in.Name, "")
		return err
	}
	args := []string{"-avd", in.Name, "-port", strconv.Itoa(consolePort(in.Number)),
		"-gpu", "host", "-accel", "on", "-no-boot-anim", "-netdelay", "none", "-netspeed", "full"}
	if in.Profile == "light" {
		args = append(args, "-no-audio") // measured: idle CPU 23% -> 14% and 130 MB less RAM per instance
	}
	args = append(args, strings.Fields(os.Getenv("DRAGONLORD_EMU_ARGS"))...) // benchmarking only
	cmd := hide(exec.Command(dir("engine", "emulator", "emulator.exe"), args...))
	cmd.Env, cmd.Stdout, cmd.Stderr = emuEnv(), log, log
	if err := cmd.Start(); err != nil {
		log.Close()
		setBusy(in.Name, "")
		return err
	}
	go retitle(in)
	go func() {
		defer log.Close()
		done := make(chan struct{})
		go func() { cmd.Wait(); close(done) }()
		logPath := filepath.Join(avdDir(in.Name), "emulator-log.txt")
		deadline := time.Now().Add(15 * time.Minute)
		for time.Now().Before(deadline) {
			select {
			case <-done:
				setBusy(in.Name, "")
				return
			case <-time.After(1500 * time.Millisecond):
			}
			// booted = the emulator says so in its log, or the guest says so over adb (either one is enough)
			b, _ := os.ReadFile(logPath)
			// a restored quick-boot snapshot never prints the cold-boot line; the VM is running as soon as it is loaded
			up := strings.Contains(string(b), "Boot completed in") || strings.Contains(string(b), "Successfully loaded snapshot")
			if !up {
				out, _ := adbTimeout(4*time.Second, "-s", serial(in.Number), "shell", "getprop", "sys.boot_completed")
				up = out == "1"
			}
			if up {
				if in.Root && !images[in.Image].playstore {
					adb("-s", serial(in.Number), "root") // the AOSP image is a debug build: adbd can restart as root
				}
				break
			}
		}
		setBusy(in.Name, "")
		<-done
	}()
	return nil
}

// waitReleased blocks until the emulator process of this instance has really exited: the console port closes a moment
// earlier, and starting again (or deleting files) in that gap fails because its lock files still exist. Locks that
// outlive the process by 30 s belong to a killed run and are removed.
func waitReleased(in *Instance, max time.Duration) bool {
	end := time.Now().Add(max)
	for running(in) {
		if time.Now().After(end) {
			return false
		}
		time.Sleep(500 * time.Millisecond)
	}
	pattern := filepath.Join(avdDir(in.Name), "*.lock")
	for i := 0; i < 60; i++ {
		if locks, _ := filepath.Glob(pattern); len(locks) == 0 {
			return true
		}
		time.Sleep(500 * time.Millisecond)
	}
	locks, _ := filepath.Glob(pattern)
	for _, l := range locks {
		os.RemoveAll(l)
	}
	return true
}

func stop(in *Instance) error {
	if !running(in) {
		return nil
	}
	setBusy(in.Name, "stopping")
	defer setBusy(in.Name, "")
	adb("-s", serial(in.Number), "emu", "kill")
	for i := 0; i < 60 && running(in); i++ {
		time.Sleep(time.Second)
	}
	if running(in) {
		return errors.New("emulator did not stop; close its window")
	}
	waitReleased(in, 90*time.Second) // the snapshot is written before the process exits
	return nil
}

func remove(in *Instance) error {
	if err := stop(in); err != nil {
		return err
	}
	os.Remove(dir("instances", in.Name+".ini"))
	// the emulator's processes keep their files open for a few seconds after the console port closes
	var err error
	for i := 0; i < 30; i++ {
		if err = os.RemoveAll(avdDir(in.Name)); err == nil {
			return nil
		}
		time.Sleep(time.Second)
	}
	return err
}

func installAPK(in *Instance, path string) (string, error) {
	out, err := adb("-s", serial(in.Number), "install", "-r", path)
	if err != nil || !strings.Contains(out, "Success") {
		return out, fmt.Errorf("install failed: %s", lastLine(out))
	}
	return "installed", nil
}

func syncShared(in *Instance) (string, error) {
	out, err := adb("-s", serial(in.Number), "push", dir("shared")+`\.`, "/sdcard/Shared/")
	if err != nil {
		return out, fmt.Errorf("copy failed: %s", lastLine(out))
	}
	return lastLine(out), nil
}

func lastLine(s string) string {
	lines := strings.Split(strings.TrimSpace(s), "\n")
	return strings.TrimSpace(lines[len(lines)-1])
}

// copyTree copies a directory, skipping lock files and logs. Files are copied one at a time (instances are several GB).
func copyTree(src, dst string) error {
	return filepath.Walk(src, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		rel, _ := filepath.Rel(src, path)
		target := filepath.Join(dst, rel)
		name := info.Name()
		if info.IsDir() {
			if strings.HasSuffix(name, ".lock") {
				return filepath.SkipDir
			}
			return os.MkdirAll(target, 0o755)
		}
		if strings.HasSuffix(name, ".lock") || name == "emulator-log.txt" {
			return nil
		}
		in, err := os.Open(path)
		if err != nil {
			return err
		}
		defer in.Close()
		out, err := os.Create(target)
		if err != nil {
			return err
		}
		_, err = io.Copy(out, in)
		if cerr := out.Close(); err == nil {
			err = cerr
		}
		return err
	})
}

// retarget points a copied or renamed instance folder at its new name. The emulator rewrites config.ini itself (it
// raises the data partition to its minimum, for one) and records the instance name and absolute paths in every
// snapshot's hardware.ini; any other difference makes it discard the quick-boot snapshot as "different AVD
// configuration". So the existing files are edited in place instead of being regenerated.
func retarget(d, oldName, newName string) error {
	oldRe := regexp.MustCompile(`(?i)\\instances\\` + regexp.QuoteMeta(oldName) + `\.avd\\`)
	edit := func(path string, f func(string) string) error {
		b, err := os.ReadFile(path)
		if err != nil {
			if os.IsNotExist(err) {
				return nil
			}
			return err
		}
		return os.WriteFile(path, []byte(f(string(b))), 0o644)
	}
	nameLines := func(t string) string {
		for _, k := range []string{"AvdId", "avd.ini.displayname", "avd.id", "avd.name"} {
			t = regexp.MustCompile(`(?m)^`+regexp.QuoteMeta(k)+`(\s*=\s*)`+regexp.QuoteMeta(oldName)+`(\r?)$`).ReplaceAllString(t, k+"${1}"+newName+"${2}")
		}
		return oldRe.ReplaceAllLiteralString(t, `\instances\`+newName+`.avd\`)
	}
	if err := edit(filepath.Join(d, "config.ini"), nameLines); err != nil {
		return err
	}
	snaps, _ := filepath.Glob(filepath.Join(d, "snapshots", "*", "hardware.ini"))
	for _, h := range snaps {
		if err := edit(h, nameLines); err != nil {
			return err
		}
	}
	return nil
}

// clone makes a full copy of a stopped instance, including its quick-boot snapshot, under a new name.
func clone(src *Instance, newName string) error {
	if !nameOK.MatchString(newName) {
		return errors.New("instance name: 1-32 letters, digits, - or _")
	}
	if running(src) || busyState(src.Name) != "" {
		return errors.New("stop the instance first")
	}
	if !setBusy(newName, "cloning") {
		return errors.New("that name is in use")
	}
	defer setBusy(newName, "")
	if _, err := os.Stat(avdDir(newName)); err == nil {
		return fmt.Errorf("instance exists: %s", newName)
	}
	used := map[int]bool{}
	paths, _ := filepath.Glob(dir("instances", "*.avd", "dragonlord.json"))
	for _, p := range paths {
		if o, err := load(strings.TrimSuffix(filepath.Base(filepath.Dir(p)), ".avd")); err == nil {
			used[o.Number] = true
		}
	}
	number := 0
	for n := 1; n <= 16 && number == 0; n++ {
		if !used[n] {
			number = n
		}
	}
	if number == 0 {
		return errors.New("at most 16 instances")
	}
	// Copy into a temporary folder and move it into place only when complete: a half-copied instance (carrying a copy
	// of the source's dragonlord.json) must never show up in the list or be startable.
	tmp := avdDir(newName) + ".tmp"
	os.RemoveAll(tmp)
	if err := copyTree(avdDir(src.Name), tmp); err != nil {
		os.RemoveAll(tmp)
		return err
	}
	n := *src
	n.Name, n.Number = newName, number
	b, _ := json.MarshalIndent(Instance{Name: n.Name, Number: n.Number, RAM: n.RAM, CPUs: n.CPUs, Disk: n.Disk, Res: n.Res, DPI: n.DPI,
		Image: n.Image, Profile: n.Profile, Root: n.Root}, "", "  ")
	if err := os.WriteFile(filepath.Join(tmp, "dragonlord.json"), b, 0o644); err != nil {
		os.RemoveAll(tmp)
		return err
	}
	if err := retarget(tmp, src.Name, newName); err != nil {
		os.RemoveAll(tmp)
		return err
	}
	if err := os.Rename(tmp, avdDir(newName)); err != nil {
		os.RemoveAll(tmp)
		return err
	}
	return writeIni(&n)
}

func busyState(name string) string {
	mu.Lock()
	defer mu.Unlock()
	return busy[name]
}

// rename moves a stopped instance to a new name.
func rename(in *Instance, newName string) error {
	if !nameOK.MatchString(newName) {
		return errors.New("instance name: 1-32 letters, digits, - or _")
	}
	if running(in) || busyState(in.Name) != "" {
		return errors.New("stop the instance first")
	}
	if _, err := os.Stat(avdDir(newName)); err == nil {
		return fmt.Errorf("instance exists: %s", newName)
	}
	if err := os.Rename(avdDir(in.Name), avdDir(newName)); err != nil {
		return err
	}
	os.Remove(dir("instances", in.Name+".ini"))
	n := *in
	n.Name = newName
	b, _ := json.MarshalIndent(Instance{Name: n.Name, Number: n.Number, RAM: n.RAM, CPUs: n.CPUs, Disk: n.Disk, Res: n.Res, DPI: n.DPI,
		Image: n.Image, Profile: n.Profile, Root: n.Root}, "", "  ")
	if err := os.WriteFile(filepath.Join(avdDir(newName), "dragonlord.json"), b, 0o644); err != nil {
		return err
	}
	if err := retarget(avdDir(newName), in.Name, newName); err != nil {
		return err
	}
	return writeIni(&n)
}

// progress estimates how far a start, stop or clone is. A restore from a snapshot takes about 10 s, a cold boot about
// 110 s (measured on the owner's PC), so the bar is elapsed time against that, never reaching 100 until it is done.
func progress(in *Instance, t0 time.Time) (int, string) {
	el := time.Since(t0).Seconds()
	expect, phase := 12.0, "Restoring the saved state"
	switch in.Busy {
	case "starting":
		if _, err := os.Stat(filepath.Join(avdDir(in.Name), "snapshots", "default_boot", "snapshot.pb")); err != nil {
			expect, phase = 110, "Starting Android for the first time (about two minutes)"
		}
	case "stopping":
		expect, phase = 10, "Saving the state"
	case "cloning":
		expect, phase = 30, "Copying the emulator"
	}
	p := int(el / expect * 95)
	if p > 95 {
		p = 95
	}
	return p, phase
}

// updateSettings changes screen, density, memory and cores of a stopped instance. The emulator discards its saved
// state when the hardware description changes, so the snapshot is removed and the next start is a cold boot.
func updateSettings(in *Instance, ram, cpus int, res string, dpi int) error {
	if running(in) || busyState(in.Name) != "" {
		return errors.New("stop the instance first")
	}
	m := resOK.FindStringSubmatch(res)
	if m == nil || ram < 2048 || ram > 16384 || cpus < 1 || cpus > 16 || dpi < 120 || dpi > 640 {
		return errors.New("limits: RAM 2048-16384 MB, CPU 1-16, density 120-640, screen like 1280x800")
	}
	w, _ := strconv.Atoi(m[1])
	h, _ := strconv.Atoi(m[2])
	orient := "portrait"
	if w > h {
		orient = "landscape"
	}
	path := filepath.Join(avdDir(in.Name), "config.ini")
	b, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	t := string(b)
	set := func(k, v string) {
		re := regexp.MustCompile(`(?m)^` + regexp.QuoteMeta(k) + `\s*=.*$`)
		if re.MatchString(t) {
			t = re.ReplaceAllLiteralString(t, k+"="+v)
		} else {
			t += k + "=" + v + "\r\n"
		}
	}
	set("hw.ramSize", strconv.Itoa(ram))
	set("hw.cpu.ncore", strconv.Itoa(cpus))
	set("hw.lcd.width", strconv.Itoa(w))
	set("hw.lcd.height", strconv.Itoa(h))
	set("hw.lcd.density", strconv.Itoa(dpi))
	set("hw.initialOrientation", orient)
	if err := os.WriteFile(path, []byte(t), 0o644); err != nil {
		return err
	}
	os.RemoveAll(filepath.Join(avdDir(in.Name), "snapshots"))
	n := *in
	n.RAM, n.CPUs, n.Res, n.DPI = ram, cpus, res, dpi
	jb, _ := json.MarshalIndent(Instance{Name: n.Name, Number: n.Number, RAM: n.RAM, CPUs: n.CPUs, Disk: n.Disk, Res: n.Res, DPI: n.DPI,
		Image: n.Image, Profile: n.Profile, Root: n.Root}, "", "  ")
	return os.WriteFile(filepath.Join(avdDir(in.Name), "dragonlord.json"), jb, 0o644)
}
