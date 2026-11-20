using Microsoft.UI.Xaml;
using Microsoft.Windows.AppLifecycle;
using {{NAMESPACE}}.ViewModels;

namespace {{NAMESPACE}};

public partial class App : Application
{
    private MainWindow? _window;

    public App()
    {
        InitializeComponent();
    }

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        _window = new MainWindow(new MainViewModel());
        _window.Activate();
    }

    public void BringMainWindowToFront(AppActivationArguments args)
    {
        _window?.Activate();
    }
}
