@echo off
rem DragonLord launcher (WSL2 engine). Starts the manager inside WSL and opens it in your browser.
rem Close this window to stop the manager (running emulators keep running until stopped in the UI).
set DISTRO=Ubuntu-24.04
for /f "usebackq tokens=*" %%i in (`wsl.exe -d %DISTRO% -e sh -c "echo $HOME"`) do set WSLHOME=%%i
wsl.exe -d %DISTRO% -e python3 "%WSLHOME%/DragonLord/DragonLord-Emulator/phase0/tools/dlui.py" --open
