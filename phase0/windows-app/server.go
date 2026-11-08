package main

import (
	"crypto/rand"
	"crypto/subtle"
	_ "embed"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"syscall"
)

//go:embed panel.html
var panelHTML string

// 8765 is the Linux edition's panel; WSL forwards it to Windows, so the Windows edition uses its own port.
const port = 8770

var (
	errInUse = errors.New("port in use")
	fileOK   = regexp.MustCompile(`^[A-Za-z0-9_][A-Za-z0-9._ -]{0,99}$`)
)

const maxUpload = 4 << 30

func loadToken(path string) (string, error) {
	if b, err := os.ReadFile(path); err == nil && len(strings.TrimSpace(string(b))) >= 32 {
		return strings.TrimSpace(string(b)), nil
	}
	raw := make([]byte, 24)
	if _, err := rand.Read(raw); err != nil {
		return "", err
	}
	t := base64.RawURLEncoding.EncodeToString(raw)
	return t, os.WriteFile(path, []byte(t+"\n"), 0o600)
}

func listen() (net.Listener, error) {
	l, err := net.Listen("tcp", fmt.Sprintf("127.0.0.1:%d", port))
	if err != nil {
		var se *os.SyscallError
		if errors.As(err, &se) && errors.Is(se.Err, syscall.Errno(10048)) { // WSAEADDRINUSE
			return nil, errInUse
		}
		if strings.Contains(err.Error(), "address already in use") || strings.Contains(err.Error(), "Only one usage") {
			return nil, errInUse
		}
	}
	return l, err
}

type api struct{ token string }

func (a *api) authorised(r *http.Request) bool {
	host := r.Host
	if h, _, err := net.SplitHostPort(r.Host); err == nil {
		host = h
	}
	if host != "127.0.0.1" && host != "localhost" { // blocks DNS rebinding
		return false
	}
	given := r.Header.Get("X-DL-Token")
	if given == "" {
		given = r.URL.Query().Get("t")
	}
	return subtle.ConstantTimeCompare([]byte(given), []byte(a.token)) == 1
}

func reply(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	w.WriteHeader(code)
	json.NewEncoder(w).Encode(v)
}

func fail(w http.ResponseWriter, err error) {
	reply(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
}

func (a *api) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if !a.authorised(r) {
		reply(w, http.StatusForbidden, map[string]string{"error": "forbidden"})
		return
	}
	switch {
	case r.Method == http.MethodGet && r.URL.Path == "/":
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("Content-Security-Policy", "default-src 'self' 'unsafe-inline'; connect-src 'self'")
		io.WriteString(w, strings.ReplaceAll(panelHTML, "__TOKEN__", a.token))
	case r.Method == http.MethodGet && r.URL.Path == "/api/instances":
		setup.Lock()
		st := map[string]any{"done": setup.done, "step": setup.step, "error": setup.err}
		setup.Unlock()
		reply(w, http.StatusOK, map[string]any{"setup": st, "instances": list(), "version": version})
	case r.Method == http.MethodPost && r.URL.Path == "/api/upload":
		a.upload(w, r)
	case r.Method == http.MethodPost:
		a.action(w, r)
	default:
		reply(w, http.StatusNotFound, map[string]string{"error": "not found"})
	}
}

func (a *api) action(w http.ResponseWriter, r *http.Request) {
	var d struct {
		Name  string `json:"name"`
		RAM   int    `json:"ram"`
		CPUs  int    `json:"cpus"`
		Disk  int    `json:"disk"`
		Res   string `json:"res"`
		DPI   int    `json:"dpi"`
		Start bool   `json:"start"`
	}
	if err := json.NewDecoder(io.LimitReader(r.Body, 10000)).Decode(&d); err != nil {
		fail(w, errors.New("bad request body"))
		return
	}
	setup.Lock()
	ready := setup.done
	setup.Unlock()
	if !ready && r.URL.Path != "/api/open-shared" {
		fail(w, errors.New("still installing the engine; wait until the page says ready"))
		return
	}
	if r.URL.Path == "/api/create" {
		in := &Instance{Name: d.Name, RAM: d.RAM, CPUs: d.CPUs, Disk: d.Disk, Res: d.Res, DPI: d.DPI}
		if err := create(in); err != nil {
			fail(w, err)
			return
		}
		if d.Start {
			if err := start(in); err != nil {
				fail(w, err)
				return
			}
		}
		reply(w, http.StatusOK, map[string]any{"ok": true})
		return
	}
	if r.URL.Path == "/api/open-shared" {
		exec.Command("explorer.exe", dir("shared")).Start()
		reply(w, http.StatusOK, map[string]any{"ok": true})
		return
	}
	in, err := load(d.Name)
	if err != nil {
		fail(w, err)
		return
	}
	var msg string
	switch r.URL.Path {
	case "/api/start":
		err = start(in)
	case "/api/stop":
		go stop(in)
	case "/api/delete":
		err = remove(in)
	case "/api/sync-shared":
		if !running(in) {
			err = errors.New("start the instance first")
		} else {
			msg, err = syncShared(in)
		}
	default:
		reply(w, http.StatusNotFound, map[string]string{"error": "not found"})
		return
	}
	if err != nil {
		fail(w, err)
		return
	}
	reply(w, http.StatusOK, map[string]any{"ok": true, "result": msg})
}

// upload: raw body. action=install installs an APK; action=shared saves the file into shared\ and copies it into Android.
func (a *api) upload(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	in, err := load(q.Get("name"))
	if err != nil {
		fail(w, err)
		return
	}
	fname, action := q.Get("file"), q.Get("action")
	if !fileOK.MatchString(fname) || strings.Contains(fname, "..") {
		fail(w, errors.New("file name: letters, digits, space and . _ - only (max 100)"))
		return
	}
	if (action != "install" && action != "shared") || (action == "install" && !strings.HasSuffix(strings.ToLower(fname), ".apk")) {
		fail(w, errors.New("action must be install (.apk) or shared"))
		return
	}
	if r.ContentLength <= 0 || r.ContentLength > maxUpload {
		fail(w, errors.New("file must be 1 byte to 4 GB"))
		return
	}
	if !running(in) {
		fail(w, errors.New("start the instance first"))
		return
	}
	target := filepath.Join(dir("shared"), fname)
	if action == "install" {
		os.MkdirAll(dir("downloads", "uploads"), 0o755)
		target = filepath.Join(dir("downloads", "uploads"), fname)
	}
	f, err := os.Create(target)
	if err != nil {
		fail(w, err)
		return
	}
	_, err = io.Copy(f, io.LimitReader(r.Body, r.ContentLength))
	f.Close()
	if err != nil {
		os.Remove(target)
		fail(w, errors.New("upload interrupted"))
		return
	}
	var msg string
	if action == "install" {
		msg, err = installAPK(in, target)
		os.Remove(target)
	} else {
		msg, err = syncShared(in)
	}
	if err != nil {
		fail(w, err)
		return
	}
	reply(w, http.StatusOK, map[string]any{"ok": true, "result": msg})
}

func serve(l net.Listener, token string) error {
	return (&http.Server{Handler: &api{token: token}}).Serve(l)
}
