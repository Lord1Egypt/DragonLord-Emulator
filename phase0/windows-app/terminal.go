package main

import (
	"bufio"
	"crypto/sha1"
	_ "embed"
	"encoding/base64"
	"encoding/binary"
	"fmt"
	"io"
	"net/http"
	"os/exec"
	"strconv"
	"strings"
	"sync"
)

//go:embed assets/xterm.js
var xtermJS []byte

//go:embed assets/xterm.css
var xtermCSS []byte

//go:embed terminal.html
var terminalHTML string

const wsGUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

// wsFrame writes one unfragmented server frame (servers never mask).
func wsFrame(w io.Writer, op byte, data []byte) error {
	head := []byte{0x80 | op}
	switch n := len(data); {
	case n < 126:
		head = append(head, byte(n))
	case n < 65536:
		head = append(head, 126, byte(n>>8), byte(n))
	default:
		head = append(head, 127, 0, 0, 0, 0, byte(n>>24), byte(n>>16), byte(n>>8), byte(n))
	}
	_, err := w.Write(append(head, data...))
	return err
}

// wsRead reads one client frame (always masked) and returns its opcode and payload.
func wsRead(r *bufio.Reader) (byte, []byte, error) {
	h := make([]byte, 2)
	if _, err := io.ReadFull(r, h); err != nil {
		return 0, nil, err
	}
	op, n := h[0]&0x0f, uint64(h[1]&0x7f)
	switch n {
	case 126:
		b := make([]byte, 2)
		if _, err := io.ReadFull(r, b); err != nil {
			return 0, nil, err
		}
		n = uint64(binary.BigEndian.Uint16(b))
	case 127:
		b := make([]byte, 8)
		if _, err := io.ReadFull(r, b); err != nil {
			return 0, nil, err
		}
		n = binary.BigEndian.Uint64(b)
	}
	if h[1]&0x80 == 0 || n > 1<<20 {
		return 0, nil, fmt.Errorf("bad websocket frame")
	}
	mask := make([]byte, 4)
	if _, err := io.ReadFull(r, mask); err != nil {
		return 0, nil, err
	}
	data := make([]byte, n)
	if _, err := io.ReadFull(r, data); err != nil {
		return 0, nil, err
	}
	for i := range data {
		data[i] ^= mask[i%4]
	}
	return op, data, nil
}

// terminal: a WebSocket to `adb shell -tt` of a running instance (the pty lives on the device side, so plain pipes work
// on Windows). Origin must be our own page, so another website cannot drive a shell with a leaked token.
func (a *api) terminal(w http.ResponseWriter, r *http.Request) {
	in, err := load(r.URL.Query().Get("name"))
	if err != nil {
		fail(w, err)
		return
	}
	origin := r.Header.Get("Origin")
	if origin != fmt.Sprintf("http://127.0.0.1:%d", port) && origin != fmt.Sprintf("http://localhost:%d", port) {
		reply(w, http.StatusForbidden, map[string]string{"error": "bad origin"})
		return
	}
	key := r.Header.Get("Sec-WebSocket-Key")
	if !strings.EqualFold(r.Header.Get("Upgrade"), "websocket") || key == "" || !running(in) {
		fail(w, fmt.Errorf("websocket upgrade to a running instance required"))
		return
	}
	cols, _ := strconv.Atoi(r.URL.Query().Get("cols"))
	rows, _ := strconv.Atoi(r.URL.Query().Get("rows"))
	hj, ok := w.(http.Hijacker)
	if !ok {
		fail(w, fmt.Errorf("no hijack"))
		return
	}
	conn, rw, err := hj.Hijack()
	if err != nil {
		return
	}
	defer conn.Close()
	sum := sha1.Sum([]byte(key + wsGUID))
	fmt.Fprintf(rw, "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: %s\r\n\r\n",
		base64.StdEncoding.EncodeToString(sum[:]))
	rw.Flush()

	cmd := hide(exec.Command(adbExe(), "-s", serial(in.Number), "shell", "-tt"))
	cmd.Env = emuEnv()
	stdin, _ := cmd.StdinPipe()
	stdout, _ := cmd.StdoutPipe()
	cmd.Stderr = cmd.Stdout
	if err := cmd.Start(); err != nil {
		return
	}
	defer func() { cmd.Process.Kill(); cmd.Wait() }()
	if cols >= 20 && cols <= 400 && rows >= 5 && rows <= 200 {
		fmt.Fprintf(stdin, "stty cols %d rows %d\n", cols, rows)
	}
	var mu sync.Mutex
	go func() {
		buf := make([]byte, 16384)
		for {
			n, err := stdout.Read(buf)
			if n > 0 {
				mu.Lock()
				werr := wsFrame(conn, 2, buf[:n])
				mu.Unlock()
				if werr != nil {
					return
				}
			}
			if err != nil {
				conn.Close()
				return
			}
		}
	}()
	for {
		op, data, err := wsRead(rw.Reader)
		if err != nil || op == 8 {
			return
		}
		switch op {
		case 9:
			mu.Lock()
			wsFrame(conn, 10, data)
			mu.Unlock()
		case 0, 1, 2:
			if _, err := stdin.Write(data); err != nil {
				return
			}
		}
	}
}
