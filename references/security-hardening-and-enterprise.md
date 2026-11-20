# Windows Security Hardening, Auth & Enterprise Compatibility (.NET 9/10)

> **Scope:** DLL hijacking defense (`SetDefaultDllDirectories`, `LoadLibraryEx`, `DefaultDllImportSearchPaths`), Windows Hello verification (`UserConsentVerifier` / `UserConsentVerifierInterop` + non-biometric fallback), OAuth 2.0 PKCE loopback auth (`127.0.0.1` vs. custom URI scheme hijacking), corporate proxies (`HttpClient.DefaultProxy`, WinHTTP/PAC), Windows Certificate Store (`X509Store` + `X509CertificateLoader`) & strict TLS hygiene, AppLocker / App Control for Business (WDAC) compatibility, SmartScreen reputation, `Microsoft.Sbom.Tool`, and deterministic CI builds.
>
> **Related:** See [windows-os-and-cswin32.md](windows-os-and-cswin32.md#4-secrets-credentials-uac--appmanifest-security) for DPAPI `CurrentUser`, Credential Manager, and `asInvoker` manifests, [packaging-signing-and-updates.md](packaging-signing-and-updates.md#7-code-signing--windows-smartscreen-engineering) for Azure Artifact Signing + RFC 3161 timestamps, [app-architecture-and-lifecycle.md](app-architecture-and-lifecycle.md#4-custom-uri-protocols--file-associations-hkcu-vs-msix) for URI command-injection defense, and [compiler-traps-and-compat.md](compiler-traps-and-compat.md) for `SYSLIB1062` / `PInvoke017`.

## Table of Contents

1. [DLL Hijacking Defense (`SetDefaultDllDirectories` & `LoadLibraryEx`)](#1-dll-hijacking-defense-setdefaultdlldirectories--loadlibraryex)
2. [Windows Hello Biometric Verification & Fallback](#2-windows-hello-biometric-verification--fallback)
3. [OAuth 2.0 PKCE Desktop Loopback Auth (RFC 8252)](#3-oauth-20-pkce-desktop-loopback-auth-rfc-8252)
4. [Corporate Networks, Proxies, Certificate Store & TLS Hygiene](#4-corporate-networks-proxies-certificate-store--tls-hygiene)
5. [AppLocker & WDAC (App Control for Business) Compatibility](#5-applocker--wdac-app-control-for-business-compatibility)
6. [Supply-Chain Integrity: SmartScreen, SBOM & Deterministic Builds](#6-supply-chain-integrity-smartscreen-sbom--deterministic-builds)

---

## 1. DLL Hijacking Defense (`SetDefaultDllDirectories` & `LoadLibraryEx`)

Default Windows DLL probing can search the current working directory (CWD) or `PATH` before resolving delay-loaded or runtime-loaded dependencies—allowing attackers who plant a rogue `version.dll` or plugin DLL in `Downloads` or a shared folder to hijack execution.

| Layer | Rule | Safe Implementation | Pitfall to Avoid |
|---|---|---|---|
| **Native C++ Startup** | Lock search order on line 1 of `wWinMain` | `SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_SYSTEM32)` (add `LOAD_LIBRARY_SEARCH_APPLICATION_DIR` only if app-local DLLs exist) | Bare `LoadLibraryA`/`LoadLibraryW` with relative filenames searches CWD/`PATH`. |
| **Dynamic Native Loads** | Always pass explicit directory flags | `LoadLibraryExW(L"...", nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32)` or `LOAD_LIBRARY_AS_DATAFILE` for resources | `SetDllDirectoryW(L"")` only removes CWD; it does not lock full `SafeDllSearch` flags. |
| **.NET P/Invoke (`[LibraryImport]`)** | Declare assembly-wide safe search paths | `[assembly: DefaultDllImportSearchPaths(DllImportSearchPath.AssemblyDirectory \| DllImportSearchPath.System32)]` | Omitting the attribute triggers **`CA5392`**; `SafeDirectories` without `System32` breaks OS imports. |
| **.NET NuGet Native Assets** | Resolve custom/sub-folder binaries explicitly | `NativeLibrary.SetDllImportResolver` + `Path.Combine(AppContext.BaseDirectory, ...)` | Calling `SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_SYSTEM32)` *alone* in a `.NET` `[ModuleInitializer]` blocks `runtimes\win-x64\native\` DLLs unless `LOAD_LIBRARY_SEARCH_APPLICATION_DIR` is included! |

### 1.1 C++ Win32 Startup Guard (`wWinMain`)

```cpp
#include <windows.h>
#include <libloaderapi.h>

int WINAPI wWinMain(_In_ HINSTANCE, _In_opt_ HINSTANCE, _In_ PWSTR, _In_ int)
{
    // First action in process startup: restrict DLL probing away from CWD and PATH
    if (!SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_SYSTEM32))
    {
        return static_cast<int>(GetLastError());
    }

    // Explicit safe flag; never call bare LoadLibraryW(L"helper.dll") on relative names
    HMODULE user32 = LoadLibraryExW(L"user32.dll", nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (user32 != nullptr)
    {
        FreeLibrary(user32);
    }
    return 0;
}
```

### 1.2 .NET (`CsWin32` + `DefaultDllImportSearchPaths` + `NativeLibrary`)

```csharp
// NativeMethods.txt: SetDefaultDllDirectories / LoadLibraryExW / LOAD_LIBRARY_FLAGS
using System;
using System.IO;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using Windows.Win32;
using Windows.Win32.System.LibraryLoader;

// Satisfies CA5392 while allowing app-local NuGet native libraries + System32 OS DLLs
[assembly: DefaultDllImportSearchPaths(DllImportSearchPath.AssemblyDirectory | DllImportSearchPath.System32)]

namespace MyApp.Security;

internal static class DllHardeningBootstrap
{
    [ModuleInitializer]
    internal static void LockDefaultDllDirectories()
    {
        PInvoke.SetDefaultDllDirectories(
            LOAD_LIBRARY_FLAGS.LOAD_LIBRARY_SEARCH_APPLICATION_DIR |
            LOAD_LIBRARY_FLAGS.LOAD_LIBRARY_SEARCH_SYSTEM32);
    }

    internal static FreeLibrarySafeHandle LoadSystemLibrarySafely(string dllName) =>
        // Caller owns and disposes the returned FreeLibrarySafeHandle
        PInvoke.LoadLibraryEx(dllName, LOAD_LIBRARY_FLAGS.LOAD_LIBRARY_SEARCH_SYSTEM32);

    internal static void RegisterPinnedNativeResolver(Assembly assembly, string nativeSubdir)
    {
        NativeLibrary.SetDllImportResolver(assembly, (libraryName, _, _) =>
        {
            if (libraryName == "my_native_codec")
            {
                string fullPath = Path.Combine(AppContext.BaseDirectory, nativeSubdir, "my_native_codec.dll");
                if (NativeLibrary.TryLoad(fullPath, out nint handle)) return handle;
            }
            return nint.Zero;
        });
    }
}
```

---

## 2. Windows Hello Biometric Verification & Fallback

Desktop WPF/WinUI 3 processes have no UWP `CoreWindow`. Calling `UserConsentVerifier.RequestVerificationAsync(...)` directly either fails or opens the prompt behind your app window—desktop apps **must** use **`UserConsentVerifierInterop.RequestVerificationForWindowAsync(hwnd, message)`** (`net10.0-windows10.0.19041.0+`).

| Mechanism | Role | Hardware Requirement | Mandatory Pairing / Fallback |
|---|---|---|---|
| **`UserConsentVerifierInterop`** | Local biometric/PIN user-presence gate | Windows Hello sensor or Windows PIN | Pair with DPAPI/PIN fallback when `DeviceNotPresent`, `NotConfiguredForUser`, or `DisabledByPolicy`. |
| **`KeyCredentialManager`** | Hardware-backed TPM asymmetric key challenge | TPM 2.0 + Windows Hello enrolled | Ideal for FIDO/server attestation; fall back to OAuth/passkey when unavailable. |
| **DPAPI (`ProtectedData` `CurrentUser`)** | Encrypts local secrets bound to Windows user profile | Any Windows PC (no bio sensor required) | Always supply app-specific `optionalEntropy`; never `LocalMachine` for user tokens. |
| **Credential Manager (`CredWriteW`)** | OS-managed user secret vault (`<= 2560 B`) | Any Windows PC | Suitable for refresh tokens/API keys when biometric re-prompt is optional. |

```csharp
using System;
using System.Threading.Tasks;
using Windows.Security.Credentials.UI;

namespace MyApp.Security;

public static class WindowsHelloGate
{
    public enum GateOutcome { Verified, FallbackRequired, Canceled, LockedOut }

    public static async Task<GateOutcome> VerifyOwnerAsync(nint ownerHwnd, string prompt)
    {
        // Always probe hardware & enterprise policy state before popping Windows Hello UI
        UserConsentVerifierAvailability availability = await UserConsentVerifier.CheckAvailabilityAsync();
        if (availability != UserConsentVerifierAvailability.Available)
        {
            return GateOutcome.FallbackRequired; // DeviceNotPresent, NotConfiguredForUser, DisabledByPolicy, DeviceBusy
        }

        // Obtain ownerHwnd via WindowInteropHelper(window).Handle (WPF) or WindowNative.GetWindowHandle(window) (WinUI 3)
        UserConsentVerificationResult result =
            await UserConsentVerifierInterop.RequestVerificationForWindowAsync(ownerHwnd, prompt);

        return result switch
        {
            UserConsentVerificationResult.Verified => GateOutcome.Verified,
            UserConsentVerificationResult.Canceled => GateOutcome.Canceled,
            UserConsentVerificationResult.RetriesExhausted => GateOutcome.LockedOut,
            _ => GateOutcome.FallbackRequired
        };
    }
}
```

---

## 3. OAuth 2.0 PKCE Desktop Loopback Auth (RFC 8252)

| Pattern | Security & Compatibility | Recommendation |
|---|---|---|
| **System Browser + `http://127.0.0.1:<port>/`** (RFC 8252) | Preserves OS SSO, passkeys/FIDO2, and password managers; Windows 10/11 permits loopback `http://127.0.0.1:<port>/` without admin `netsh http add urlacl` (unlike `http://+:port/`). | **Default** for third-party OAuth/OIDC desktop apps. Bind `127.0.0.1` explicitly (`localhost` can race IPv6 `::1`). |
| **Custom URI Scheme (`myapp://callback`)** | **Scheme hijacking risk:** any unprivileged process on Windows can overwrite `HKCU\Software\Classes\myapp` or race-register the scheme to intercept codes! | Avoid unless using MSIX-bound schemes; always enforce `S256` PKCE + exact `redirect_uri` verification. |
| **Windows Web Account Manager (`WebAuthenticationCoreManager` / MSAL WAM)** | Brokered OS SSO for Microsoft Entra ID / MSA without raw sockets or browser tab handoff. | **Preferred** for Microsoft Entra ID / M365 enterprise login when using MSAL or Package Identity. |
| **Embedded WebView2 Login** | Breaks FIDO2/SSO isolation; exposes credentials to host app; blocked by Google and major IdPs. | **Never use** embedded WebViews for primary OAuth 2.0 authorization. |

```csharp
using System;
using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace MyApp.Auth;

public static class LoopbackPkceAuth
{
    public sealed record AuthCallbackResult(string Code, string CodeVerifier, string RedirectUri);

    public static async Task<AuthCallbackResult> AuthorizeAsync(
        string authorizationEndpoint, string clientId, string scope, CancellationToken ct)
    {
        if (!Uri.TryCreate(authorizationEndpoint, UriKind.Absolute, out Uri? authUri) ||
            authUri.Scheme != Uri.UriSchemeHttps)
        {
            throw new ArgumentException("Authorization endpoint must use HTTPS.", nameof(authorizationEndpoint));
        }

        string codeVerifier = Base64UrlEncode(RandomNumberGenerator.GetBytes(32));
        string codeChallenge = Base64UrlEncode(SHA256.HashData(Encoding.ASCII.GetBytes(codeVerifier)));
        string expectedState = Base64UrlEncode(RandomNumberGenerator.GetBytes(32));

        int port = GetEphemeralPort();
        string redirectUri = $"http://127.0.0.1:{port}/callback/";

        using var listener = new HttpListener();
        listener.Prefixes.Add(redirectUri);
        listener.Start();

        try
        {
            string url = $"{authorizationEndpoint}" +
                         $"?response_type=code" +
                         $"&client_id={Uri.EscapeDataString(clientId)}" +
                         $"&redirect_uri={Uri.EscapeDataString(redirectUri)}" +
                         $"&scope={Uri.EscapeDataString(scope)}" +
                         $"&state={Uri.EscapeDataString(expectedState)}" +
                         $"&code_challenge={Uri.EscapeDataString(codeChallenge)}" +
                         $"&code_challenge_method=S256";

            // Validated HTTPS URI before launching the external system browser
            Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });

            using var reg = ct.Register(() => listener.Stop());
            HttpListenerContext context = await listener.GetContextAsync();

            string? returnedState = context.Request.QueryString["state"];
            string? error = context.Request.QueryString["error"];
            string? code = context.Request.QueryString["code"];

            bool stateValid = returnedState is not null &&
                              CryptographicOperations.FixedTimeEquals(
                                  Encoding.UTF8.GetBytes(returnedState),
                                  Encoding.UTF8.GetBytes(expectedState));

            byte[] html = Encoding.UTF8.GetBytes(
                stateValid && string.IsNullOrEmpty(error) && !string.IsNullOrEmpty(code)
                    ? "<html><body><h3>Sign-in complete</h3><p>You may close this browser tab.</p></body></html>"
                    : "<html><body><h3>Sign-in failed</h3><p>Return to the application.</p></body></html>");

            context.Response.StatusCode = stateValid && !string.IsNullOrEmpty(code) ? 200 : 400;
            context.Response.ContentType = "text/html; charset=utf-8";
            context.Response.ContentLength64 = html.Length;
            await context.Response.OutputStream.WriteAsync(html, ct);
            context.Response.OutputStream.Close();

            if (!stateValid) throw new InvalidOperationException("OAuth CSRF state mismatch.");
            if (!string.IsNullOrEmpty(error)) throw new InvalidOperationException($"OAuth error: {error}");
            if (string.IsNullOrEmpty(code)) throw new InvalidOperationException("Missing authorization code.");

            return new AuthCallbackResult(code, codeVerifier, redirectUri);
        }
        finally
        {
            if (listener.IsListening) listener.Stop();
        }
    }

    private static int GetEphemeralPort()
    {
        using var tcp = new TcpListener(IPAddress.Loopback, 0);
        tcp.Start();
        return ((IPEndPoint)tcp.LocalEndpoint).Port;
    }

    private static string Base64UrlEncode(ReadOnlySpan<byte> bytes) =>
        Convert.ToBase64String(bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_');
}
```

---

## 4. Corporate Networks, Proxies, Certificate Store & TLS Hygiene

- **Automatic Proxy & PAC Resolution (`HttpClient.DefaultProxy`):** On Windows `.NET 9/10`, `HttpClient.DefaultProxy` inspects `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` first, then reads Windows WinINet / PAC auto-configuration scripts automatically. Set `DefaultProxyCredentials = CredentialCache.DefaultNetworkCredentials` on `SocketsHttpHandler` for corporate NTLM/Kerberos proxies. *(Note: Session 0 Windows Services under `LocalSystem` have no per-user WinINet proxy—configure machine WinHTTP via `netsh winhttp set proxy` or query `WinHttpGetProxyForUrl`.)*
- **Windows Certificate Store & TLS Inspection Proxies:** Windows SChannel trusts enterprise Root/Intermediate CAs deployed to `LocalMachine\Root` or `CurrentUser\Root` automatically. **Avoid hard-coded leaf/intermediate cert pinning** in general desktop apps—corporate TLS-inspecting proxies (Zscaler, Netskope, Palo Alto) re-sign TLS with an enterprise CA from the Windows Certificate Store, breaking brittle pins.
- **Strict TLS Hygiene:** Leave `EnabledSslProtocols = SslProtocols.None` (allows OS SChannel to negotiate TLS 1.2/1.3 while blocking deprecated TLS 1.0/1.1). **Never** assign `ServerCertificateCustomValidationCallback = (_, _, _, _) => true` outside `#if DEBUG` (even inside `#if DEBUG`, restrict bypasses to `localhost` or an explicit dev cert thumbprint). Use **`X509CertificateLoader`** (`.NET 9/10`) instead of obsolete `new X509Certificate2(path, pwd)` constructors (`SYSLIB0057`).

```csharp
using System;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Security;
using System.Security.Authentication;
using System.Security.Cryptography.X509Certificates;

namespace MyApp.Networking;

public static class EnterpriseHttpClientFactory
{
    public static SocketsHttpHandler CreateCorporateHandler(
        string? clientCertThumbprint = null, string? pfxPath = null, string? pfxPassword = null)
    {
        var handler = new SocketsHttpHandler
        {
            Proxy = HttpClient.DefaultProxy,
            UseProxy = true,
            DefaultProxyCredentials = CredentialCache.DefaultNetworkCredentials,
            PooledConnectionLifetime = TimeSpan.FromMinutes(2),
            SslOptions = new SslClientAuthenticationOptions
            {
                // SslProtocols.None delegates TLS 1.2/1.3 negotiation to Windows SChannel
                EnabledSslProtocols = SslProtocols.None,
                CertificateRevocationCheckMode = X509RevocationMode.Online
            }
        };

        if (!string.IsNullOrWhiteSpace(clientCertThumbprint))
        {
            using var store = new X509Store(StoreName.My, StoreLocation.CurrentUser);
            store.Open(OpenFlags.ReadOnly);
            X509Certificate2Collection matches = store.Certificates.Find(
                X509FindType.FindByThumbprint, clientCertThumbprint, validOnly: true);
            if (matches.Count > 0)
            {
                handler.SslOptions.ClientCertificates ??= new X509Certificate2Collection();
                handler.SslOptions.ClientCertificates.Add(matches[0]);
            }
        }
        else if (!string.IsNullOrWhiteSpace(pfxPath) && File.Exists(pfxPath))
        {
            X509Certificate2 clientCert = X509CertificateLoader.LoadPkcs12FromFile(pfxPath, pfxPassword);
            handler.SslOptions.ClientCertificates ??= new X509Certificate2Collection();
            handler.SslOptions.ClientCertificates.Add(clientCert);
        }

        return handler;
    }
}
```

---

## 5. AppLocker & WDAC (App Control for Business) Compatibility

Enterprise Windows endpoints enforce **AppLocker** or **App Control for Business (WDAC)** allow-lists based on Publisher certificates, Managed Installers (Intune/SCCM), and secure directories (`Program Files`).

| Artifact / Pattern | AppLocker & WDAC Behavior | Enterprise Remediation |
|---|---|---|
| **Signed MSIX / WiX MSI (`Program Files`, multi-file)** | Allowed cleanly under Publisher, Managed Installer, or default `Program Files` path rules. | Sign every `.exe`, `.dll`, and installer container inside-out with SHA-256 + RFC 3161 timestamps. |
| **Single-file + `IncludeNativeLibrariesForSelfExtract=true`** | **BLOCKED:** native DLLs extract to `%TEMP%\.net\<App>\`, violating non-writable-exec rules. | Ship multi-file `<PublishSingleFile>false</PublishSingleFile>` for enterprise builds; keep `PublishReadyToRun=true`. |
| **Runtime `%TEMP%` `.ps1`/`.bat`/`.dll` or `Assembly.Load(byte[])`** | **BLOCKED:** unsigned or temp-path scripts/assemblies fail user-mode code integrity. | Replace runtime scripts with compiled native/C# code; avoid dynamic `Roslyn` / `Emit` in locked-down apps. |
| **WDAC Option `19` (`Enabled:Dynamic Code Security`)** | Enforces strict integrity checks on `System.Reflection.Emit` and `.NET` native images (`NTFS` Extended Attributes; audit-mode needs Win11 `24H2+`). | Enable `<PublishReadyToRun>true</PublishReadyToRun>` and source generators (`CommunityToolkit.Mvvm`, `System.Text.Json`, `CsWin32`). |

**Diagnosing Blocks on Target Devices:** Inspect Event Viewer under `Applications and Services Logs -> Microsoft -> Windows -> AppLocker -> EXE and DLL` and `CodeIntegrity -> Operational` (Event IDs `3076`/`3077` for WDAC audit/enforce blocks).

---

## 6. Supply-Chain Integrity: SmartScreen, SBOM & Deterministic Builds

### 6.1 SmartScreen Enterprise Reputation Quick Checks

Follow [packaging-signing-and-updates.md](packaging-signing-and-updates.md#7-code-signing--windows-smartscreen-engineering) for Azure Artifact Signing CI workflows and RFC 3161 timestamping. After signing and before release promotion, verify both Authenticode trust and timestamp chaining:

```powershell
signtool.exe verify /pa /v ".\releases\MyApp.msi"
Get-AuthenticodeSignature ".\releases\MyApp.msi" | Format-List Status, SignerCertificate, TimeStamperCertificate
```

### 6.2 Deterministic Builds, Lock Files & `NuGetAudit` (`Directory.Build.props`)

Enable deterministic compilation, CI path normalization, locked restores, and `NuGetAudit` so binary SHA-256 digests stay reproducible across runners and match SBOM manifests:

```xml
<!-- Directory.Build.props -->
<Project>
  <PropertyGroup>
    <Deterministic>true</Deterministic>
    <ContinuousIntegrationBuild Condition="'$(CI)' == 'true' or '$(GITHUB_ACTIONS)' == 'true'">true</ContinuousIntegrationBuild>
    <RestorePackagesWithLockFile>true</RestorePackagesWithLockFile>
    <RestoreLockedMode Condition="'$(CI)' == 'true' or '$(GITHUB_ACTIONS)' == 'true'">true</RestoreLockedMode>
    <NuGetAudit>true</NuGetAudit>
    <NuGetAuditMode>all</NuGetAuditMode>
    <NuGetAuditLevel>moderate</NuGetAuditLevel>
  </PropertyGroup>
</Project>
```

### 6.3 SPDX SBOM Generation & Validation (`Microsoft.Sbom.Tool`)

Generate and validate the SPDX manifest (`_manifest/spdx_2.2/manifest.spdx.json`) against the published drop **before** wrapping binaries into signed installers:

```powershell
dotnet tool install --global Microsoft.Sbom.DotNetTool

dotnet publish -c Release -r win-x64 --self-contained true -p:PublishReadyToRun=true -p:ContinuousIntegrationBuild=true -o ".\publish\win-x64"

sbom-tool generate `
  -b ".\publish\win-x64" `
  -bc ".\src" `
  -pn "MyApp" `
  -pv "1.2.0" `
  -ps "MyCompany" `
  -nsb "https://sbom.example.com" `
  -m ".\publish\win-x64\_manifest"

sbom-tool validate `
  -b ".\publish\win-x64" `
  -m ".\publish\win-x64\_manifest" `
  -o ".\sbom-validation.json"
```
