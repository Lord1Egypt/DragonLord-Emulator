package main

import (
	"fmt"
	"syscall"
	"time"
	"unsafe"
)

var (
	user32        = syscall.NewLazyDLL("user32.dll")
	findWindow    = user32.NewProc("FindWindowW")
	setWindowText = user32.NewProc("SetWindowTextW")
)

// retitle renames the emulator's window from "Android Emulator - NAME:PORT" to "DragonLord - NAME" once it appears.
// The emulator may set its title again while starting, so it keeps watching for a few minutes.
func retitle(in *Instance) {
	from, err := syscall.UTF16PtrFromString(fmt.Sprintf("Android Emulator - %s:%d", in.Name, consolePort(in.Number)))
	if err != nil {
		return
	}
	to, err := syscall.UTF16PtrFromString("DragonLord - " + in.Name)
	if err != nil {
		return
	}
	for end := time.Now().Add(5 * time.Minute); time.Now().Before(end); time.Sleep(2 * time.Second) {
		if hwnd, _, _ := findWindow.Call(0, uintptr(unsafe.Pointer(from))); hwnd != 0 {
			setWindowText.Call(hwnd, uintptr(unsafe.Pointer(to)))
		}
	}
}
