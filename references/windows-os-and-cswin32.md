# Windows OS Interop, CsWin32, Security & Hardware Events (.NET 9/10)

> **Scope:** Modern Win32 interop via `Microsoft.Windows.CsWin32` vs. `[LibraryImport]`, `SafeHandle` and `Lease()` lifetimes, `.NET 8/9/10` Shell pickers (`OpenFileDialog`, `OpenFolderDialog`, WinUI 3 `InitializeWithWindow`), COM `IFileOpenDialog` / `SHGetKnownFolderPath`, Drag-Drop + UIPI, `RegisterHotKey` vs. `WH_KEYBOARD_LL`, DPAPI (`CurrentUser`), Windows Credential Manager (`CredWriteW`/`CredReadW`) vs. `PasswordVault`, UAC/`app.manifest`, Registry `Run` + `StartupApproved` vs. MSIX `StartupTask`, `WM_DEVICECHANGE`, WASAPI/`NAudio` traps, and leak-free `SystemEvents.PowerModeChanged`.
>
> **Related:** Starter `NativeMethods.txt`/`NativeMethods.json` setup is included in [`scaffold_windows_app.py`](../scripts/scaffold_windows_app.py) (`wpf-modern`). See [compiler-traps-and-compat.md](compiler-traps-and-compat.md) for `PInvoke001`/`PInvoke017`/`SYSLIB1062` diagnostics, [security-hardening-and-enterprise.md](security-hardening-and-enterprise.md) for `SetDefaultDllDirectories` DLL-hijack defense, Windows Hello, and TLS/proxy hardening, and [graphics-media-and-windows-ai.md](graphics-media-and-windows-ai.md) for full WASAPI loopback capture and HID/Serial/BLE device recipes.

## Table of Contents

1. [Modern Win32 Interop (`Microsoft.Windows.CsWin32` & `[LibraryImport]`)](#1-modern-win32-interop-microsoftwindowscswin32--libraryimport)
2. [Native Shell Pickers, Known Folders & Drag-and-Drop](#2-native-shell-pickers-known-folders--drag-and-drop)
3. [Global Hotkeys & Low-Level Input Caveats](#3-global-hotkeys--low-level-input-caveats)
4. [Secrets, Credentials, UAC & `app.manifest` Security](#4-secrets-credentials-uac--appmanifest-security)
5. [Hardware, Audio Routing, Startup & Power Events](#5-hardware-audio-routing-startup--power-events)

---

## 1. Modern Win32 Interop (`Microsoft.Windows.CsWin32` & `[LibraryImport]`)

### 1.1 `.csproj`, `NativeMethods.txt` & `NativeMethods.json` Setup

Prefer **`Microsoft.Windows.CsWin32`** over hand-written P/Invokes: it generates exact signatures, structs, enums, and `SafeHandle` wrappers directly from official Win32 metadata (`winmd`).

```xml
<!-- MyApp.csproj (.NET 9/10) -->
<PropertyGroup>
  <TargetFramework>net10.0-windows10.0.19041.0</TargetFramework>
  <AllowUnsafeBlocks>true</AllowUnsafeBlocks>
</PropertyGroup>
<ItemGroup>
  <PackageReference Include="Microsoft.Windows.CsWin32" Version="0.3.371">
    <PrivateAssets>all</PrivateAssets>
    <IncludeAssets>runtime; build; native; contentfiles; analyzers</IncludeAssets>
  </PackageReference>
</ItemGroup>
```

```text
// NativeMethods.txt (exact API / struct / constant / enum names; comments use //, not #)
RegisterHotKey
UnregisterHotKey
WM_HOTKEY
HOT_KEY_MODIFIERS
CredWriteW
CredReadW
CredDeleteW
CredFree
CREDENTIALW
CRED_TYPE
CRED_PERSIST
SHGetKnownFolderPath
CoTaskMemFree
FOLDERID_Documents
IFileOpenDialog
FileOpenDialog
FILEOPENDIALOGOPTIONS
SIGDN
RegisterDeviceNotificationW
UnregisterDeviceNotification
DEV_BROADCAST_HDR
DEV_BROADCAST_DEVICEINTERFACE_W
WM_DEVICECHANGE
DBT_DEVICEARRIVAL
DBT_DEVICEREMOVECOMPLETE
DEV_BROADCAST_HDR_DEVICE_TYPE
REGISTER_NOTIFICATION_FLAGS
```

> **Analyzer Note (`PInvoke004` & `W` Suffixes):** For constants inside Win32 enums (`DBT_DEVTYP_DEVICEINTERFACE`, `DEVICE_NOTIFY_WINDOW_HANDLE`), list the **enum name** (`DEV_BROADCAST_HDR_DEVICE_TYPE`, `REGISTER_NOTIFICATION_FLAGS`) in `NativeMethods.txt` to avoid warning `PInvoke004`. CsWin32 drops the trailing `W` on generated friendly overloads (`CredWriteW` -> `PInvoke.CredWrite`, `RegisterDeviceNotificationW` -> `PInvoke.RegisterDeviceNotification`).

```json
// NativeMethods.json
{
  "$schema": "https://aka.ms/CsWin32.schema.json",
  "allowMarshaling": false,
  "useSafeHandles": true,
  "friendlyOverloads": { "enabled": true },
  "public": false,
  "emitSingleFile": false
}
```

| `NativeMethods.json` Option | Recommended Value | Effect & Trade-Off |
|---|---|---|
| `allowMarshaling` | **`false`** (AOT/modern) or `true` (RCW) | `false` drops runtime COM/marshal stubs (NativeAOT & trim-friendly; COM types generate as `unsafe struct*` vtables instead of `[ComImport]` RCWs). |
| `useSafeHandles` | **`true`** | Returns `SafeHandle` subclasses (`SafeFileHandle`, `CredFreeCREDENTIALWPointerSafeHandle`, `CoTaskMemFreePWSTRSafeHandle`, `UnregisterDeviceNotificationSafeHandle`). |
| `friendlyOverloads` | `{ "enabled": true }` | Emits `string`, `ReadOnlySpan<T>`, `in`/`out`, and `SafeHandle` overloads alongside raw pointer signatures. |
| `public` | `false` (`internal`) | Keeps generated `Windows.Win32.PInvoke` internal; set `true` only for dedicated interop assemblies. |
| `emitSingleFile` | `false` | Splits generated types across files for faster incremental Roslyn builds. |

### 1.2 `SafeHandle` Lifecycle vs. `[LibraryImport]` vs. `[DllImport]`

| Approach | `AllowUnsafeBlocks` Rule | Pros & When to Choose |
|---|---|---|
| **`Microsoft.Windows.CsWin32`** | CsWin32 `.props` sets `<AllowUnsafeBlocks>true</AllowUnsafeBlocks>`; **never** override to `false`. | Default for multi-API Windows apps: zero manual struct layout bugs, automatic `SafeHandle`, `DefaultDllImportSearchPaths(System32)`. |
| **`[LibraryImport]`** (`.NET 7+`) | **Requires `<AllowUnsafeBlocks>true</AllowUnsafeBlocks>`** in `.csproj` (else Roslyn **`SYSLIB1062`**). | Best for 1–3 custom/3rd-party DLL imports without a NuGet package; NativeAOT-safe with blittable types or `MarshalUsing`. |
| **`[DllImport]`** (legacy) | Compiles with `AllowUnsafeBlocks=false`. | Only if unsafe code is banned; relies on slower runtime IL marshaling. |

**`SafeHandle` Rules:** Wrap every CsWin32 `SafeHandle` in `using`. When reading native struct fields (e.g., `CredFreeCREDENTIALWPointerSafeHandle` or `CoTaskMemFreePWSTRSafeHandle`), acquire `using var lease = handle.Lease();` and pass `lease.Value` directly to a helper call (or call `.ToString()`) — **never** save `DangerousValue` or dereference sub-pointers inline (triggers analyzer **`PInvoke017`**).

---

## 2. Native Shell Pickers, Known Folders & Drag-and-Drop

### 2.1 WPF `.NET 8/9/10` Built-In Pickers (`OpenFolderDialog`, `OpenFileDialog`)

Since `.NET 8`, WPF includes **`Microsoft.Win32.OpenFolderDialog`** in `PresentationFramework.dll` (no WinForms or 3rd-party package needed!), supporting multi-folder selection via `Multiselect` + `FolderNames`:

```csharp
using System;
using Microsoft.Win32;

namespace MyApp.Shell;

public static class WpfPickers
{
    public static string[] PickFolders(bool multiselect = true)
    {
        var dialog = new OpenFolderDialog
        {
            Title = "Select Folders",
            Multiselect = multiselect,
            InitialDirectory = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments)
        };
        return dialog.ShowDialog() == true ? dialog.FolderNames : [];
    }

    public static string? PickFile()
    {
        var dialog = new OpenFileDialog
        {
            Title = "Open Project",
            Filter = "Project Files (*.myproj)|*.myproj|All Files (*.*)|*.*",
            CheckFileExists = true
        };
        return dialog.ShowDialog() == true ? dialog.FileName : null;
    }
}
```

### 2.2 WinUI 3 Pickers & COM `IFileOpenDialog` / `SHGetKnownFolderPath`

- **WinUI 3 (`FileOpenPicker` / `FolderPicker`):** Desktop WinUI 3 requires binding the picker to the parent `HWND` via `WinRT.Interop.WindowNative.GetWindowHandle(window)` + `WinRT.Interop.InitializeWithWindow.Initialize(picker, hwnd)`, else Windows throws `COMException (0x80070578)`. *(WinRT pickers fail in elevated Admin processes; Windows App SDK `1.8+` adds `Microsoft.Windows.Storage.Pickers` with `WindowId`.)*
- **Known Folders & Raw COM `IFileOpenDialog` (`CsWin32`):** Use `SHGetKnownFolderPath` for folders missing from `Environment.SpecialFolder` (e.g., `FOLDERID_Downloads`), and `IFileOpenDialog` for custom COM flags (`FOS_PICKFOLDERS`) or elevated processes:

```csharp
using System.Runtime.InteropServices;
using Windows.Win32;
using Windows.Win32.Foundation;
using Windows.Win32.System.Com;
using Windows.Win32.UI.Shell;

namespace MyApp.Shell;

public static unsafe class ShellInterop
{
    public static string GetKnownDocumentsPath()
    {
        HRESULT hr = PInvoke.SHGetKnownFolderPath(in PInvoke.FOLDERID_Documents, KNOWN_FOLDER_FLAG.KF_FLAG_DEFAULT, null, out CoTaskMemFreePWSTRSafeHandle pathHandle);
        hr.ThrowOnFailure();
        using (pathHandle) { return pathHandle.DangerousValue.ToString(); }
    }

    public static string? PickFolderViaCom(nint ownerHwnd)
    {
        // allowMarshaling=false generates unmanaged struct vtable pointers
        PInvoke.CoCreateInstance<IFileOpenDialog>(typeof(FileOpenDialog).GUID, null, CLSCTX.CLSCTX_INPROC_SERVER, out IFileOpenDialog* dialog).ThrowOnFailure();
        try
        {
            dialog->GetOptions(out FILEOPENDIALOGOPTIONS opts);
            dialog->SetOptions(opts | FILEOPENDIALOGOPTIONS.FOS_PICKFOLDERS | FILEOPENDIALOGOPTIONS.FOS_FORCEFILESYSTEM);
            try { dialog->Show(new HWND(ownerHwnd)); }
            catch (COMException ex) when (ex.HResult == unchecked((int)0x800704C7)) { return null; } // ERROR_CANCELLED

            IShellItem* item = null;
            dialog->GetResult(&item);
            if (item is null) return null;
            try
            {
                item->GetDisplayName(SIGDN.SIGDN_FILESYSPATH, out PWSTR pszPath);
                try { return pszPath.ToString(); }
                finally { PInvoke.CoTaskMemFree(pszPath.Value); }
            }
            finally { item->Release(); }
        }
        finally { dialog->Release(); }
    }
}
```

### 2.3 WPF Drag-and-Drop & the UIPI Elevation Pitfall

Set `AllowDrop="True"`, validate `e.Data.GetDataPresent(DataFormats.FileDrop)` in `DragOver` (`e.Effects = DragDropEffects.Copy` or `None`; `e.Handled = true`), and read `(string[]?)e.Data.GetData(DataFormats.FileDrop)` in `Drop`. **UIPI Pitfall:** User Interface Privilege Isolation blocks OLE drag-and-drop from Medium-integrity Explorer into an elevated (`requireAdministrator`) window — keep desktop UIs **`asInvoker`**.

---

## 3. Global Hotkeys & Low-Level Input Caveats

### 3.1 `RegisterHotKey` / `UnregisterHotKey` via `HwndSource` Hook

Use **`RegisterHotKey`** + **`MOD_NOREPEAT` (`0x4000`)** for global shortcuts. Handle collisions (`RegisterHotKey` returns `false`, `Marshal.GetLastWin32Error() == 1409` `ERROR_HOTKEY_ALREADY_REGISTERED`) and always call **`UnregisterHotKey`** on dispose/close. *(Note: `HOT_KEY_MODIFIERS` is `internal` when `NativeMethods.json` sets `"public": false`, so keep the wrapper `internal` or expose a `public` enum.)*

```csharp
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;
using Windows.Win32;
using Windows.Win32.Foundation;
using Windows.Win32.UI.Input.KeyboardAndMouse;

namespace MyApp.Input;

internal sealed class GlobalHotkeyService : IDisposable
{
    private const int ErrorHotkeyAlreadyRegistered = 1409;
    private readonly HwndSource _hwndSource;
    private readonly HWND _hwnd;
    private readonly int _hotkeyId;
    private readonly Action _callback;
    private bool _registered;

    public GlobalHotkeyService(Window ownerWindow, int hotkeyId, HOT_KEY_MODIFIERS modifiers, uint virtualKey, Action callback)
    {
        _hotkeyId = hotkeyId;
        _callback = callback;

        nint handle = new WindowInteropHelper(ownerWindow).EnsureHandle();
        _hwnd = new HWND(handle);
        _hwndSource = HwndSource.FromHwnd(handle) ?? throw new InvalidOperationException("Window HWND unavailable.");
        _hwndSource.AddHook(WndProc);

        if (!PInvoke.RegisterHotKey(_hwnd, _hotkeyId, modifiers | HOT_KEY_MODIFIERS.MOD_NOREPEAT, virtualKey))
        {
            int err = Marshal.GetLastWin32Error();
            _hwndSource.RemoveHook(WndProc);
            if (err == ErrorHotkeyAlreadyRegistered)
                throw new InvalidOperationException("Hotkey is already claimed by another application.");
            throw new Win32Exception(err);
        }
        _registered = true;
    }

    private nint WndProc(nint hwnd, int msg, nint wParam, nint lParam, ref bool handled)
    {
        if (msg == PInvoke.WM_HOTKEY && wParam == _hotkeyId)
        {
            _callback();
            handled = true;
        }
        return nint.Zero;
    }

    public void Dispose()
    {
        if (_registered) { PInvoke.UnregisterHotKey(_hwnd, _hotkeyId); _registered = false; }
        _hwndSource.RemoveHook(WndProc);
    }
}
```

### 3.2 Why `WH_KEYBOARD_LL` (`SetWindowsHookEx`) Breaks in Production

| Failure Mode | Mechanism | Consequence |
|---|---|---|
| **Silent unhook** | Runs synchronously on installer thread; Windows enforces `LowLevelHooksTimeout` (~`300–1000 ms`). | One GC pause or UI stall causes Windows to **silently remove the hook** with no error callback. |
| **AV / EDR flags** | Global `WH_KEYBOARD_LL` triggers keylogger heuristics. | Unsigned/low-reputation binaries risk Microsoft Defender / SmartScreen quarantine. |
| **UAC / UIPI blind spot** | Non-elevated (`asInvoker`) hooks never see keystrokes sent to elevated Admin windows. | Hotkeys silently stop working inside Task Manager or elevated tools. |

---

## 4. Secrets, Credentials, UAC & `app.manifest` Security

### 4.1 Windows DPAPI (`ProtectedData`) — Always `CurrentUser`, Never `LocalMachine`

WPF (`UseWPF=true`) already receives `ProtectedData` from `Microsoft.WindowsDesktop.App` (non-WPF apps reference `System.Security.Cryptography.ProtectedData`). Always pass **`DataProtectionScope.CurrentUser`** + app-specific `optionalEntropy` (and use `Span<byte>` overloads on `.NET 9/10` for zero-copy buffers). **NEVER pass `DataProtectionScope.LocalMachine` for user secrets**: any local user or low-privilege process on the PC can decrypt `LocalMachine` blobs!

```csharp
using System;
using System.Security.Cryptography;
using System.Text;

namespace MyApp.Security;

public static class UserDpapiSecretBox
{
    private static readonly byte[] AppEntropy = "MyApp.TokenVault.v1"u8.ToArray();

    public static byte[] ProtectText(string plaintext)
    {
        byte[] bytes = Encoding.UTF8.GetBytes(plaintext);
        try { return ProtectedData.Protect(bytes, AppEntropy, DataProtectionScope.CurrentUser); }
        finally { CryptographicOperations.ZeroMemory(bytes); }
    }

    public static string UnprotectText(byte[] encryptedBlob)
    {
        byte[] bytes = ProtectedData.Unprotect(encryptedBlob, AppEntropy, DataProtectionScope.CurrentUser);
        try { return Encoding.UTF8.GetString(bytes); }
        finally { CryptographicOperations.ZeroMemory(bytes); }
    }
}
```

### 4.2 Windows Credential Manager (`CsWin32`) vs. WinRT `PasswordVault`

| API | Project Requirement | Size & Behavior Notes |
|---|---|---|
| **Win32 `CredWrite` / `CredRead`** (`CsWin32`) | Any Windows `.NET` TFM | `CredentialBlobSize <= 2560` bytes; `useSafeHandles: true` wraps result in `CredFreeCREDENTIALWPointerSafeHandle`. |
| **WinRT `PasswordVault`** (`Windows.Security.Credentials`) | `net9.0-windows10.0.19041.0`+ TFM | Clean OO API (`Add`, `Retrieve`, `Remove` — must call `cred.RetrievePassword()`). Unpackaged Win32 apps do **not** hit UWP's 20-credential cap. |

```csharp
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using Windows.Win32;
using Windows.Win32.Foundation;
using Windows.Win32.Security.Credentials;

namespace MyApp.Security;

public static unsafe class CredentialVault
{
    public static void SaveGeneric(string targetName, string userName, string secret)
    {
        byte[] blob = Encoding.UTF8.GetBytes(secret);
        try
        {
            fixed (char* pTarget = targetName)
            fixed (char* pUser = userName)
            fixed (byte* pBlob = blob)
            {
                var cred = new CREDENTIALW
                {
                    Type = CRED_TYPE.CRED_TYPE_GENERIC,
                    TargetName = new PWSTR(pTarget),
                    UserName = new PWSTR(pUser),
                    CredentialBlobSize = (uint)blob.Length,
                    CredentialBlob = pBlob,
                    Persist = CRED_PERSIST.CRED_PERSIST_LOCAL_MACHINE
                };
                if (!PInvoke.CredWrite(in cred, 0)) throw new Win32Exception(Marshal.GetLastWin32Error());
            }
        }
        finally { CryptographicOperations.ZeroMemory(blob); }
    }

    public static string? ReadGeneric(string targetName)
    {
        if (!PInvoke.CredRead(targetName, CRED_TYPE.CRED_TYPE_GENERIC, out CredFreeCREDENTIALWPointerSafeHandle handle))
        {
            int err = Marshal.GetLastWin32Error();
            if (err == 1168) return null; // ERROR_NOT_FOUND
            throw new Win32Exception(err);
        }
        using (handle)
        using (var lease = handle.Lease())
        {
            return ReadCredentialBlob(lease.Value); // Pass lease.Value directly to a call (satisfies PInvoke017)
        }
    }

    private static string ReadCredentialBlob(CREDENTIALW* cred) =>
        cred is null || cred->CredentialBlob is null || cred->CredentialBlobSize == 0
            ? string.Empty
            : Encoding.UTF8.GetString(cred->CredentialBlob, (int)cred->CredentialBlobSize);

    public static void DeleteGeneric(string targetName) => _ = PInvoke.CredDelete(targetName, CRED_TYPE.CRED_TYPE_GENERIC);
}
```

### 4.3 UAC & `app.manifest` Security Blueprint

Always default desktop apps to **`level="asInvoker" uiAccess="false"`**:
- **`requireAdministrator`**: triggers UAC prompts, breaks Explorer drag-and-drop (UIPI), and breaks Windows App SDK toasts; move admin work into a dedicated service/helper.
- **`uiAccess="true"`**: assistive UI only; Windows refuses launch (`ERROR_ELEVATION_REQUIRED`) unless Authenticode-signed and installed in `Program Files` or `Windows\System32`.

```xml
<?xml version="1.0" encoding="utf-8"?>
<assembly manifestVersion="1.0" xmlns="urn:schemas-microsoft-com:asm.v1">
  <assemblyIdentity version="1.0.0.0" name="MyCompany.MyApp"/>
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v2">
    <security>
      <requestedPrivileges xmlns="urn:schemas-microsoft-com:asm.v3">
        <requestedExecutionLevel level="asInvoker" uiAccess="false" />
      </requestedPrivileges>
    </security>
  </trustInfo>
  <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1">
    <application>
      <supportedOS Id="{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}" /> <!-- Windows 10 & 11 -->
    </application>
  </compatibility>
  <application xmlns="urn:schemas-microsoft-com:asm.v3">
    <windowsSettings>
      <dpiAware xmlns="http://schemas.microsoft.com/SMI/2005/WindowsSettings">true/pm</dpiAware>
      <dpiAwareness xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">PerMonitorV2</dpiAwareness>
      <longPathAware xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">true</longPathAware>
      <activeCodePage xmlns="http://schemas.microsoft.com/SMI/2019/WindowsSettings">UTF-8</activeCodePage>
    </windowsSettings>
  </application>
</assembly>
```

---

## 5. Hardware, Audio Routing, Startup & Power Events

### 5.1 Startup Registration: Registry `Run` + `StartupApproved` vs. MSIX `StartupTask`

- **Unpackaged (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`):** Always quote the `.exe` path (`"\"C:\Path\MyApp.exe\" --minimized"`) to stop unquoted path-hijacking. Read **`HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run`** (first byte `0x02`/`0x06` = enabled, `0x03`/`0x07` = disabled by user in Task Manager/Settings) before showing startup status — never silently overwrite user-disabled state.
- **Packaged MSIX (`Windows.ApplicationModel.StartupTask`):** Declare `<uap5:StartupTask TaskId="MyAppStartup" Enabled="false" DisplayName="MyApp" />` in `Package.appxmanifest` and call `await (await StartupTask.GetAsync("MyAppStartup")).RequestEnableAsync();`.

### 5.2 Hardware Plug/Unplug (`WM_DEVICECHANGE` & `RegisterDeviceNotification`)

```csharp
using System;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;
using Windows.Win32;
using Windows.Win32.UI.WindowsAndMessaging;

namespace MyApp.Hardware;

public sealed unsafe class UsbDeviceWatcher : IDisposable
{
    private static readonly Guid UsbInterfaceGuid = new("A5DCBF10-6530-11D2-901F-00C04FB951ED");
    private readonly HwndSource _hwndSource;
    private UnregisterDeviceNotificationSafeHandle? _notifyHandle;

    public event Action<bool, string>? DeviceChanged;

    public UsbDeviceWatcher(Window window)
    {
        nint hwnd = new WindowInteropHelper(window).EnsureHandle();
        _hwndSource = HwndSource.FromHwnd(hwnd) ?? throw new InvalidOperationException();
        _hwndSource.AddHook(WndProc);

        var filter = new DEV_BROADCAST_DEVICEINTERFACE_W
        {
            dbcc_size = (uint)sizeof(DEV_BROADCAST_DEVICEINTERFACE_W),
            dbcc_devicetype = (uint)DEV_BROADCAST_HDR_DEVICE_TYPE.DBT_DEVTYP_DEVICEINTERFACE,
            dbcc_classguid = UsbInterfaceGuid
        };
        _notifyHandle = PInvoke.RegisterDeviceNotification(
            new SafeHwndWrapper(hwnd), &filter, REGISTER_NOTIFICATION_FLAGS.DEVICE_NOTIFY_WINDOW_HANDLE);
    }

    private nint WndProc(nint hwnd, int msg, nint wParam, nint lParam, ref bool handled)
    {
        if (msg == PInvoke.WM_DEVICECHANGE && lParam != 0)
        {
            uint evt = (uint)wParam.ToInt64();
            if (evt == PInvoke.DBT_DEVICEARRIVAL || evt == PInvoke.DBT_DEVICEREMOVECOMPLETE)
            {
                DEV_BROADCAST_HDR* hdr = (DEV_BROADCAST_HDR*)lParam;
                if (hdr->dbch_devicetype == DEV_BROADCAST_HDR_DEVICE_TYPE.DBT_DEVTYP_DEVICEINTERFACE)
                {
                    DEV_BROADCAST_DEVICEINTERFACE_W* dev = (DEV_BROADCAST_DEVICEINTERFACE_W*)lParam;
                    DeviceChanged?.Invoke(evt == PInvoke.DBT_DEVICEARRIVAL, new string((char*)&dev->dbcc_name));
                }
            }
        }
        return nint.Zero;
    }

    public void Dispose()
    {
        _hwndSource.RemoveHook(WndProc);
        _notifyHandle?.Dispose();
        _notifyHandle = null;
    }

    private sealed class SafeHwndWrapper(nint hwnd) : SafeHandle(hwnd, ownsHandle: false)
    {
        public override bool IsInvalid => handle == nint.Zero;
        protected override bool ReleaseHandle() => true;
    }
}
```

### 5.3 Windows Audio Routing & WASAPI / `NAudio` Device-Change Traps

When registering `NAudio.CoreAudioApi.Interfaces.IMMNotificationClient` on `MMDeviceEnumerator.RegisterEndpointNotificationCallback(...)`:
1. **Keep strong references** to both `MMDeviceEnumerator` and your `IMMNotificationClient` until `UnregisterEndpointNotificationCallback` (GC/CCW collection mid-callback crashes native audio threads).
2. **Debounce `OnDefaultDeviceChanged` bursts:** Headset plug/unplug fires up to **3 consecutive callbacks** (`Role.Console`, `Role.Multimedia`, `Role.Communications`) on Core Audio **MTA worker threads**. Never tear down/recreate `WasapiCapture` or `WaveOutEvent` synchronously inside the COM callback — schedule a debounced `150–250 ms` re-init, marshal UI updates to `Dispatcher`, and handle `RecordingStopped` exceptions when a mic is yanked mid-stream.

### 5.4 Power Events (`SystemEvents.PowerModeChanged`) & Leak Prevention

Subscribe **from the WPF UI thread** (`SystemEvents` binds a hidden broadcast window to the first subscribing thread; subscribing on a ThreadPool worker without a message pump drops events or stalls exit). Always pair `+=` with **`-=`** on `OnClosed`/`Dispose`:

```csharp
using System;
using Microsoft.Win32;

namespace MyApp.Power;

public sealed class PowerLifecycleBridge : IDisposable
{
    private bool _subscribed;

    public void AttachOnUiThread()
    {
        if (_subscribed) return;
        SystemEvents.PowerModeChanged += OnPowerModeChanged;
        _subscribed = true;
    }

    private void OnPowerModeChanged(object? sender, PowerModeChangedEventArgs e)
    {
        if (e.Mode == PowerModes.Suspend) { /* Pause audio capture / close sockets cleanly */ }
        else if (e.Mode == PowerModes.Resume) { /* Re-enumerate devices & reconnect with backoff */ }
    }

    public void Dispose()
    {
        if (!_subscribed) return;
        // MANDATORY: SystemEvents is static; omitting -= leaks the instance forever
        SystemEvents.PowerModeChanged -= OnPowerModeChanged;
        _subscribed = false;
    }
}
```

> **Headless / Service Alternative:** Without a UI message loop, use Win32 `PowerRegisterSuspendResumeNotification` (`REGISTER_NOTIFICATION_FLAGS.DEVICE_NOTIFY_CALLBACK` + `[UnmanagedCallersOnly]` inside `DEVICE_NOTIFY_SUBSCRIBE_PARAMETERS`) and `PowerUnregisterSuspendResumeNotification` via CsWin32.
