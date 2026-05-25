# Windows Packaging

WiX Toolset v6/v7 MSI installer that registers ONVIFy as a native Windows Service.

## Prerequisites

- WiX Toolset v6 or v7 (`dotnet tool install --global wix`)
- PyInstaller (`pip install -e ".[packaging]"`)

## Build

```powershell
# Bundle the Python app
.\packaging\windows\build-exe.ps1 -Clean

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
