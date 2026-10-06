using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;
using TkCrm.Updater;
using static TkCrm.Updater.DirectorySnapshot;

const long MaxInstallerBytes = 512L * 1024 * 1024;
var arguments = ParseArguments(args);
var statusFile = Required(arguments, "status-file");
var installDirectory = Path.GetFullPath(Required(arguments, "install-dir"));
var dataDirectory = Path.GetFullPath(arguments.TryGetValue("data-dir", out var configuredData) && !string.IsNullOrWhiteSpace(configuredData)
    ? configuredData
    : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "TkCRM", "server"));
var parentPid = int.Parse(Required(arguments, "parent-pid"));
var releaseVersion = arguments.GetValueOrDefault("expected-version", "");
var expectedVersion = releaseVersion.StartsWith('v') ? releaseVersion[1..] : releaseVersion;
var installerUrl = new Uri(Required(arguments, "installer-url"));
var expectedHash = Required(arguments, "sha256").ToLowerInvariant();
var launchPath = Path.Combine(installDirectory, "TkCrm.Desktop.exe");
var workDirectory = Path.Combine(Path.GetDirectoryName(statusFile)!, "updates", Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(workDirectory);
var parentExited = false;
UpdateBackup? completedBackup = null;
Process? launched = null;

try
{
    ValidateInstallation(installDirectory, dataDirectory, statusFile);
    if (!Version.TryParse(expectedVersion, out _))
        throw new InvalidOperationException("目标版本格式错误");
    using var manifest = UpdateHistory.LoadManifest(Required(arguments, "manifest-file"), releaseVersion, installerUrl.ToString(), expectedHash);
    if (installerUrl.Scheme != Uri.UriSchemeHttps || installerUrl.Host != "github.com"
        || installerUrl.UserInfo.Length != 0 || installerUrl.Fragment.Length != 0 || installerUrl.Query.Length != 0
        || !installerUrl.AbsolutePath.StartsWith("/TheLayya/tk_crm/releases/download/", StringComparison.Ordinal)
        || !installerUrl.AbsolutePath.EndsWith(".exe", StringComparison.OrdinalIgnoreCase))
        throw new InvalidOperationException("更新地址不是受信任的 Windows 发布资产");
    if (expectedHash.Length != 64 || !expectedHash.All(Uri.IsHexDigit))
        throw new InvalidOperationException("安装包 SHA-256 格式错误");
    WriteStatus(statusFile, "running", "正在下载并校验 Windows 安装包");
    var installer = Path.Combine(workDirectory, "TkCRM-update.exe");
    await DownloadAndVerifyAsync(installerUrl, installer, expectedHash);
    WriteStatus(statusFile, "waiting_exit", "等待 TkCRM 主窗口退出");
    WaitForProcessExit(parentPid, TimeSpan.FromMinutes(2));
    parentExited = true;

    completedBackup = UpdateTransaction.Snapshot(installDirectory, dataDirectory, workDirectory);
    WriteStatus(statusFile, "running", "正在安装更新");
    UpdateTransaction.Install(installer, installDirectory);

    WriteStatus(statusFile, "installed", "安装程序已完成，正在等待新版本健康检查");
    var readyFile = Path.Combine(workDirectory, "ready.json");
    var launchInfo = new ProcessStartInfo { FileName = launchPath, WorkingDirectory = installDirectory, UseShellExecute = false };
    launchInfo.Environment["TKCRM_UPDATE_READY_FILE"] = readyFile;
    launchInfo.Environment["TKCRM_DATA_DIR"] = dataDirectory;
    launched = Process.Start(launchInfo)
        ?? throw new InvalidOperationException("无法启动更新后的 TkCRM");
    if (!await UpdateProcess.WaitForHealthAsync(launched, readyFile, expectedVersion, TimeSpan.FromSeconds(90)))
        throw new InvalidOperationException("更新后的 TkCRM 就绪检查失败");
    UpdateHistory.Record(dataDirectory, manifest.RootElement);
    WriteStatus(statusFile, "completed", "更新完成");
}
catch (Exception error)
{
    if (parentExited)
    {
        try
        {
            if (launched is not null) UpdateProcess.Stop(launched, "无法停止失败的新版本，请手动恢复备份");
            if (completedBackup is not null) UpdateTransaction.Restore(completedBackup, installDirectory, dataDirectory);
            var recoveryInfo = new ProcessStartInfo { FileName = launchPath, WorkingDirectory = installDirectory, UseShellExecute = false };
            recoveryInfo.Environment["TKCRM_DATA_DIR"] = dataDirectory;
            var recoveryReadyFile = Path.Combine(workDirectory, "recovery-ready.json");
            recoveryInfo.Environment["TKCRM_UPDATE_READY_FILE"] = recoveryReadyFile;
            using var recovered = Process.Start(recoveryInfo)
                ?? throw new InvalidOperationException("无法启动恢复后的 TkCRM");
            if (!await UpdateProcess.WaitForHealthAsync(recovered, recoveryReadyFile, null, TimeSpan.FromSeconds(90)))
            {
                UpdateProcess.Stop(recovered, "恢复后的进程无法停止，请手动关闭 TkCRM 后查看日志");
                throw new InvalidOperationException("文件已恢复，但旧版本未通过就绪检查，请查看日志并手动启动");
            }
        }
        catch (Exception recoveryError)
        {
            WriteStatus(statusFile, "failed", error.Message + "；恢复失败：" + recoveryError.Message);
            Environment.ExitCode = 1;
            return;
        }
    }
    WriteStatus(statusFile, "failed", error.Message);
    Environment.ExitCode = 1;
}

static Dictionary<string, string> ParseArguments(string[] values)
{
    var result = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
    for (var index = 0; index < values.Length; index++)
    {
        if (!values[index].StartsWith("--") || index + 1 >= values.Length) throw new ArgumentException("更新器参数不完整");
        result[values[index][2..]] = values[++index];
    }
    return result;
}

static string Required(IReadOnlyDictionary<string, string> values, string name) =>
    values.TryGetValue(name, out var value) && !string.IsNullOrWhiteSpace(value) ? value : throw new ArgumentException($"缺少参数 --{name}");

static async Task DownloadAndVerifyAsync(Uri url, string destination, string expectedHash)
{
    if (url.Scheme != Uri.UriSchemeHttps) throw new InvalidOperationException("更新地址必须使用 HTTPS");
    using var client = new HttpClient { Timeout = TimeSpan.FromMinutes(10) };
    client.DefaultRequestHeaders.UserAgent.ParseAdd("TkCRM-Updater");
    using var response = await client.GetAsync(url, HttpCompletionOption.ResponseHeadersRead);
    response.EnsureSuccessStatusCode();
    var finalUri = response.RequestMessage?.RequestUri;
    if (finalUri?.Scheme != Uri.UriSchemeHttps || !IsTrustedDownloadHost(finalUri.Host))
        throw new InvalidOperationException("安装包重定向地址不是受信任的 GitHub 资产");
    if (response.Content.Headers.ContentLength is > MaxInstallerBytes) throw new InvalidOperationException("安装包超过大小限制");
    await using var input = await response.Content.ReadAsStreamAsync();
    await using var output = File.Create(destination);
    using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
    var buffer = new byte[1024 * 1024];
    long total = 0;
    int read;
    while ((read = await input.ReadAsync(buffer)) > 0)
    {
        total += read;
        if (total > MaxInstallerBytes) throw new InvalidOperationException("安装包超过大小限制");
        hash.AppendData(buffer, 0, read);
        await output.WriteAsync(buffer.AsMemory(0, read));
    }
    var actualHash = Convert.ToHexString(hash.GetHashAndReset()).ToLowerInvariant();
    if (!CryptographicOperations.FixedTimeEquals(Convert.FromHexString(actualHash), Convert.FromHexString(expectedHash)))
        throw new InvalidOperationException("安装包 SHA-256 校验失败");
}

static bool IsTrustedDownloadHost(string host) => host.Equals("github.com", StringComparison.OrdinalIgnoreCase)
    || host.Equals("release-assets.githubusercontent.com", StringComparison.OrdinalIgnoreCase)
    || host.Equals("objects.githubusercontent.com", StringComparison.OrdinalIgnoreCase);

static void WaitForProcessExit(int pid, TimeSpan timeout)
{
    var deadline = DateTime.UtcNow + timeout;
    while (DateTime.UtcNow < deadline)
    {
        try { using var process = Process.GetProcessById(pid); if (process.HasExited) return; }
        catch (ArgumentException) { return; }
        Thread.Sleep(250);
    }
    throw new TimeoutException("等待 TkCRM 退出超时");
}

static void ValidateInstallation(string installation, string dataDirectory, string status)
{
    var root = Path.GetPathRoot(installation);
    if (string.Equals(installation.TrimEnd(Path.DirectorySeparatorChar), root?.TrimEnd(Path.DirectorySeparatorChar), StringComparison.OrdinalIgnoreCase)
        || !File.Exists(Path.Combine(installation, "TkCrm.Desktop.exe"))
        || !File.Exists(Path.Combine(installation, "server", "TkCrm.Server.exe")))
        throw new InvalidOperationException("安装目录缺少 TkCRM 程序文件");
    var prefix = installation.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
    var dataPrefix = dataDirectory.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
    if (Path.GetFullPath(status).StartsWith(prefix, StringComparison.OrdinalIgnoreCase)
        || Path.GetFullPath(AppContext.BaseDirectory).StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
        throw new InvalidOperationException("更新器及状态目录必须位于安装目录外");
    if (string.Equals(dataDirectory.TrimEnd(Path.DirectorySeparatorChar), installation.TrimEnd(Path.DirectorySeparatorChar), StringComparison.OrdinalIgnoreCase)
        || dataDirectory.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)
        || installation.StartsWith(dataPrefix, StringComparison.OrdinalIgnoreCase)
        || Path.GetFullPath(status).StartsWith(dataPrefix, StringComparison.OrdinalIgnoreCase)
        || Path.GetFullPath(AppContext.BaseDirectory).StartsWith(dataPrefix, StringComparison.OrdinalIgnoreCase)
        || !File.Exists(Path.Combine(dataDirectory, "monitor.db"))
        || !File.Exists(Path.Combine(dataDirectory, ".env")))
        throw new InvalidOperationException("用户数据目录不能位于安装目录内或包含状态文件");
    if (Directory.Exists(dataDirectory)) RejectLinks(dataDirectory);
    RejectLinks(installation);
    if (Directory.EnumerateFiles(installation, "*", SearchOption.AllDirectories)
        .Any(file => Path.GetFileName(file) == ".env" || new[] { ".db", ".sqlite", ".sqlite3" }.Contains(Path.GetExtension(file).ToLowerInvariant())))
        throw new InvalidOperationException("安装目录包含运行时数据，请先迁移至用户数据目录");
}


static void WriteStatus(string path, string status, string message)
{
    Directory.CreateDirectory(Path.GetDirectoryName(path)!);
    var temporary = path + ".tmp";
    File.WriteAllText(temporary, JsonSerializer.Serialize(new { status, message, updated_at = DateTimeOffset.UtcNow }));
    File.Move(temporary, path, true);
}
