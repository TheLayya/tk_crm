using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;
using System.Text.Json;

namespace TkCrm.Desktop;

public sealed class MainForm : Form
{
    private const int DefaultWidth = 1440;
    private const int DefaultHeight = 900;
    private const int MinimumWidth = 1180;
    private const int MinimumHeight = 720;
    private readonly WebView2 browser = new() { Dock = DockStyle.Fill };
    private readonly string settingsPath = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "TkCRM", "desktop-window.json");
    private bool ready;
    private bool initializationCanceled;
    private ManagedServer? server;
    private UpdateAgent? updateAgent;
    private bool updateClosing;
    private readonly CancellationTokenSource startupCancellation = new();

    public MainForm()
    {
        Text = "TkCRM";
        Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        AutoScaleMode = AutoScaleMode.Dpi;
        AutoScaleDimensions = new SizeF(96F, 96F);
        StartPosition = FormStartPosition.CenterScreen;
        MinimumSize = new Size(MinimumWidth, MinimumHeight);
        ClientSize = new Size(DefaultWidth, DefaultHeight);
        LoadWindowSettings();
        FitWorkingArea();
        Controls.Add(browser);
        browser.MinimumSize = Size.Empty;
        browser.ZoomFactor = 1.0;
        FormClosing += OnFormClosing;
        FormClosed += (_, _) =>
        {
            startupCancellation.Cancel();
            server?.Dispose();
            updateAgent?.Dispose();
        };
        Shown += async (_, _) =>
        {
            FitWorkingArea();
            await InitializeBrowserAsync();
        };
        DpiChanged += (_, _) => BeginInvoke((Action)FitWorkingArea);
    }

    private async Task InitializeBrowserAsync()
    {
        try
        {
            var runtimeVersion = CoreWebView2Environment.GetAvailableBrowserVersionString();
            if (string.IsNullOrWhiteSpace(runtimeVersion))
                throw new InvalidOperationException("未检测到 Microsoft Edge WebView2 Runtime");
            var legacyDirectory = SelectInitialData();
            if (initializationCanceled || IsDisposed || startupCancellation.IsCancellationRequested) return;
            updateAgent = UpdateAgent.Start(AppContext.BaseDirectory, RequestCloseForUpdateAsync);
            server = await ManagedServer.StartFromEnvironmentAsync(startupCancellation.Token, legacyDirectory, updateAgent?.Url, updateAgent?.Token);
            if (IsDisposed) { server?.Dispose(); return; }
            var userData = Environment.GetEnvironmentVariable("WEBVIEW2_USER_DATA_FOLDER");
            if (string.IsNullOrWhiteSpace(userData))
                userData = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "TkCRM", "webview2");
            else if (!Path.IsPathFullyQualified(userData))
                throw new InvalidOperationException("WEBVIEW2_USER_DATA_FOLDER 必须是绝对路径");
            Directory.CreateDirectory(userData);
            var environment = await CoreWebView2Environment.CreateAsync(null, userData);
            await browser.EnsureCoreWebView2Async(environment);
            browser.CoreWebView2.Settings.AreDefaultContextMenusEnabled = true;
            browser.CoreWebView2.Settings.IsStatusBarEnabled = false;
            browser.CoreWebView2.Settings.AreDevToolsEnabled = false;
            browser.CoreWebView2.NavigationCompleted += async (_, args) =>
            {
                if (!args.IsSuccess)
                {
                    Text = "TkCRM - 页面加载失败";
                }
                else
                {
                    ready = true;
                    Text = "TkCRM";
                    var readyFile = Environment.GetEnvironmentVariable("TKCRM_UPDATE_READY_FILE");
                    if (server is not null && !string.IsNullOrWhiteSpace(readyFile))
                    {
                        try
                        {
                            await WriteReadyFileAsync(readyFile, server.Port);
                        }
                        catch (IOException) { }
                        catch (HttpRequestException) { }
                        catch (TaskCanceledException) { }
                        catch (JsonException) { }
                        catch (KeyNotFoundException) { }
                        catch (InvalidOperationException) { }
                    }
                }
            };
            browser.Source = new Uri(Environment.GetEnvironmentVariable("TKCRM_URL")
                ?? (server is null ? "http://127.0.0.1:8080/login/" : $"http://127.0.0.1:{server.Port}/login/"));
        }
        catch (OperationCanceledException) when (startupCancellation.IsCancellationRequested) { }
        catch (Exception error)
        {
            server?.Dispose();
            updateAgent?.Dispose();
            server = null;
            updateAgent = null;
            if (IsDisposed) return;
            var message = error.Message.Contains("WebView2 Runtime", StringComparison.OrdinalIgnoreCase)
                ? "本机缺少 Microsoft Edge WebView2 Runtime。请先安装 WebView2 Runtime 后重新启动 TkCRM。"
                : $"无法初始化内置浏览器窗口：{error.Message}";
            MessageBox.Show(message, "TkCRM 启动失败", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private static async Task WriteReadyFileAsync(string path, int port)
    {
        using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(5) };
        using var response = await client.GetAsync($"http://127.0.0.1:{port}/health");
        response.EnsureSuccessStatusCode();
        using var document = JsonDocument.Parse(await response.Content.ReadAsStreamAsync());
        var version = document.RootElement.GetProperty("version").GetString();
        if (string.IsNullOrWhiteSpace(version)) throw new InvalidOperationException("服务未返回版本号");
        File.WriteAllText(path, JsonSerializer.Serialize(new { pid = Environment.ProcessId, port, version }));
    }

    private void OnFormClosing(object? sender, FormClosingEventArgs e)
    {
        if (!ready)
        {
            SaveWindowSettings();
            return;
        }

        var result = updateClosing ? DialogResult.Yes : MessageBox.Show(server is null ? "关闭窗口？外部服务不会停止。" : "退出 TkCRM 并停止本窗口启动的服务？", "退出 TkCRM",
            MessageBoxButtons.YesNo, MessageBoxIcon.Question);
        if (result != DialogResult.Yes)
        {
            e.Cancel = true;
            return;
        }

        SaveWindowSettings();
    }

    private Task RequestCloseForUpdateAsync()
    {
        if (!IsDisposed) BeginInvoke((Action)(() => { updateClosing = true; Close(); }));
        return Task.CompletedTask;
    }

    private string? SelectInitialData()
    {
        var executable = Environment.GetEnvironmentVariable("TKCRM_SERVER_EXE")
            ?? Path.Combine(AppContext.BaseDirectory, "server", "TkCrm.Server.exe");
        var data = Environment.GetEnvironmentVariable("TKCRM_DATA_DIR")
            ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "TkCRM", "server");
        var configured = Environment.GetEnvironmentVariable("TKCRM_LEGACY_DATA_DIR");
        if (!File.Exists(executable) || File.Exists(Path.Combine(data, "monitor.db"))
            || File.Exists(Path.Combine(data, ".env")) || !string.IsNullOrWhiteSpace(configured))
            return configured;
        var choice = MessageBox.Show(this,
            "首次使用 TkCRM：是否导入已有数据？\n\n是：选择旧项目或数据目录，保留原账号、密码与加密密钥。\n否：创建空数据库，初始账号 admin，密码 Admin123!。\n取消：退出，不创建数据。\n\n导入前请停止旧实例，原数据不会被删除。",
            "TkCRM 数据初始化", MessageBoxButtons.YesNoCancel, MessageBoxIcon.Question);
        if (choice == DialogResult.No) return null;
        if (choice == DialogResult.Cancel)
        {
            initializationCanceled = true;
            Close();
            return null;
        }
        using var dialog = new FolderBrowserDialog
        {
            Description = "选择旧 TkCRM 项目、backend 或包含 monitor.db 与原 .env 的目录",
            UseDescriptionForTitle = true,
            ShowNewFolderButton = false,
        };
        if (dialog.ShowDialog(this) == DialogResult.OK) return dialog.SelectedPath;
        initializationCanceled = true;
        Close();
        return null;
    }

    private void LoadWindowSettings()
    {
        try
        {
            if (!File.Exists(settingsPath)) return;
            var settings = JsonSerializer.Deserialize<WindowSettings>(File.ReadAllText(settingsPath));
            if (settings is null) return;
            if (settings.Width >= MinimumWidth && settings.Height >= MinimumHeight)
                Size = new Size(settings.Width, settings.Height);
            if (Screen.AllScreens.Any(screen => screen.WorkingArea.IntersectsWith(new Rectangle(settings.Left, settings.Top, 40, 40))))
            {
                StartPosition = FormStartPosition.Manual;
                Location = new Point(settings.Left, settings.Top);
            }
        }
        catch { }
    }

    private void SaveWindowSettings()
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(settingsPath)!);
            var bounds = WindowState == FormWindowState.Normal ? Bounds : RestoreBounds;
            var settings = new WindowSettings { Width = bounds.Width, Height = bounds.Height, Left = bounds.Left, Top = bounds.Top };
            File.WriteAllText(settingsPath, JsonSerializer.Serialize(settings));
        }
        catch { }
    }

    private void FitWorkingArea()
    {
        if (IsDisposed || WindowState != FormWindowState.Normal) return;
        var area = Screen.FromControl(this).WorkingArea;
        var minimum = new Size(Math.Min(MinimumWidth, area.Width), Math.Min(MinimumHeight, area.Height));
        MinimumSize = minimum;
        Size = WindowGeometry.ClampSize(Size, minimum, area);
        if (StartPosition == FormStartPosition.Manual)
            Location = WindowGeometry.ClampLocation(Location, Size, area);
    }

    private sealed class WindowSettings
    {
        public int Width { get; set; }
        public int Height { get; set; }
        public int Left { get; set; }
        public int Top { get; set; }
    }
}
