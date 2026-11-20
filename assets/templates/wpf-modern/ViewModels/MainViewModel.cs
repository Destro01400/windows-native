using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using {{NAMESPACE}}.Motion;

namespace {{NAMESPACE}}.ViewModels;

/// <summary>
/// Primary view model for the starter application window.
/// </summary>
public sealed partial class MainViewModel : ObservableObject
{
    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(AddItemCommand))]
    public partial string InputText { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string StatusText { get; set; } = "Ready";

    public string AppTitle => "{{APP_NAME}}";

    public MotionSettings Motion => MotionSettings.Instance;

    public ObservableCollection<string> Items { get; } =
    [
        "PerMonitorV2 DPI awareness enabled",
        "WindowChrome with HTMAXBUTTON Snap Layouts",
        "Generic Host DI & CommunityToolkit.Mvvm 8.4.2",
    ];

    private bool CanAddItem() => !string.IsNullOrWhiteSpace(InputText);

    [RelayCommand(CanExecute = nameof(CanAddItem))]
    private void AddItem()
    {
        string trimmed = InputText.Trim();
        Items.Insert(0, trimmed);
        StatusText = $"Added \"{trimmed}\"";
        InputText = string.Empty;
    }

    [RelayCommand]
    private void ClearStatus()
    {
        StatusText = "Ready";
    }
}
