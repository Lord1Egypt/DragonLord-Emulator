package main

import (
	"os/exec"
	"syscall"
)

// createNoWindow keeps console programs (adb, the emulator launcher) from opening a black console window each time
// they are started from this window-less program.
const createNoWindow = 0x08000000

func hide(cmd *exec.Cmd) *exec.Cmd {
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: createNoWindow}
	return cmd
}
