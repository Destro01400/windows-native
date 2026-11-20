# Windows Background Services & High-Performance Local IPC (.NET 9/10)

> **Scope:** Session 0 Isolation and companion Tray/UI bridge architecture, `Microsoft.Extensions.Hosting.WindowsServices` (`AddWindowsService`, `ContentRootPath`, `BackgroundService` cancellation, EventLog), **gRPC over Named Pipes** on `.NET 8/9/10` (`Kestrel` `ListenNamedPipe` + `NamedPipeTransportOptions` + `SocketsHttpHandler.ConnectCallback`), explicit `PipeSecurity` ACLs (`LocalSystemSid` + `AuthenticatedUserSid` vs. insecure `WorldSid` & `CurrentUserOnly`), length-prefixed framing on raw `NamedPipeServerStream`/`ClientStream`, `MemoryMappedFile` ring buffers for high-frequency local IPC, `sc.exe failure`/`failureflag`, WiX v5 `<ServiceInstall>`, and Tray companion watchdog patterns.
>
> **Related:** See [app-architecture-and-lifecycle.md](app-architecture-and-lifecycle.md#3-single-instance-activation--secure-named-pipe-ipc) for desktop-only single-instance `Mutex` + `NamedPipeServerStream`, [packaging-signing-and-updates.md](packaging-signing-and-updates.md#51-wix-toolset-v5-wixproj--packagewxs) for WiX v5 MSI setups, and [compiler-traps-and-compat.md](compiler-traps-and-compat.md) for Windows service runtime traps.

## Table of Contents

1. [Session 0 Isolation & the Companion Tray/UI Pattern](#1-session-0-isolation--the-companion-trayui-pattern)
2. [`Microsoft.Extensions.Hosting.WindowsServices` Worker Setup](#2-microsoftextensionshostingwindowsservices-worker-setup)
3. [gRPC over Named Pipes on `.NET 8/9/10`](#3-grpc-over-named-pipes-on-net-8910)
4. [Named Pipe Security: `PipeSecurity` ACLs & `CurrentUserOnly`](#4-named-pipe-security-pipesecurity-acls--currentuseronly)
5. [Raw `NamedPipeServerStream`: Length-Prefixed Framing & Cancellation](#5-raw-namedpipeserverstream-length-prefixed-framing--cancellation)
6. [High-Frequency Local IPC: `MemoryMappedFile` Ring Buffers](#6-high-frequency-local-ipc-memorymappedfile-ring-buffers)
7. [Service Recovery (`sc.exe failure`), WiX v5 `<ServiceInstall>` & Tray Watchdog](#7-service-recovery-scexe-failure-wix-v5-serviceinstall--tray-watchdog)

---

## 1. Session 0 Isolation & the Companion Tray/UI Pattern

Since Windows Vista, the Service Control Manager (SCM) isolates all Windows Services inside non-interactive **Session 0**, separated from user desktops (**Session 1, 2, ...** on `WinSta0\Default`).

| Consequence of Session 0 | Why Direct Workarounds Fail | Supported Architecture |
|---|---|---|
| **No desktop UI or tray icon** | `SERVICE_INTERACTIVE_PROCESS` (`UI0Detect`) is dead in Windows 10/11; hidden prompts hang forever. | Run a separate **user-session Tray/UI companion** (`asInvoker`) started at logon (`HKLM\...\Run` or Scheduled Task). |
| **Isolated `HKCU` & DPAPI scope** | Service `CurrentUser` DPAPI keys and hives belong to `SYSTEM`/`LocalService`, not the logged-in user. | Store service state in `%ProgramData%\<Company>\<App>` (service ACL) and user preferences in `%LocalAppData%`. |
| **Multi-user / RDP sessions** | Fast User Switching & RDP create multiple interactive sessions concurrently. | Have each user's Tray app connect **outbound** to the service IPC endpoint; never assume one Session 1 user exists. |

```text
  [Session 1+ User Desktop]                          [Session 0 Service]
  MyApp.Tray.exe (asInvoker)  -- Named Pipe / gRPC -->  MyApp.Service.exe
  - Tray icon, Toasts, UI        (PipeSecurity ACL)     - BackgroundService / Hardware / Privileged work
```

---

## 2. `Microsoft.Extensions.Hosting.WindowsServices` Worker Setup

### 2.1 Service Account Least Privilege Matrix

| Service Account | Privilege Level | Network Identity | Typical Use Case |
|---|---|---|---|
| **`NT SERVICE\<ServiceName>`** (Virtual Service Account) | Minimal; per-service SID | Machine account (`DOMAIN\HOST$`) | **Preferred default**; grant write ACL only to `%ProgramData%\<Company>\<App>`. |
| **`NT AUTHORITY\LocalService`** | Minimal | Anonymous on network | Local hardware/telemetry workers with zero domain access needed. |
| **`NT AUTHORITY\NetworkService`** | Minimal local; machine network | Machine account | Workers calling authenticated intranet/AD endpoints. |
| **`LocalSystem`** | **Full machine admin** | Machine account | **Avoid** unless kernel/driver/machine-wide control strictly requires it. |

### 2.2 `ContentRootPath`, `AddWindowsService` & EventLog Pitfalls

1. **`C:\Windows\System32` CWD Trap:** SCM starts every service with `Environment.CurrentDirectory == C:\Windows\System32`. Pass `ContentRootPath = AppContext.BaseDirectory` into `HostApplicationBuilderSettings` / `WebApplicationOptions` so `appsettings.json` resolves beside the `.exe`.
2. **Console vs. SCM Dual Mode:** `AddWindowsService()` activates `WindowsServiceLifetime` **only** when `WindowsServiceHelpers.IsWindowsService()` detects SCM; launching the `.exe` directly in a terminal still supports `Ctrl+C`.
3. **Graceful Cancellation Within SCM Timeout:** SCM allows ~20–30 s (`WaitToKillServiceTimeout`) on stop before killing the process. Thread `stoppingToken` into every `Task.Delay`/I/O call and catch `OperationCanceledException` cleanly.
4. **EventLog Source Permissions:** `AddWindowsService()` registers `EventLogLoggerProvider` automatically (`Warning` default filter). Creating a *new* custom EventLog source at runtime fails under `LocalService`/`NT SERVICE`; pre-create custom sources in your MSI or log under the default `"Application"` source.

```csharp
// Requires NuGet: Microsoft.Extensions.Hosting.WindowsServices (>= 10.0.0)
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Configuration;
using Microsoft.Extensions.Logging.EventLog;

namespace MyApp.Services;

public sealed class AgentWorkerService(ILogger<AgentWorkerService> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        await Task.Yield();
        logger.LogInformation("Background worker started (PID {ProcessId}).", Environment.ProcessId);
        try
        {
            while (!stoppingToken.IsCancellationRequested)
                await Task.Delay(TimeSpan.FromSeconds(30), stoppingToken);
        }
        catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
        {
            logger.LogInformation("Background worker stopping gracefully.");
        }
    }
}

public static class WorkerHostBuilder
{
    public static IHost BuildWorkerServiceHost(string[] args)
    {
        HostApplicationBuilder builder = Host.CreateApplicationBuilder(new HostApplicationBuilderSettings
        {
            Args = args,
            ContentRootPath = AppContext.BaseDirectory
        });
        builder.Services.AddWindowsService(options => options.ServiceName = "MyAppBackgroundWorker");
        LoggerProviderOptions.RegisterProviderOptions<EventLogSettings, EventLogLoggerProvider>(builder.Services);
        builder.Services.AddHostedService<AgentWorkerService>();
        return builder.Build();
    }
}
```

---

## 3. gRPC over Named Pipes on `.NET 8/9/10`

gRPC over Named Pipes gives HTTP/2 multiplexing, strongly typed `.proto` contracts, and server-streaming updates with **zero TCP ports** and **zero Windows Firewall prompts**.

### 3.1 `.proto` Contract (`Protos/agent_ipc.proto`)

```protobuf
syntax = "proto3";
option csharp_namespace = "MyApp.Ipc";
package agent_ipc;

service AgentControl {
  rpc GetStatus (StatusRequest) returns (StatusReply);
  rpc StreamEvents (StatusRequest) returns (stream AgentEvent);
}

message StatusRequest { string client_id = 1; }
message StatusReply { bool is_healthy = 1; int64 uptime_seconds = 2; }
message AgentEvent { string kind = 1; string detail = 2; }
```

### 3.2 Kestrel Server (`ListenNamedPipe` + Cross-Session `PipeSecurity`)

Kestrel defaults to `NamedPipeTransportOptions.CurrentUserOnly = true`, which **blocks** Session 1 desktop users from connecting to a Session 0 service running as `LocalSystem` or `NT SERVICE\...`. Clear `CurrentUserOnly` and supply explicit `PipeSecurity`—or use `.NET 9/10`'s `CreateNamedPipeServerStream` callback for per-endpoint ACLs:

```csharp
// Requires NuGet: Grpc.AspNetCore, Microsoft.Extensions.Hosting.WindowsServices
using System.IO.Pipes;
using Grpc.Core;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Server.Kestrel.Core;
using Microsoft.AspNetCore.Server.Kestrel.Transport.NamedPipes;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging.Configuration;
using Microsoft.Extensions.Logging.EventLog;

namespace MyApp.Services;

public sealed class AgentControlGrpcService : MyApp.Ipc.AgentControl.AgentControlBase
{
    private static readonly DateTimeOffset StartedAt = DateTimeOffset.UtcNow;

    public override Task<MyApp.Ipc.StatusReply> GetStatus(MyApp.Ipc.StatusRequest request, ServerCallContext context) =>
        Task.FromResult(new MyApp.Ipc.StatusReply { IsHealthy = true, UptimeSeconds = (long)(DateTimeOffset.UtcNow - StartedAt).TotalSeconds });

    public override async Task StreamEvents(
        MyApp.Ipc.StatusRequest request, IServerStreamWriter<MyApp.Ipc.AgentEvent> responseStream, ServerCallContext context)
    {
        while (!context.CancellationToken.IsCancellationRequested)
        {
            await responseStream.WriteAsync(new MyApp.Ipc.AgentEvent { Kind = "heartbeat", Detail = "ok" }, context.CancellationToken);
            await Task.Delay(TimeSpan.FromSeconds(5), context.CancellationToken);
        }
    }
}

public static class ServiceHostSample
{
    public static WebApplication BuildMultiEndpointServiceHost(string[] args)
    {
        var builder = WebApplication.CreateBuilder(new WebApplicationOptions { Args = args, ContentRootPath = AppContext.BaseDirectory });
        builder.Services.AddWindowsService(o => o.ServiceName = "MyAppAgentService");
        LoggerProviderOptions.RegisterProviderOptions<EventLogSettings, EventLogLoggerProvider>(builder.Services);
        builder.Services.AddGrpc();
        builder.Services.AddHostedService<AgentWorkerService>();
        builder.WebHost.ConfigureKestrel(server =>
        {
            server.ListenNamedPipe("MyApp.AdminPipe", o => o.Protocols = HttpProtocols.Http2);
            server.ListenNamedPipe("MyApp.TrayPipe", o => o.Protocols = HttpProtocols.Http2);
        });
        // .NET 9/10 per-endpoint NamedPipeTransportOptions hook
        builder.WebHost.UseNamedPipes(options =>
        {
            options.CreateNamedPipeServerStream = context =>
            {
                if (context.NamedPipeEndPoint.PipeName == "MyApp.TrayPipe")
                {
                    PipeOptions pipeOptions = context.PipeOptions & ~PipeOptions.CurrentUserOnly;
                    return NamedPipeServerStreamAcl.Create(
                        context.NamedPipeEndPoint.PipeName, PipeDirection.InOut,
                        NamedPipeServerStream.MaxAllowedServerInstances, PipeTransmissionMode.Byte,
                        pipeOptions, 0, 0, ServicePipeSecurityFactory.CreateServiceToUserPipeSecurity());
                }
                return NamedPipeTransportOptions.CreateDefaultNamedPipeServerStream(context);
            };
        });
        WebApplication app = builder.Build();
        app.MapGrpcService<AgentControlGrpcService>();
        return app;
    }
}
```

### 3.3 Client (`SocketsHttpHandler.ConnectCallback` + `NamedPipeClientStream`)

Pass `TokenImpersonationLevel.Anonymous` (or `None`) on `NamedPipeClientStream` so a compromised server cannot impersonate the user's client token:

```csharp
// Requires NuGet: Grpc.Net.Client
using System.IO.Pipes;
using System.Net.Http;
using System.Security.Principal;
using Grpc.Net.Client;

namespace MyApp.Ipc;

public static class GrpcNamedPipeClientFactory
{
    public static GrpcChannel CreateChannel(string pipeName)
    {
        var handler = new SocketsHttpHandler
        {
            ConnectCallback = async (_, cancellationToken) =>
            {
                var clientStream = new NamedPipeClientStream(
                    ".", pipeName, PipeDirection.InOut, PipeOptions.Asynchronous, TokenImpersonationLevel.Anonymous);
                try { await clientStream.ConnectAsync(cancellationToken).ConfigureAwait(false); return clientStream; }
                catch { await clientStream.DisposeAsync().ConfigureAwait(false); throw; }
            }
        };
        return GrpcChannel.ForAddress("http://localhost", new GrpcChannelOptions { HttpHandler = handler, DisposeHttpClient = true });
    }
}
```

> **Unsupported gRPC Client APIs:** With `SocketsHttpHandler.ConnectCallback`, `GrpcChannel.State`, `WaitForStateChangedAsync`, and client-side load balancing throw `InvalidOperationException`. Reuse one `GrpcChannel` for the Tray process lifetime.

---

## 4. Named Pipe Security: `PipeSecurity` ACLs & `CurrentUserOnly`

| Rule | Why It Matters |
|---|---|
| **Prefer `PipeOptions.CurrentUserOnly`** for user-to-user desktop IPC | Kernel enforces identical user SID automatically with zero custom ACL code. |
| **Never combine `PipeOptions.CurrentUserOnly` with `PipeSecurity`** | Throws `ArgumentException` (`NamedPipeServerStreamAcl` & Kestrel `.NET 9/10`). Strip `~PipeOptions.CurrentUserOnly` when using `PipeSecurity`. |
| **Never grant `WorldSid` (`Everyone`) or client `FullControl`** | Exposes the pipe to guest/sandboxed processes and lets clients alter DACLs (`ChangePermissions`). |
| **Never grant `CreateNewInstance` to `AuthenticatedUserSid`** | Enables **Named Pipe Squatting**: an unprivileged attacker can race the service at boot, claim the pipe name first, and hijack client commands. |
| **Use `PipeOptions.FirstPipeInstance` on single-instance raw servers** | Fails immediately if a rogue process already squatted the pipe name. |

```csharp
using System.IO.Pipes;
using System.Security.AccessControl;
using System.Security.Principal;

namespace MyApp.Services;

public static class ServicePipeSecurityFactory
{
    public static PipeSecurity CreateServiceToUserPipeSecurity()
    {
        var security = new PipeSecurity();
        foreach (var sidType in new[] { WellKnownSidType.LocalSystemSid, WellKnownSidType.BuiltinAdministratorsSid })
            security.AddAccessRule(new PipeAccessRule(new SecurityIdentifier(sidType, null), PipeAccessRights.FullControl, AccessControlType.Allow));
        using WindowsIdentity identity = WindowsIdentity.GetCurrent();
        if (identity.User is not null)
            security.AddAccessRule(new PipeAccessRule(identity.User, PipeAccessRights.FullControl, AccessControlType.Allow));
        // Clients get ReadWrite ONLY (no CreateNewInstance, no FullControl, no WorldSid)
        security.AddAccessRule(new PipeAccessRule(
            new SecurityIdentifier(WellKnownSidType.AuthenticatedUserSid, null), PipeAccessRights.ReadWrite, AccessControlType.Allow));
        return security;
    }
}
```

---

## 5. Raw `NamedPipeServerStream`: Length-Prefixed Framing & Cancellation

For ultra-lean NativeAOT utilities without ASP.NET Core/Kestrel, pair `PipeTransmissionMode.Byte` with **4-byte little-endian length-prefixed framing**. Unlike Windows-only `PipeTransmissionMode.Message` (which still requires looping on `!stream.IsMessageComplete`), explicit length headers validate `MaxFrameBytes` *before* allocating and use `.NET 7+` `ReadExactlyAsync`:

```csharp
using System.Buffers;
using System.Buffers.Binary;
using System.IO;
using System.IO.Pipes;
using System.Security.AccessControl;
using MyApp.Services;

namespace MyApp.Ipc;

public static class FramedPipeTransport
{
    public const int MaxFrameBytes = 4 * 1024 * 1024;

    public static NamedPipeServerStream CreateHardenedServerStream(string pipeName, bool sameUserOnly)
    {
        if (sameUserOnly)
            return new NamedPipeServerStream(pipeName, PipeDirection.InOut, 1, PipeTransmissionMode.Byte,
                PipeOptions.CurrentUserOnly | PipeOptions.Asynchronous | PipeOptions.FirstPipeInstance);

        PipeSecurity security = ServicePipeSecurityFactory.CreateServiceToUserPipeSecurity();
        return NamedPipeServerStreamAcl.Create(pipeName, PipeDirection.InOut, 1, PipeTransmissionMode.Byte,
            PipeOptions.Asynchronous | PipeOptions.FirstPipeInstance, 0, 0, security);
    }

    public static async Task WriteFrameAsync(Stream stream, ReadOnlyMemory<byte> payload, CancellationToken ct)
    {
        if (payload.Length > MaxFrameBytes) throw new InvalidDataException($"Frame exceeds {MaxFrameBytes} bytes.");
        byte[] header = ArrayPool<byte>.Shared.Rent(4);
        try
        {
            BinaryPrimitives.WriteInt32LittleEndian(header.AsSpan(0, 4), payload.Length);
            await stream.WriteAsync(header.AsMemory(0, 4), ct).ConfigureAwait(false);
            if (!payload.IsEmpty) await stream.WriteAsync(payload, ct).ConfigureAwait(false);
            await stream.FlushAsync(ct).ConfigureAwait(false);
        }
        finally { ArrayPool<byte>.Shared.Return(header); }
    }

    public static async Task<byte[]?> ReadFrameAsync(Stream stream, CancellationToken ct)
    {
        byte[] header = ArrayPool<byte>.Shared.Rent(4);
        int length;
        try
        {
            try { await stream.ReadExactlyAsync(header.AsMemory(0, 4), ct).ConfigureAwait(false); }
            catch (EndOfStreamException) { return null; }
            length = BinaryPrimitives.ReadInt32LittleEndian(header.AsSpan(0, 4));
        }
        finally { ArrayPool<byte>.Shared.Return(header); }

        if (length < 0 || length > MaxFrameBytes) throw new InvalidDataException($"Invalid frame length: {length}");
        byte[] payload = new byte[length];
        if (length > 0) await stream.ReadExactlyAsync(payload.AsMemory(), ct).ConfigureAwait(false);
        return payload;
    }
}
```

> **Structured Cancellation:** Wrap reads in `CancellationTokenSource.CreateLinkedTokenSource(stoppingToken)` with `.CancelAfter(...)` so stalled peers cannot pin server pipe instances past shutdown.

---

## 6. High-Frequency Local IPC: `MemoryMappedFile` Ring Buffers

Drop below Named Pipes to `MemoryMappedFile` ring buffers only when telemetry, audio PCM, or frame throughput exceeds ~10,000 messages/second or multi-MB payloads where per-message kernel syscalls bottleneck:

1. **Session 0 `Global\` ACL Caveat in `.NET 8/9/10`:** Modern `.NET` omits `MemoryMappedFileSecurity` on `MemoryMappedFile.CreateNew`. Crossing Session 0 -> Session 1 requires `Global\` (created by the service holding `SeCreateGlobalPrivilege`) **plus** an explicit DACL—achieve this by backing the mapping with a real file under `%ProgramData%\<Company>\<App>\shm\` ACL'd via `FileSystemAclExtensions`, or via `CsWin32` `CreateFileMapping` + `SECURITY_ATTRIBUTES`. Reserve bare pagefile-backed `Local\` MMFs for same-session processes.
2. **Cache-Line Padding & Fences:** Separate `WriteCursor` and `ReadCursor` by **64 bytes** to prevent false sharing, emit `Thread.MemoryBarrier()` before publishing/consuming cursors (critical on ARM64), and signal wakeups via `EventWaitHandle` (`AutoReset`) instead of polling.

```csharp
using System.Buffers.Binary;
using System.IO;
using System.IO.MemoryMappedFiles;
using System.Runtime.Versioning;

namespace MyApp.Ipc;

[SupportedOSPlatform("windows")]
public sealed class SameSessionRingBuffer : IDisposable
{
    private const int WriteCursorOffset = 0, ReadCursorOffset = 64, HeaderSize = 128;
    private readonly int _capacity;
    private readonly MemoryMappedFile _mmf;
    private readonly MemoryMappedViewAccessor _view;
    private readonly EventWaitHandle _dataReadyEvent;

    public SameSessionRingBuffer(string baseName, int capacityBytes, bool isCreator)
    {
        if (capacityBytes <= 8) throw new ArgumentOutOfRangeException(nameof(capacityBytes));
        _capacity = capacityBytes;
        long totalSize = HeaderSize + capacityBytes;
        _mmf = isCreator ? MemoryMappedFile.CreateNew($@"Local\{baseName}.Ring", totalSize)
                         : MemoryMappedFile.OpenExisting($@"Local\{baseName}.Ring");
        _view = _mmf.CreateViewAccessor(0, totalSize);
        _dataReadyEvent = new EventWaitHandle(false, EventResetMode.AutoReset, $@"Local\{baseName}.Signal");
    }

    public bool TryWriteFrame(byte[] payload, int offset, int count)
    {
        if (count < 0 || offset < 0 || offset + count > payload.Length) throw new ArgumentOutOfRangeException(nameof(count));
        int frameBytes = 4 + count, readPos = ReadCursorAcquire(), writePos = _view.ReadInt32(WriteCursorOffset);
        int free = _capacity - (writePos >= readPos ? writePos - readPos : _capacity - readPos + writePos) - 1;
        if (frameBytes > free) return false;
        byte[] lenBytes = BitConverter.GetBytes(count);
        if (!BitConverter.IsLittleEndian) Array.Reverse(lenBytes);
        WriteCircular(writePos, lenBytes, 0, 4);
        WriteCircular((writePos + 4) % _capacity, payload, offset, count);
        Thread.MemoryBarrier();
        _view.Write(WriteCursorOffset, (writePos + frameBytes) % _capacity);
        _dataReadyEvent.Set();
        return true;
    }

    public bool TryReadFrame(byte[] destinationBuffer, out int bytesRead)
    {
        bytesRead = 0;
        int writePos = WriteCursorAcquire(), readPos = _view.ReadInt32(ReadCursorOffset);
        if (readPos == writePos) return false;
        byte[] lenBytes = new byte[4];
        ReadCircular(readPos, lenBytes, 0, 4);
        int length = BinaryPrimitives.ReadInt32LittleEndian(lenBytes);
        if (length < 0 || length > destinationBuffer.Length) throw new InvalidDataException($"Corrupt frame: {length}");
        ReadCircular((readPos + 4) % _capacity, destinationBuffer, 0, length);
        Thread.MemoryBarrier();
        _view.Write(ReadCursorOffset, (readPos + 4 + length) % _capacity);
        bytesRead = length;
        return true;
    }

    public bool WaitForData(TimeSpan timeout) => _dataReadyEvent.WaitOne(timeout);
    private int ReadCursorAcquire() { int v = _view.ReadInt32(ReadCursorOffset); Thread.MemoryBarrier(); return v; }
    private int WriteCursorAcquire() { int v = _view.ReadInt32(WriteCursorOffset); Thread.MemoryBarrier(); return v; }

    private void WriteCircular(int ringOffset, byte[] data, int srcOffset, int count)
    {
        int first = Math.Min(count, _capacity - ringOffset);
        _view.WriteArray(HeaderSize + ringOffset, data, srcOffset, first);
        if (first < count) _view.WriteArray(HeaderSize, data, srcOffset + first, count - first);
    }

    private void ReadCircular(int ringOffset, byte[] dest, int destOffset, int count)
    {
        int first = Math.Min(count, _capacity - ringOffset);
        _view.ReadArray(HeaderSize + ringOffset, dest, destOffset, first);
        if (first < count) _view.ReadArray(HeaderSize, dest, destOffset + first, count - first);
    }

    public void Dispose() { _dataReadyEvent.Dispose(); _view.Dispose(); _mmf.Dispose(); }
}
```

---

## 7. Service Recovery (`sc.exe failure`), WiX v5 `<ServiceInstall>` & Tray Watchdog

### 7.1 `sc.exe failure` + `failureflag` Auto-Restart Setup

Keep the **mandatory space after `=`**, and set `sc.exe failureflag <Name> 1` so non-zero exit codes trigger recovery too (not only hard crashes). Intentional stops (`sc.exe stop` or exit code `0`) never trigger recovery:

```powershell
# Run as Administrator
sc.exe create MyAppAgentService binPath= "`"C:\Program Files\MyCompany\MyApp\MyApp.Service.exe`"" start= auto obj= "NT SERVICE\MyAppAgentService" DisplayName= "MyApp Background Agent"
sc.exe failure MyAppAgentService reset= 86400 actions= restart/5000/restart/30000/restart/60000
sc.exe failureflag MyAppAgentService 1
sc.exe start MyAppAgentService
sc.exe qfailure MyAppAgentService
```

### 7.2 WiX Toolset v5 `<ServiceInstall>` + `<util:ServiceConfig>`

Requires `WixToolset.Util.wixext` (`xmlns:util="http://wixtoolset.org/schemas/v4/wxs/util"`):

```xml
<Component Id="AgentServiceComponent" Guid="PUT-COMPONENT-GUID-HERE">
  <File Id="AgentServiceExe" Source="$(var.ServicePublishDir)\MyApp.Service.exe" KeyPath="yes" />
  <ServiceInstall Id="MyAppAgentServiceInstall" Name="MyAppAgentService" DisplayName="MyApp Background Agent"
                  Description="Runs background sync and device monitoring in Session 0."
                  Start="auto" Type="ownProcess" ErrorControl="normal" Account="NT SERVICE\MyAppAgentService" Vital="yes">
    <util:ServiceConfig FirstFailureActionType="restart" SecondFailureActionType="restart" ThirdFailureActionType="restart"
                        RestartServiceDelayInSeconds="10" ResetPeriodInDays="1" />
  </ServiceInstall>
  <ServiceControl Id="MyAppAgentServiceControl" Name="MyAppAgentService" Start="install" Stop="both" Remove="uninstall" Wait="yes" />
</Component>
```

### 7.3 Tray Companion Watchdog Architecture

Standard `asInvoker` users can query `ServiceController.Status` read-only (`SERVICE_QUERY_STATUS`), whereas starting/stopping a service requires elevation (unless an installer modifies the service DACL via `sc.exe sdset`). Reconnect with capped exponential backoff + jitter and **halt retries** on `UnauthorizedAccessException`:

```csharp
// Requires NuGet: System.ServiceProcess.ServiceController, Grpc.Net.Client
using System.ComponentModel;
using System.IO;
using System.Runtime.Versioning;
using System.ServiceProcess;
using Grpc.Core;
using Grpc.Net.Client;

namespace MyApp.Ipc;

[SupportedOSPlatform("windows")]
public sealed class TrayServiceWatchdog(string serviceName, string pipeName)
{
    public ServiceControllerStatus? TryQueryServiceStatus()
    {
        try { using var sc = new ServiceController(serviceName); return sc.Status; }
        catch (Exception ex) when (ex is InvalidOperationException or Win32Exception) { return null; }
    }

    public async Task RunWatchdogLoopAsync(
        Func<GrpcChannel, CancellationToken, Task> streamSessionAsync, Action<string> reportUiState, CancellationToken ct)
    {
        for (int backoffSeconds = 1; !ct.IsCancellationRequested;)
        {
            ServiceControllerStatus? status = TryQueryServiceStatus();
            if (status != ServiceControllerStatus.Running)
            {
                reportUiState(status is null ? "Service not installed" : $"Service {status}");
                await Task.Delay(TimeSpan.FromSeconds(backoffSeconds), ct);
                backoffSeconds = Math.Min(backoffSeconds * 2, 15);
                continue;
            }
            try
            {
                using GrpcChannel channel = GrpcNamedPipeClientFactory.CreateChannel(pipeName);
                backoffSeconds = 1;
                reportUiState("Connected");
                await streamSessionAsync(channel, ct);
            }
            catch (UnauthorizedAccessException)
            {
                reportUiState("Pipe ACL denied access — verify service permissions");
                return;
            }
            catch (Exception ex) when (ex is IOException or System.TimeoutException or RpcException)
            {
                if (ct.IsCancellationRequested) break;
                reportUiState("Reconnecting to service...");
                await Task.Delay(TimeSpan.FromSeconds(backoffSeconds) + TimeSpan.FromMilliseconds(Random.Shared.Next(100, 450)), ct);
                backoffSeconds = Math.Min(backoffSeconds * 2, 15);
            }
        }
    }
}
```
