using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using WinRT;

namespace {{NAMESPACE}}.ViewModels;

[GeneratedBindableCustomProperty]
public sealed partial class WorkspaceItem : ObservableObject
{
    [ObservableProperty]
    public partial string Title { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string Detail { get; set; } = string.Empty;
}

[GeneratedBindableCustomProperty]
public sealed partial class MainViewModel : ObservableObject
{
    [ObservableProperty]
    public partial string InputText { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string StatusText { get; set; } = "Ready";

    public IRelayCommand AddItemCommand { get; }

    public IRelayCommand ClearStatusCommand { get; }

    public ObservableCollection<WorkspaceItem> Items { get; } =
    [
        new WorkspaceItem { Title = "NativeAOT + CsWinRT 2.2", Detail = "Zero-reflection compiled x:Bind bindings" },
        new WorkspaceItem { Title = "Single-instance AppInstance", Detail = "Activation redirection before XAML startup" },
        new WorkspaceItem { Title = "MicaBackdrop & Custom TitleBar", Detail = "AppWindow.TitleBar with Tall height option" },
    ];

    public MainViewModel()
    {
        AddItemCommand = new RelayCommand(AddItem, CanAddItem);
        ClearStatusCommand = new RelayCommand(ClearStatus);
    }

    partial void OnInputTextChanged(string value) => AddItemCommand.NotifyCanExecuteChanged();

    private bool CanAddItem() => !string.IsNullOrWhiteSpace(InputText);

    private void AddItem()
    {
        string trimmed = InputText.Trim();
        Items.Insert(0, new WorkspaceItem { Title = trimmed, Detail = "Added at runtime" });
        StatusText = $"Added \"{trimmed}\"";
        InputText = string.Empty;
    }

    private void ClearStatus()
    {
        StatusText = "Ready";
    }
}
