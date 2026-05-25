# Windows Packaging

WiX Toolset v6/v7 MSI installer that registers ONVIFy as a native Windows Service.

## Prerequisites

- WiX Toolset v6 or v7 (`dotnet tool install --global wix`)
- PyInstaller (to bundle Python app into standalone exe)

## Build

```powershell
# Bundle the Python app
pyinstaller --onefile --name onvify src/onvify/cli.py

# Build the MSI
wix build packaging/windows/onvify.wxs -d ProductVersion=0.1.0 -o ONVIFy.msi
```

## Service Registration

The MSI uses WiX `ServiceInstall` and `ServiceControl` elements to register
ONVIFy as a proper native Windows Service — no NSSM or third-party wrappers.

The service:
- Starts automatically on boot
- Runs under NetworkService by default
- Supports standard `sc.exe` management (start, stop, query)
- Logs to Windows Event Log

Override `SERVICEACCOUNT` at install time only for built-in or managed service
accounts that do not require an MSI-supplied password.
