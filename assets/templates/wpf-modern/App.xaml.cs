using System;
using System.Globalization;
using System.Threading;
using System.Windows;
using System.Windows.Documents;
using System.Windows.Markup;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using {{NAMESPACE}}.Motion;
using {{NAMESPACE}}.ViewModels;

namespace {{NAMESPACE}};

public partial class App : Application
{
    private const string InstanceMutexName = @"Local\{{NAMESPACE}}.{{APP_GUID}}.SingleInstance";

    private IHost? _host;
    private Mutex? _instanceMutex;

    private async void OnApplicationStartup(object sender, StartupEventArgs e)
    {
        _instanceMutex = new Mutex(initiallyOwned: true, InstanceMutexName, out bool createdNew);
        if (!createdNew)
        {
            _instanceMutex.Dispose();
            _instanceMutex = null;
            Shutdown(0);
            return;
        }

        // Override WPF default en-US culture metadata before constructing any UI elements.
        var xmlLanguage = XmlLanguage.GetLanguage(CultureInfo.CurrentCulture.IetfLanguageTag);
        FrameworkElement.LanguageProperty.OverrideMetadata(
            typeof(FrameworkElement),
            new FrameworkPropertyMetadata(xmlLanguage));
        FrameworkContentElement.LanguageProperty.OverrideMetadata(
            typeof(TextElement),
            new FrameworkPropertyMetadata(xmlLanguage));

        var builder = Host.CreateApplicationBuilder(e.Args);
        builder.Services.AddSingleton<MainViewModel>();
        builder.Services.AddSingleton<MainWindow>();

        _host = builder.Build();
        await _host.StartAsync();

        var mainWindow = _host.Services.GetRequiredService<MainWindow>();
        MainWindow = mainWindow;
        mainWindow.Show();
    }

    private async void OnApplicationExit(object sender, ExitEventArgs e)
    {
        if (_host is not null)
        {
            using (_host)
            {
                await _host.StopAsync(TimeSpan.FromSeconds(5));
            }

            _host = null;
        }

        MotionSettings.Instance.Dispose();

        if (_instanceMutex is not null)
        {
            GC.KeepAlive(_instanceMutex);
            _instanceMutex.Dispose();
            _instanceMutex = null;
        }
    }
}
