package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
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
	Adb     string `json:"adb"`
	Gapps   bool   `json:"gapps"`
}

var (
	nameOK = regexp.MustCompile(`^[A-Za-z0-9_-]{1,32}$`)
	resOK  = regexp.MustCompile(`^(\d{3,4})x(\d{3,4})$`)
	mu     sync.Mutex
	busy   = map[string]string{}
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
	cmd := exec.CommandContext(ctx, adbExe(), args...)
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
			mu.Unlock()
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
	if in.RAM < 2048 || in.RAM > 16384 || in.CPUs < 1 || in.CPUs > 16 || in.Disk < 2048 || in.Disk > 262144 || in.DPI < 120 || in.DPI > 640 {
		return errors.New("limits: RAM 2048-16384 MB, CPU 1-16, drive 2048-262144 MB, density 120-640")
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
	} else {
		busy[name] = state
	}
	return true
}

func start(in *Instance) error {
	if running(in) {
		return errors.New("already running")
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
	args = append(args, strings.Fields(os.Getenv("DRAGONLORD_EMU_ARGS"))...) // benchmarking only
	cmd := exec.Command(dir("engine", "emulator", "emulator.exe"), args...)
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
			up := strings.Contains(string(b), "Boot completed in")
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
