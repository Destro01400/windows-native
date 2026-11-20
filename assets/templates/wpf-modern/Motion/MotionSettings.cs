using System;
using System.ComponentModel;
using System.Windows;
using System.Windows.Media;
using CommunityToolkit.Mvvm.ComponentModel;

namespace {{NAMESPACE}}.Motion;

/// <summary>
/// Tracks Windows reduced-motion and hardware rendering tier settings.
/// </summary>
public sealed partial class MotionSettings : ObservableObject, IDisposable
{
    public static MotionSettings Instance { get; } = new();

    private bool _appReducedMotionOverride;
    private bool _disposed;

    [ObservableProperty]
    public partial bool IsReducedMotion { get; set; }

    public bool AllowMotion => !IsReducedMotion;

    private MotionSettings()
    {
        Refresh();
        SystemParameters.StaticPropertyChanged += OnSystemParametersChanged;
        RenderCapability.TierChanged += OnTierChanged;
    }

    public bool AppReducedMotionOverride
    {
        get => _appReducedMotionOverride;
        set
        {
            if (_appReducedMotionOverride != value)
            {
                _appReducedMotionOverride = value;
                Refresh();
            }
        }
    }

    private void OnSystemParametersChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName is nameof(SystemParameters.ClientAreaAnimation) or null)
        {
            Application.Current?.Dispatcher.BeginInvoke(Refresh);
        }
    }

    private void OnTierChanged(object? sender, EventArgs e) =>
        Application.Current?.Dispatcher.BeginInvoke(Refresh);

    private void Refresh()
    {
        bool reduced = _appReducedMotionOverride
                       || !SystemParameters.ClientAreaAnimation
                       || (RenderCapability.Tier >> 16) == 0;
        if (reduced != IsReducedMotion)
        {
            IsReducedMotion = reduced;
            OnPropertyChanged(nameof(AllowMotion));
        }
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        SystemParameters.StaticPropertyChanged -= OnSystemParametersChanged;
        RenderCapability.TierChanged -= OnTierChanged;
    }
}
