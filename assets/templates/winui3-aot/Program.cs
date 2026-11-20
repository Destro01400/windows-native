using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.Windows.AppLifecycle;
using WinRT;

namespace {{NAMESPACE}};

public static class Program
{
    private static DispatcherQueue? _uiQueue;
    private static App? _app;

    [STAThread]
    public static int Main(string[] args)
    {
        ComWrappersSupport.InitializeComWrappers();

        AppActivationArguments activationArgs = AppInstance.GetCurrent().GetActivatedEventArgs();
        AppInstance primary = AppInstance.FindOrRegisterForKey("{{NAMESPACE}}.{{APP_GUID}}");

        if (!primary.IsCurrent)
        {
            using var redirected = new AutoResetEvent(false);
            _ = Task.Run(async () =>
            {
                try
                {
                    await primary.RedirectActivationToAsync(activationArgs);
                }
                finally
                {
                    redirected.Set();
                }
            });
            redirected.WaitOne();
            return 0;
        }

        primary.Activated += OnPrimaryActivated;

        Application.Start(p =>
        {
            _uiQueue = DispatcherQueue.GetForCurrentThread();
            SynchronizationContext.SetSynchronizationContext(new DispatcherQueueSynchronizationContext(_uiQueue));
            _app = new App();
        });

        primary.Activated -= OnPrimaryActivated;
        return 0;
    }

    private static void OnPrimaryActivated(object? sender, AppActivationArguments args)
    {
        _uiQueue?.TryEnqueue(() => _app?.BringMainWindowToFront(args));
    }
}
