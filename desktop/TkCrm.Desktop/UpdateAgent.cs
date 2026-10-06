using System.Net;
using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace TkCrm.Desktop;

public sealed class UpdateAgent : IDisposable
{
    private readonly HttpListener listener = new();
    private readonly CancellationTokenSource cancellation = new();
    private readonly Func<Task> closeApplication;
    private readonly string installDirectory;
    private readonly string statusFile;
    private readonly string updaterPath;
    private readonly string token;
    private readonly object gate = new();
    private bool running;

    private UpdateAgent(string installDirectory, Func<Task> closeApplication)
    {
        this.installDirectory = installDirectory;
        this.closeApplication = closeApplication;
        statusFile = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "TkCRM", "update-status.json");
        updaterPath = Path.Combine(installDirectory, "TkCrm.Updater.exe");
        token = Convert.ToHexString(RandomNumberGenerator.GetBytes(32)).ToLowerInvariant();
    }

    public string Url { get; private set; } = "";
    public string Token => token;

    public static UpdateAgent Start(string installDirectory, Func<Task> closeApplication)
    {
        if (!File.Exists(Path.Combine(installDirectory, "TkCrm.Updater.exe")))
            throw new FileNotFoundException("缺少 TkCRM 更新器，请重新安装完整桌面安装包");
        var agent = new UpdateAgent(installDirectory, closeApplication);
        for (var port = 8765; port < 8775; port++)
        {
            try
            {
                agent.listener.Prefixes.Add($"http://127.0.0.1:{port}/");
                agent.listener.Start();
                agent.Url = $"http://127.0.0.1:{port}";
                _ = agent.RunAsync();
                return agent;
            }
            catch (HttpListenerException)
            {
                agent.listener.Prefixes.Clear();
            }
        }
        agent.Dispose();
        throw new InvalidOperationException("本地更新代理端口均已被占用");
    }

    private async Task RunAsync()
    {
        while (!cancellation.IsCancellationRequested)
        {
            HttpListenerContext context;
            try { context = await listener.GetContextAsync(); }
            catch when (cancellation.IsCancellationRequested) { return; }
            catch { continue; }
            _ = Task.Run(() => HandleAsync(context), cancellation.Token);
        }
    }

    private async Task HandleAsync(HttpListenerContext context)
    {
        try
        {
            if (!string.Equals(context.Request.Headers["Authorization"], $"Bearer {token}", StringComparison.Ordinal))
            {
                context.Response.StatusCode = 401;
                await WriteJsonAsync(context, new { detail = "Unauthorized" });
                return;
            }
            if (context.Request.HttpMethod == "GET" && context.Request.Url?.AbsolutePath == "/status")
            {
                await WriteStatusAsync(context);
                return;
            }
            if (context.Request.HttpMethod == "POST" && context.Request.Url?.AbsolutePath == "/apply")
            {
                await ApplyAsync(context);
                return;
            }
            context.Response.StatusCode = 404;
            await WriteJsonAsync(context, new { detail = "Not found" });
        }
        catch (Exception error)
        {
            context.Response.StatusCode = 500;
            await WriteJsonAsync(context, new { detail = error.Message });
        }
        finally { context.Response.Close(); }
    }

    private async Task ApplyAsync(HttpListenerContext context)
    {
        if (context.Request.ContentLength64 < 0 || context.Request.ContentLength64 > 256 * 1024)
            throw new InvalidOperationException("更新请求超过大小限制");
        using var reader = new StreamReader(context.Request.InputStream, context.Request.ContentEncoding ?? Encoding.UTF8);
        using var document = JsonDocument.Parse(await reader.ReadToEndAsync());
        var root = document.RootElement;
        var url = root.GetProperty("windows_package_url").GetString() ?? throw new InvalidOperationException("缺少 Windows 安装包地址");
        var sha256 = root.GetProperty("windows_sha256").GetString() ?? throw new InvalidOperationException("缺少安装包校验值");
        var version = root.TryGetProperty("version", out var versionElement)
            ? versionElement.GetString() ?? ""
            : "";
        if (string.IsNullOrWhiteSpace(version))
            throw new InvalidOperationException("缺少目标版本");
        var dataDirectory = Environment.GetEnvironmentVariable("TKCRM_DATA_DIR")
            ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "TkCRM", "server");
        lock (gate)
        {
            if (running) { context.Response.StatusCode = 409; return; }
            running = true;
        }
        try
        {
        if (!Uri.TryCreate(url, UriKind.Absolute, out var packageUrl) || packageUrl.Scheme != Uri.UriSchemeHttps
            || packageUrl.Host != "github.com" || packageUrl.UserInfo.Length != 0 || packageUrl.Fragment.Length != 0
            || packageUrl.Query.Length != 0 || !packageUrl.AbsolutePath.StartsWith("/TheLayya/tk_crm/releases/download/", StringComparison.Ordinal)
            || !packageUrl.AbsolutePath.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)
            || sha256.Length != 64 || !sha256.All(Uri.IsHexDigit))
            throw new InvalidOperationException("Windows 发布资产校验失败");

        var runDirectory = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "TkCRM", "updates", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(runDirectory);
        var runUpdater = Path.Combine(runDirectory, "TkCrm.Updater.exe");
        File.Copy(updaterPath, runUpdater, true);
        var manifestFile = Path.Combine(runDirectory, "release.json");
        File.WriteAllText(manifestFile, root.GetRawText());
        var runStatus = statusFile;
        File.WriteAllText(runStatus, JsonSerializer.Serialize(new { status = "running", message = "正在准备更新" }));
        var info = new ProcessStartInfo
        {
            FileName = runUpdater,
            WorkingDirectory = runDirectory,
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        foreach (var argument in new[] { "--parent-pid", Environment.ProcessId.ToString(), "--install-dir", installDirectory, "--data-dir", dataDirectory, "--expected-version", version, "--manifest-file", manifestFile, "--installer-url", packageUrl.ToString(), "--sha256", sha256, "--status-file", runStatus })
            info.ArgumentList.Add(argument);
        var process = Process.Start(info) ?? throw new InvalidOperationException("无法启动更新器");
        await WriteJsonAsync(context, new { status = "running" });
        _ = Task.Run(async () =>
        {
            using (process)
            {
                try
                {
                    while (!process.HasExited && !cancellation.IsCancellationRequested)
                    {
                        try
                        {
                            using var state = JsonDocument.Parse(await File.ReadAllTextAsync(statusFile));
                            if (state.RootElement.GetProperty("status").GetString() == "waiting_exit")
                            {
                                await closeApplication();
                                return;
                            }
                        }
                        catch (IOException) { }
                        catch (JsonException) { }
                        await Task.Delay(250, cancellation.Token);
                    }
                }
                catch (OperationCanceledException) { }
                finally { lock (gate) running = false; }
            }
        });
        }
        catch
        {
            lock (gate) running = false;
            throw;
        }
    }

    private async Task WriteStatusAsync(HttpListenerContext context)
    {
        if (!File.Exists(statusFile)) { await WriteJsonAsync(context, new { status = "idle", message = "" }); return; }
        using var state = JsonDocument.Parse(await File.ReadAllTextAsync(statusFile));
        await WriteJsonAsync(context, state.RootElement);
    }

    private static async Task WriteJsonAsync(HttpListenerContext context, object value)
    {
        var bytes = JsonSerializer.SerializeToUtf8Bytes(value);
        context.Response.ContentType = "application/json";
        context.Response.ContentLength64 = bytes.Length;
        await context.Response.OutputStream.WriteAsync(bytes);
    }

    public void Dispose()
    {
        cancellation.Cancel();
        if (listener.IsListening) listener.Stop();
        listener.Close();
        cancellation.Dispose();
    }
}
