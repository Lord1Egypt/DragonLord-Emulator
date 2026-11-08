@echo off
rem DragonLord launcher (WSL2 engine). Starts the manager inside WSL and opens it in your browser.
rem The manager keeps running inside WSL after this window closes; double-click again to reopen the page.
rem Emulators keep running until stopped in the panel.
set DISTRO=Ubuntu-24.04
for /f "usebackq tokens=*" %%i in (`wsl.exe -d %DISTRO% -e sh -c "echo $HOME"`) do set WSLHOME=%%i
wsl.exe -d %DISTRO% -e python3 "%WSLHOME%/DragonLord/DragonLord-Emulator/phase0/tools/dlui.py" --open
