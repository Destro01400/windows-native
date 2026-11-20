# Graphics, Capture, Low-Latency Audio, Devices & Windows AI (.NET 9/10)

> **Scope:** Custom rendering decision ladder (WPF `DrawingContext`, `WriteableBitmap`, `SkiaSharp.Views.WPF`, `Win2D`, `D3DImage`, `SwapChainPanel`, `DirectComposition`), **Windows Graphics Capture** (`GraphicsCapturePicker`, `Direct3D11CaptureFramePool`, `IsBorderRequired`, `WindowId` / `HWND` interop), **WASAPI** low-latency audio & loopback capture (`NAudio` traps + `IMMNotificationClient` resilience + per-process loopback), **Serial / HID / Bluetooth LE** hardware integration, and on-device **Windows AI** (`Microsoft.ML.OnnxRuntime.DirectML` and `Microsoft.Windows.AI`).
>
> **Related:** See [winui3-and-cppwinrt-native.md](winui3-and-cppwinrt-native.md#11-pure-modern-win32--directcomposition--direct2d-skeleton--2-mb-utilities) for pure C++ Direct2D/DirectComposition pipelines, [windows-os-and-cswin32.md](windows-os-and-cswin32.md#5-hardware-audio-routing-startup--power-events) for `WM_DEVICECHANGE` and power events, and [compiler-traps-and-compat.md](compiler-traps-and-compat.md) for Windows build compatibility (`19041`–`26100`).

## Table of Contents

1. [Custom GPU Rendering Decision Ladder](#1-custom-gpu-rendering-decision-ladder)
2. [Windows Graphics Capture (`Windows.Graphics.Capture`)](#2-windows-graphics-capture-windowsgraphicscapture)
3. [WASAPI Low-Latency Audio, Loopback & Device-Switch Resilience](#3-wasapi-low-latency-audio-loopback--device-switch-resilience)
4. [Device & Hardware Integration (`SerialPort`, HID & Bluetooth LE)](#4-device--hardware-integration-serialport-hid--bluetooth-le)
5. [On-Device Windows AI (`ONNX Runtime DirectML` & `Microsoft.Windows.AI`)](#5-on-device-windows-ai-onnx-runtime-directml--microsoftwindowsai)

---

## 1. Custom GPU Rendering Decision Ladder

Choose the **simplest** rendering tier that satisfies frame-rate and pixel-pipeline needs; moving lower increases interop surface and device-loss complexity.

| Tier | Stack & Primary API | Render Thread / Backing | Best Use Cases | Key Production Pitfall |
|---|---|---|---|---|
| **1. Retained Vector** | WPF `DrawingContext` (`OnRender` / `DrawingVisual`) | UI thread records commands; WPF MIL rasterizes on GPU | Custom charts, overlays, `< ~5k` vector shapes | Recording thousands of un-frozen geometries every frame stalls UI layout. |
| **2. CPU Pixel Buffer** | WPF `WriteableBitmap` (`Lock` / `AddDirtyRect` / `Unlock`) | CPU memory copied to D3D texture on UI thread | Video decode frames, heatmaps, software raytracers | `BackBufferStride` can exceed `PixelWidth * 4`; row-by-row copy required. |
| **3. Cross-Plat 2D** | `SkiaSharp.Views.WPF` (`SKElement` / `SKGLElement`) | `SKElement` (CPU) or `SKGLElement` (OpenGL `GRContext`) | Shared 2D rendering, complex vector shaders, SVG/Lottie | `SKGLElement` OpenGL drivers flake on RDP/older iGPUs; keep `SKElement` fallback. |
| **4. WinUI 3 Hardware 2D** | `Microsoft.Graphics.Win2D` (`CanvasControl` / `CanvasAnimatedControl`) | Direct2D over `ID2D1DeviceContext` | WinUI 3 custom graphs, effects, blurs, `60–120 Hz` loops | Unloading a `Page` without `canvas.RemoveFromVisualTree()` leaks the visual tree. |
| **5. WPF DX Interop** | `System.Windows.Interop.D3DImage` | Direct3D9Ex shared DXGI surface (`D3D11` -> `D3D9Ex`) | High-FPS 3D/video shaders inside WPF visual tree | Lock screen/RDP drops `IsFrontBufferAvailable`; pause loop & rebuild surface. |
| **6. WinUI 3 DX Surface** | `SwapChainPanel` (`ISwapChainPanelNative.SetSwapChain`) | Direct3D 11/12 `IDXGISwapChain` | 3D engines, capture previews, zero-copy video | Size swap chain in physical pixels (`RasterizationScale`), not DIPs. |
| **7. Zero-Framework Native** | Pure Win32 + `DirectComposition` (`WS_EX_NOREDIRECTIONBITMAP`) | `CreateSwapChainForComposition` + `IDCompositionDevice` | Sub-10 MB overlays, custom compositors | Manual `WM_DPICHANGED`, `ResizeBuffers`, and swap-chain presentation loop. |

### 1.1 WPF `WriteableBitmap`, `D3DImage` & `SkiaSharp.Views.WPF`

```csharp
// NuGet: SkiaSharp.Views.WPF (>= 3.119.0) | Target: net10.0-windows10.0.26100.0 (<AllowUnsafeBlocks>true</AllowUnsafeBlocks>)
using System;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using SkiaSharp;
using SkiaSharp.Views.WPF;

namespace MyApp.Graphics;

public static class WpfFrameRenderers
{
    public static void BlitBgraFrame(WriteableBitmap bitmap, ReadOnlySpan<byte> bgraPixels, int sourceStride)
    {
        bitmap.Lock();
        try
        {
            int dstStride = bitmap.BackBufferStride, rowBytes = Math.Min(sourceStride, dstStride);
            unsafe
            {
                byte* dst = (byte*)bitmap.BackBuffer;
                fixed (byte* src = bgraPixels)
                    for (int y = 0; y < bitmap.PixelHeight; y++)
                        Buffer.MemoryCopy(src + (long)y * sourceStride, dst + (long)y * dstStride, dstStride, rowBytes);
            }
            bitmap.AddDirtyRect(new Int32Rect(0, 0, bitmap.PixelWidth, bitmap.PixelHeight));
        }
        finally { bitmap.Unlock(); }
    }

    public static SKElement CreateDpiAwareSkiaCanvas()
    {
        var element = new SKElement { IgnorePixelScaling = false };
        element.PaintSurface += (_, e) =>
        {
            e.Surface.Canvas.Clear(SKColors.Transparent);
            using var paint = new SKPaint { Color = new SKColor(0x00, 0x78, 0xD4), IsAntialias = true };
            e.Surface.Canvas.DrawCircle(e.Info.Width / 2f, e.Info.Height / 2f, Math.Min(e.Info.Width, e.Info.Height) * 0.25f, paint);
        };
        return element;
    }
}

public sealed class D3D9SharedSurfaceHost : IDisposable
{
    private readonly D3DImage _d3dImage = new();
    private bool _renderingHooked;
    public D3DImage ImageSource => _d3dImage;

    public void Attach() { _d3dImage.IsFrontBufferAvailableChanged += OnFrontBufferChanged; if (_d3dImage.IsFrontBufferAvailable) SetRenderLoop(true); }
    private void OnFrontBufferChanged(object s, DependencyPropertyChangedEventArgs e) => SetRenderLoop(_d3dImage.IsFrontBufferAvailable);

    private void SetRenderLoop(bool enable)
    {
        if (enable == _renderingHooked) return;
        if (enable) CompositionTarget.Rendering += OnRender; else CompositionTarget.Rendering -= OnRender;
        _renderingHooked = enable;
    }

    private void OnRender(object? sender, EventArgs e)
    {
        nint pSharedD3D9Surface = GetOrRenderSharedD3D9Surface(); // D3D11_RESOURCE_MISC_SHARED -> D3D9Ex CreateSharedSurface
        if (!_d3dImage.IsFrontBufferAvailable || pSharedD3D9Surface == 0) return;
        _d3dImage.Lock();
        try
        {
            _d3dImage.SetBackBuffer(D3DResourceType.IDirect3DSurface9, pSharedD3D9Surface);
            if (_d3dImage.PixelWidth > 0 && _d3dImage.PixelHeight > 0)
                _d3dImage.AddDirtyRect(new Int32Rect(0, 0, _d3dImage.PixelWidth, _d3dImage.PixelHeight));
        }
        finally { _d3dImage.Unlock(); }
    }

    private static nint GetOrRenderSharedD3D9Surface() => 0;
    public void Dispose() { SetRenderLoop(false); _d3dImage.IsFrontBufferAvailableChanged -= OnFrontBufferChanged; }
}
```

### 1.2 WinUI 3 `Win2D` (`CanvasControl`) & `SwapChainPanel` Interop

Use `CanvasControl` for event-driven drawing (`Invalidate()`) and `CanvasAnimatedControl` / `CanvasSwapChainPanel` for independent 60/120 FPS render loops outside XAML layout passes.

```csharp
// NuGet: Microsoft.WindowsAppSDK (>= 1.8 / 2.7.0), Microsoft.Graphics.Win2D (>= 1.4.0)
using System.Runtime.InteropServices;
using Microsoft.Graphics.Canvas.UI.Xaml;
using Microsoft.UI;
using Microsoft.UI.Xaml.Controls;
using WinRT;

namespace MyApp.WinUiGraphics;

public static class Win2DLifecycleHelper
{
    public static void AttachAndGuardLeak(Page page, CanvasControl canvas)
    {
        canvas.Draw += OnCanvasDraw;
        page.Unloaded += (_, _) => { canvas.Draw -= OnCanvasDraw; canvas.RemoveFromVisualTree(); }; // Breaks WinUI 3 visual-tree leak
    }

    private static void OnCanvasDraw(CanvasControl sender, CanvasDrawEventArgs args)
    {
        args.DrawingSession.Clear(Colors.Transparent);
        args.DrawingSession.FillCircle(64f, 64f, 32f, Colors.DodgerBlue);
    }

    [ComImport, Guid("63aad0b8-7c24-40ff-85a8-640d944cc325"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface ISwapChainPanelNative { int SetSwapChain(nint swapChain); }

    public static void BindDxgiSwapChain(SwapChainPanel panel, nint dxgiSwapChainPtr) =>
        Marshal.ThrowExceptionForHR(panel.As<ISwapChainPanelNative>().SetSwapChain(dxgiSwapChainPtr));
}
```

---

## 2. Windows Graphics Capture (`Windows.Graphics.Capture`)

### 2.1 Picker vs. Programmatic Window Capture & Borderless Guard

| Scenario | API Path | OS / Manifest Requirement | Unpackaged Trap |
|---|---|---|---|
| **User picks window/monitor** | `GraphicsCapturePicker` + `InitializeWithWindow.Initialize(picker, hwnd)` | Windows 10 1903+ (`18362+`), zero extra capability | Calling `PickSingleItemAsync()` without `InitializeWithWindow` throws `COMException`. |
| **Known `HWND` (all builds)** | `GraphicsCaptureItem.As<IGraphicsCaptureItemInterop>().CreateForWindow` | Windows 10 1903+, works unpackaged without restricted caps | Never use removed `.NET Framework` `WindowsRuntimeMarshal`; use `CsWinRT` `.As<T>()` + `.FromAbi()`. |
| **Known `WindowId` (modern)** | `GraphicsCaptureItem.TryCreateFromWindowId(new Windows.UI.WindowId(...))` | Build `20348+`, `graphicsCaptureProgrammatic` + `RequestAccessAsync` | `Win32Interop.GetWindowIdFromWindow` returns `Microsoft.UI.WindowId`; convert `.Value` to `Windows.UI.WindowId`. |
| **Hide yellow capture border** | `session.IsBorderRequired = false` | Build `20348+`, `graphicsCaptureWithoutBorder` + `RequestAccessAsync` | Calling on Win10 `19045` throws `E_NOINTERFACE` (`0x80004002`); always guard with `ApiInformation.IsPropertyPresent`. |

### 2.2 Production `Direct3D11CaptureFramePool` Service (`CsWinRT` / `.NET 10`)

```csharp
using System;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using Windows.Foundation.Metadata;
using Windows.Graphics;
using Windows.Graphics.Capture;
using Windows.Graphics.DirectX;
using Windows.Graphics.DirectX.Direct3D11;
using Windows.Security.Authorization.AppCapabilityAccess;
using WinRT;
using WinRT.Interop;

namespace MyApp.Capture;

[ComImport, System.Runtime.InteropServices.Guid("3628E81B-3CAC-4C60-B7F4-23CE0E0C3356"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
internal interface IGraphicsCaptureItemInterop { int CreateForWindow(nint window, ref Guid riid, out nint result); int CreateForMonitor(nint monitor, ref Guid riid, out nint result); }

[ComImport, System.Runtime.InteropServices.Guid("A9B3D012-3DF2-4EE3-B8D1-8695F457D3C1"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
internal interface IDirect3DDxgiInterfaceAccess { int GetInterface(ref Guid riid, out nint pInterface); }

public sealed partial class WindowCaptureSession : IDisposable
{
    private static readonly Guid CaptureItemIid = new("79C3F95B-31F7-4EC2-A464-632EF5D30760");
    private static readonly Guid Texture2DIid = new("6F15AAF2-D208-4E89-9AB4-489535D34F9C");
    private readonly IDirect3DDevice _d3dDevice;
    private Direct3D11CaptureFramePool? _framePool;
    private GraphicsCaptureSession? _session;
    private SizeInt32 _lastSize;
    public event Action<nint, SizeInt32>? TextureFrameReady;

    public WindowCaptureSession(nint nativeDxgiDevice)
    {
        Marshal.ThrowExceptionForHR(CreateDirect3D11DeviceFromDXGIDevice(nativeDxgiDevice, out nint inspectable));
        try { _d3dDevice = MarshalInterface<IDirect3DDevice>.FromAbi(inspectable); }
        finally { Marshal.Release(inspectable); }
    }

    public static async Task<GraphicsCaptureItem?> PickItemAsync(nint ownerHwnd)
    {
        var picker = new GraphicsCapturePicker();
        InitializeWithWindow.Initialize(picker, ownerHwnd);
        return await picker.PickSingleItemAsync();
    }

    public static GraphicsCaptureItem CreateItemFromHwnd(nint hwnd)
    {
        Guid iid = CaptureItemIid;
        Marshal.ThrowExceptionForHR(GraphicsCaptureItem.As<IGraphicsCaptureItemInterop>().CreateForWindow(hwnd, ref iid, out nint abi));
        try { return GraphicsCaptureItem.FromAbi(abi); } finally { Marshal.Release(abi); }
    }

    public async Task StartAsync(GraphicsCaptureItem item, bool requestBorderless = false)
    {
        _lastSize = item.Size;
        _framePool = Direct3D11CaptureFramePool.CreateFreeThreaded(_d3dDevice, DirectXPixelFormat.B8G8R8A8UIntNormalized, 2, _lastSize);
        _framePool.FrameArrived += OnFrameArrived;
        _session = _framePool.CreateCaptureSession(item);
        if (requestBorderless && ApiInformation.IsPropertyPresent("Windows.Graphics.Capture.GraphicsCaptureSession", "IsBorderRequired") &&
            await GraphicsCaptureAccess.RequestAccessAsync(GraphicsCaptureAccessKind.Borderless) == AppCapabilityAccessStatus.Allowed)
            _session.IsBorderRequired = false;
        _session.StartCapture();
    }

    private void OnFrameArrived(Direct3D11CaptureFramePool sender, object args)
    {
        using Direct3D11CaptureFrame? frame = sender.TryGetNextFrame(); // Dispose immediately or pool stalls
        if (frame is null) return;
        if (frame.ContentSize.Width != _lastSize.Width || frame.ContentSize.Height != _lastSize.Height)
        {
            _lastSize = frame.ContentSize;
            sender.Recreate(_d3dDevice, DirectXPixelFormat.B8G8R8A8UIntNormalized, 2, _lastSize);
        }
        Guid texIid = Texture2DIid;
        Marshal.ThrowExceptionForHR(frame.Surface.As<IDirect3DDxgiInterfaceAccess>().GetInterface(ref texIid, out nint texPtr));
        try { TextureFrameReady?.Invoke(texPtr, frame.ContentSize); } finally { Marshal.Release(texPtr); }
    }

    public void Dispose() { if (_framePool is not null) { _framePool.FrameArrived -= OnFrameArrived; _framePool.Dispose(); _framePool = null; } _session?.Dispose(); _session = null; _d3dDevice.Dispose(); }

    [LibraryImport("d3d11.dll")]
    private static partial int CreateDirect3D11DeviceFromDXGIDevice(nint dxgiDevice, out nint graphicsDevice);
}
```

---

## 3. WASAPI Low-Latency Audio, Loopback & Device-Switch Resilience

See [windows-os-and-cswin32.md](windows-os-and-cswin32.md#53-windows-audio-routing--wasapi--naudio-device-change-traps) for `IMMNotificationClient` COM thread rules. Four production traps dominate `NAudio` (`WasapiCapture` / `WasapiLoopbackCapture`):

1. **Loopback Silence Paradox:** `WasapiLoopbackCapture` **stops firing `DataAvailable` completely** when no audio plays on the render endpoint—causing severe A/V drift when mixed with continuous mic input.
   - *Fix A (Recommended):* Pipe mic and loopback streams into separate `BufferedWaveProvider` instances with **`ReadFully = true`** so silent intervals emit zeroed PCM frames synchronously.
   - *Fix B (Keep-Alive):* Open a silent `WasapiOut` playing `SilenceProvider(capture.WaveFormat)` only during active capture.
2. **Shared-Mode `WaveFormat` Mismatch:** `AudioClientShareMode.Shared` always runs at the Windows mixer's native format (usually 32-bit IEEE float, 48 kHz stereo); resample downstream via `WdlResamplingSampleProvider` / `MediaFoundationResampler`.
3. **Default-Device Switch Bursts:** Headset hot-plugging fires **3 consecutive** `OnDefaultDeviceChanged` callbacks (`Console`, `Multimedia`, `Communications`) on Core Audio MTA threads. Debounce `150–250 ms`, hold strong references to `MMDeviceEnumerator` + `IMMNotificationClient`, and handle `RecordingStopped` errors cleanly.
4. **Per-Process Loopback (Win10 `20348+` / Win11):** To capture or exclude one PID tree without OS chimes, invoke `ActivateAudioInterfaceAsync` with `VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK` and `AUDIOCLIENT_ACTIVATION_PARAMS` (`AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK`, `PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE` / `EXCLUDE`).

```csharp
// NuGet: NAudio (>= 2.2.1)
using System;
using System.Threading;
using NAudio.CoreAudioApi;
using NAudio.CoreAudioApi.Interfaces;
using NAudio.Wave;

namespace MyApp.Audio;

public sealed class ResilientAudioCapture : IMMNotificationClient, IDisposable
{
    private readonly MMDeviceEnumerator _enumerator = new();
    private readonly DataFlow _flow;
    private readonly Lock _gate = new();
    private WasapiCapture? _capture;
    private Timer? _reinitDebounce;
    private bool _running, _disposed;
    public event EventHandler<WaveInEventArgs>? FrameReceived;

    public ResilientAudioCapture(DataFlow flow = DataFlow.Capture) { _flow = flow; _enumerator.RegisterEndpointNotificationCallback(this); }
    public void Start() { lock (_gate) { ObjectDisposedException.ThrowIf(_disposed, this); _running = true; StartInternal(); } }

    private void StartInternal()
    {
        StopCaptureOnly();
        MMDevice device = _enumerator.GetDefaultAudioEndpoint(_flow, Role.Multimedia);
        _capture = _flow == DataFlow.Render
            ? new WasapiLoopbackCapture(device)
            : new WasapiCapture(device, useEventSync: true, audioBufferMillisecondsLength: 20);
        _capture.DataAvailable += (_, e) => FrameReceived?.Invoke(this, e);
        _capture.RecordingStopped += (_, e) => { if (e.Exception is not null && _running && !_disposed) ScheduleReinit(); };
        _capture.StartRecording();
    }

    public void OnDefaultDeviceChanged(DataFlow flow, Role role, string id) { if (flow == _flow && _running && !_disposed) ScheduleReinit(); }
    public void OnDeviceStateChanged(string id, DeviceState state) { } public void OnDeviceAdded(string id) { }
    public void OnDeviceRemoved(string id) { } public void OnPropertyValueChanged(string id, PropertyKey key) { }

    private void ScheduleReinit()
    {
        lock (_gate)
        {
            if (_disposed) return;
            _reinitDebounce ??= new Timer(_ => { lock (_gate) { if (_running && !_disposed) StartInternal(); } }, null, Timeout.Infinite, Timeout.Infinite);
            _reinitDebounce.Change(dueTime: 200, period: Timeout.Infinite);
        }
    }

    private void StopCaptureOnly()
    {
        if (_capture is null) return;
        try { _capture.StopRecording(); } catch { /* Unplugged endpoints can throw on stop */ }
        _capture.Dispose(); _capture = null;
    }

    public void Dispose()
    {
        lock (_gate) { if (_disposed) return; _disposed = true; _running = false; _reinitDebounce?.Dispose(); StopCaptureOnly(); _enumerator.UnregisterEndpointNotificationCallback(this); _enumerator.Dispose(); }
    }

    public static (BufferedWaveProvider Mic, BufferedWaveProvider Loopback) CreateAlignedBuffers(WaveFormat format) =>
        (new BufferedWaveProvider(format) { ReadFully = true, DiscardOnBufferOverflow = true },
         new BufferedWaveProvider(format) { ReadFully = true, DiscardOnBufferOverflow = true });

    public static WasapiOut StartSilentKeepAlive(WaveFormat format)
    {
        var output = new WasapiOut(AudioClientShareMode.Shared, useEventSync: true, latency: 100);
        output.Init(new SilenceProvider(format)); output.Play();
        return output;
    }
}
```

---

## 4. Device & Hardware Integration (`SerialPort`, HID & Bluetooth LE)

| Transport | API / Package | Critical Trap | Production Pattern |
|---|---|---|---|
| **Serial / USB-CDC** | `System.IO.Ports.SerialPort` (`10.0+`) or WinRT `SerialDevice` | `DataReceived` calling `Dispatcher.Invoke` deadlocks `Close()`; `BaseStream.ReadAsync` ignores `ReadTimeout`. | Never mix `DataReceived` with `BaseStream.ReadAsync`; pass `CancellationToken`, enable `DtrEnable`/`RtsEnable` for MCUs, catch `IOException` on unplug. |
| **USB / Bluetooth HID** | `Windows.Devices.HumanInterfaceDevice.HidDevice` | Windows reserves keyboard/mouse usage pages (`0x01`/`0x02`/`0x06`), returning `null` from `FromIdAsync`. | Query vendor-defined usage pages (`0xFF00+`) via `GetDeviceSelector`, guard `null` return, declare `humaninterfacedevice` capability if packaged. |
| **Bluetooth LE** | `Windows.Devices.Bluetooth` | GC collecting `BluetoothLEDevice`/`GattCharacteristic` silently drops `ValueChanged`; GATT cache hides firmware updates. | Keep strong instance fields for `BluetoothLEDevice`, `GattDeviceService`, and `GattCharacteristic`; query `BluetoothCacheMode.Uncached`; `Dispose()` on disconnect. |

```csharp
// NuGet: System.IO.Ports (>= 10.0.15)
using System;
using System.IO;
using System.IO.Ports;
using System.Threading;
using System.Threading.Tasks;
using Windows.Devices.Bluetooth;
using Windows.Devices.Bluetooth.Advertisement;
using Windows.Devices.Bluetooth.GenericAttributeProfile;
using Windows.Devices.Enumeration;
using Windows.Devices.HumanInterfaceDevice;
using Windows.Storage;
using Windows.Storage.Streams;

namespace MyApp.Devices;

public sealed class AsyncSerialReader : IDisposable
{
    private readonly SerialPort _port;
    private readonly CancellationTokenSource _cts = new();

    public AsyncSerialReader(string portName, int baudRate = 115200) =>
        _port = new SerialPort(portName, baudRate) { DtrEnable = true, RtsEnable = true, ReadTimeout = 500 };

    public async Task ReadLoopAsync(Func<ReadOnlyMemory<byte>, Task> onPacket, CancellationToken externalCt)
    {
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(_cts.Token, externalCt);
        _port.Open();
        byte[] buffer = new byte[1024];
        try
        {
            while (!linked.Token.IsCancellationRequested)
            {
                int read = await _port.BaseStream.ReadAsync(buffer, linked.Token); // Ignores ReadTimeout -> use CT
                if (read == 0) break;
                await onPacket(buffer.AsMemory(0, read));
            }
        }
        catch (OperationCanceledException) { }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { /* USB dongle unplugged */ }
    }
    public void Dispose() { _cts.Cancel(); if (_port.IsOpen) _port.Close(); _port.Dispose(); _cts.Dispose(); }
}

public sealed class HidAndBleBridge : IDisposable
{
    private HidDevice? _hid;
    private BluetoothLEDevice? _bleDevice;
    private GattDeviceService? _bleService;
    private GattCharacteristic? _bleNotifyChar;
    public event Action<byte, byte[]>? HidReportReceived;
    public event Action<byte[]>? BleNotificationReceived;

    public async Task<bool> OpenHidAsync(ushort usagePage, ushort usageId, ushort vendorId, ushort productId)
    {
        var devices = await DeviceInformation.FindAllAsync(HidDevice.GetDeviceSelector(usagePage, usageId, vendorId, productId));
        if (devices.Count == 0) return false;
        _hid = await HidDevice.FromIdAsync(devices[0].Id, FileAccessMode.Read);
        if (_hid is null) return false;
        _hid.InputReportReceived += (_, args) => HidReportReceived?.Invoke((byte)args.Report.Id, ReadBuffer(args.Report.Data));
        return true;
    }

    public async Task<bool> ConnectBleNotifyAsync(ulong address, Guid serviceUuid, Guid charUuid)
    {
        _bleDevice = await BluetoothLEDevice.FromBluetoothAddressAsync(address);
        if (_bleDevice is null) return false;
        var svc = await _bleDevice.GetGattServicesForUuidAsync(serviceUuid, BluetoothCacheMode.Uncached);
        if (svc.Status != GattCommunicationStatus.Success || svc.Services.Count == 0) return false;
        _bleService = svc.Services[0];
        var ch = await _bleService.GetCharacteristicsForUuidAsync(charUuid, BluetoothCacheMode.Uncached);
        if (ch.Status != GattCommunicationStatus.Success || ch.Characteristics.Count == 0) return false;
        _bleNotifyChar = ch.Characteristics[0];
        _bleNotifyChar.ValueChanged += OnBleValueChanged;
        return await _bleNotifyChar.WriteClientCharacteristicConfigurationDescriptorAsync(
            GattClientCharacteristicConfigurationDescriptorValue.Notify) == GattCommunicationStatus.Success;
    }

    public static BluetoothLEAdvertisementWatcher CreatePassiveScanner(Action<ulong, short> onAdv)
    {
        var watcher = new BluetoothLEAdvertisementWatcher { ScanningMode = BluetoothLEScanningMode.Passive };
        watcher.Received += (_, a) => onAdv(a.BluetoothAddress, a.RawSignalStrengthInDBm);
        return watcher;
    }

    private void OnBleValueChanged(GattCharacteristic s, GattValueChangedEventArgs a) => BleNotificationReceived?.Invoke(ReadBuffer(a.CharacteristicValue));
    private static byte[] ReadBuffer(IBuffer buf) { using var r = DataReader.FromBuffer(buf); byte[] d = new byte[buf.Length]; r.ReadBytes(d); return d; }
    public void Dispose() { _hid?.Dispose(); _hid = null; if (_bleNotifyChar is not null) { _bleNotifyChar.ValueChanged -= OnBleValueChanged; _bleNotifyChar = null; } _bleService?.Dispose(); _bleService = null; _bleDevice?.Dispose(); _bleDevice = null; }
}
```

---

## 5. On-Device Windows AI (`ONNX Runtime DirectML` & `Microsoft.Windows.AI`)

### 5.1 `Microsoft.ML.OnnxRuntime.DirectML` (GPU/NPU + Clean CPU Fallback)

- **Package Conflict Rule:** Install **`Microsoft.ML.OnnxRuntime.DirectML`** *alone* — never reference `Microsoft.ML.OnnxRuntime` (CPU package) in the same project or native `onnxruntime.dll` exports collide.
- **Mandatory DirectML Flags:** Set `EnableMemoryPattern = false` and `ExecutionMode = ExecutionMode.ORT_SEQUENTIAL` before `AppendExecutionProvider_DML(deviceId)`.
- **Session Lifetime:** Treat `InferenceSession` as a thread-safe singleton (`Run()` is thread-safe; construction compiles graphs). Dispose `IDisposableReadOnlyCollection<DisposableNamedOnnxValue>`.

```csharp
// NuGet: Microsoft.ML.OnnxRuntime.DirectML (>= 1.24.4)
using System;
using System.Collections.Generic;
using Microsoft.ML.OnnxRuntime;
using Microsoft.ML.OnnxRuntime.Tensors;

namespace MyApp.AI;

public sealed class DirectMlOnnxRunner : IDisposable
{
    public InferenceSession Session { get; }
    public bool UsingDirectMl { get; }
    public DirectMlOnnxRunner(string modelPath, int dmlDeviceId = 0) => (Session, UsingDirectMl) = CreateSession(modelPath, dmlDeviceId);

    private static (InferenceSession Session, bool IsDirectMl) CreateSession(string modelPath, int deviceId)
    {
        try
        {
            using var dml = new SessionOptions { GraphOptimizationLevel = GraphOptimizationLevel.ORT_ENABLE_ALL, EnableMemoryPattern = false, ExecutionMode = ExecutionMode.ORT_SEQUENTIAL };
            dml.AppendExecutionProvider_DML(deviceId);
            return (new InferenceSession(modelPath, dml), true);
        }
        catch (Exception) { using var cpu = new SessionOptions { GraphOptimizationLevel = GraphOptimizationLevel.ORT_ENABLE_ALL, EnableMemoryPattern = true }; return (new InferenceSession(modelPath, cpu), false); }
    }

    public float[] RunFloatTensor(string inputName, string outputName, float[] inputData, int[] dimensions)
    {
        using IDisposableReadOnlyCollection<DisposableNamedOnnxValue> results = Session.Run(
            new List<NamedOnnxValue> { NamedOnnxValue.CreateFromTensor(inputName, new DenseTensor<float>(inputData, dimensions)) });
        foreach (var item in results) if (item.Name == outputName) return item.AsTensor<float>().ToArray();
        throw new InvalidOperationException($"Output tensor '{outputName}' not found.");
    }
    public void Dispose() => Session.Dispose();
}
```

### 5.2 `Microsoft.Windows.AI` (Phi Silica, OCR & Imaging Readiness Pattern)

`Microsoft.Windows.AI` (`Microsoft.WindowsAppSDK.AI` + `Microsoft.WindowsAppSDK`) requires MSIX/Sparse package identity declaring `<uap3:Capability Name="systemAIModels" />` (`MaxVersionTested="10.0.26226.0"`+) and supported Windows 11 / Copilot+ PC hardware for NPU features like Phi Silica (`LanguageModel`). Always check `GetReadyState()` -> `EnsureReadyAsync()` when `NotReady` -> fall back cleanly to DirectML/CPU ONNX when `NotSupportedOnCurrentSystem` or `DisabledByUser`.

```csharp
// NuGet: Microsoft.WindowsAppSDK (>= 1.8 / 2.7.0), Microsoft.WindowsAppSDK.AI (>= 1.8 / 2.7.0)
using System;
using System.Text;
using System.Threading.Tasks;
using Microsoft.Graphics.Imaging;
using Microsoft.Windows.AI;
using Microsoft.Windows.AI.Imaging;
using Microsoft.Windows.AI.Text;
using Windows.Foundation;
using Windows.Graphics;
using Windows.Graphics.Imaging;

namespace MyApp.WindowsAi;

public static class WindowsAiGateways
{
    private static async Task<bool> EnsureReadyAsync(Func<AIFeatureReadyState> getState, Func<IAsyncOperationWithProgress<AIFeatureReadyResult, double>> ensure)
    {
        AIFeatureReadyState state = getState();
        if (state == AIFeatureReadyState.NotReady && (await ensure()).Status == AIFeatureReadyResultState.Success) state = getState();
        return state == AIFeatureReadyState.Ready;
    }

    public static async Task<string?> TryGenerateWithPhiSilicaAsync(string prompt)
    {
        if (!await EnsureReadyAsync(LanguageModel.GetReadyState, LanguageModel.EnsureReadyAsync)) return null;
        using LanguageModel model = await LanguageModel.CreateAsync();
        return (await model.GenerateResponseAsync(prompt)).Text;
    }

    public static async Task<string?> TryRecognizeTextAsync(SoftwareBitmap bitmap)
    {
        if (!await EnsureReadyAsync(TextRecognizer.GetReadyState, TextRecognizer.EnsureReadyAsync)) return null;
        using TextRecognizer recognizer = await TextRecognizer.CreateAsync();
        using ImageBuffer imageBuffer = ImageBuffer.CreateForSoftwareBitmap(bitmap);
        var sb = new StringBuilder();
        foreach (var line in recognizer.RecognizeTextFromImage(imageBuffer).Lines) sb.AppendLine(line.Text);
        return sb.ToString();
    }

    public static async Task<SoftwareBitmap?> TryScaleImageAsync(SoftwareBitmap bitmap, int width, int height)
    {
        if (!await EnsureReadyAsync(ImageScaler.GetReadyState, ImageScaler.EnsureReadyAsync)) return null;
        using ImageScaler scaler = await ImageScaler.CreateAsync();
        return scaler.ScaleSoftwareBitmap(bitmap, width, height);
    }

    public static async Task<SoftwareBitmap?> TryExtractObjectMaskAsync(SoftwareBitmap bitmap, int includeX, int includeY)
    {
        if (!await EnsureReadyAsync(ImageObjectExtractor.GetReadyState, ImageObjectExtractor.EnsureReadyAsync)) return null;
        using ImageObjectExtractor extractor = await ImageObjectExtractor.CreateWithSoftwareBitmapAsync(bitmap);
        return extractor.GetSoftwareBitmapObjectMask(new ImageObjectExtractorHint(Array.Empty<RectInt32>(), new[] { new PointInt32(includeX, includeY) }, Array.Empty<PointInt32>())); // Gray8 mask
    }
}
```
