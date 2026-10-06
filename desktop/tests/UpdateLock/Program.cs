using System.Diagnostics;
using System.Net.Http.Headers;
using System.Text.Json;
using TkCrm.Desktop;
using TkCrm.Updater;

if (args.Length > 0)
{
    if (!UpdateLock.TryAcquire(args[1], out var acquired)) throw new Exception("fixture lock unavailable");
    using (acquired)
    {
        File.WriteAllText(args[2], Environment.ProcessId.ToString());
        await Console.In.ReadLineAsync();
    }
    return;
}

var root = Path.Combine(Path.GetTempPath(), "TkCRM-update-lock-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(root);
var status = Path.Combine(root, "status.json");
var initialStatus = JsonSerializer.Serialize(new { status = "running", latest_version = "99.0.0", message = "fixture" });
File.WriteAllText(status, initialStatus);
var installation = Path.Combine(root, "installation");
Directory.CreateDirectory(installation);
var updater = Environment.GetEnvironmentVariable("TKCRM_TEST_UPDATER_EXE")
    ?? throw new Exception("TKCRM_TEST_UPDATER_EXE required");
File.Copy(updater, Path.Combine(installation, "TkCrm.Updater.exe"));
Environment.SetEnvironmentVariable("TKCRM_DATA_DIR", root);
using var agent = UpdateAgent.Start(installation, () => throw new Exception("status must not close app"), status);
using var client = new HttpClient { BaseAddress = new Uri(agent.Url), Timeout = TimeSpan.FromSeconds(5) };
client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", agent.Token);

foreach (var crash in new[] { false, true })
{
    var ready = Path.Combine(root, crash ? "crash.ready" : "exit.ready");
    using var holder = StartHolder(status, ready);
    try
    {
        await WaitForFile(ready);
        if (UpdateLock.TryAcquire(status, out var unexpected))
        {
            unexpected!.Dispose();
            throw new Exception("second process lock acquisition unexpectedly succeeded");
        }
        if (await ReadStatus(client) != "running") throw new Exception("live updater status was treated as stale");
        if (crash) holder.Kill(entireProcessTree: true);
        else await holder.StandardInput.WriteLineAsync("exit");
        if (!holder.WaitForExit(10000)) throw new Exception("holder did not exit");
        if (!UpdateLock.TryAcquire(status, out var recovered)) throw new Exception("lock was not released after owner exit");
        recovered!.Dispose();
        if (await ReadStatus(client) != "failed") throw new Exception("stale running status was not recovered");
        if (File.ReadAllText(status) != initialStatus) throw new Exception("status read overwrote shared state");
        Console.WriteLine(crash ? "PASS update lock: real process crash releases lock and stale status recovers" : "PASS update lock: contention and normal exit");
    }
    finally
    {
        if (!holder.HasExited) { holder.Kill(entireProcessTree: true); holder.WaitForExit(10000); }
    }
}

if (!File.Exists(updater)) throw new Exception("updater executable missing");
using (var live = UpdateLock.TryAcquire(status, out var lockForUpdater) ? lockForUpdater : throw new Exception("busy fixture lock unavailable"))
{
    var receipt = Path.Combine(root, "updater.receipt");
    var info = new ProcessStartInfo(updater) { UseShellExecute = false, CreateNoWindow = true };
    foreach (var argument in new[] {
        "--parent-pid", Environment.ProcessId.ToString(), "--install-dir", root, "--data-dir", root,
        "--expected-version", "99.0.0", "--installer-url", "https://github.com/TheLayya/tk_crm/releases/download/v99.0.0/setup.exe",
        "--sha256", new string('a', 64), "--manifest-file", Path.Combine(root, "missing.json"), "--status-file", status,
        "--startup-receipt", receipt }) info.ArgumentList.Add(argument);
    using var contender = Process.Start(info) ?? throw new Exception("contender did not start");
    try
    {
        if (!contender.WaitForExit(10000)) throw new Exception("busy contender did not exit");
        using var result = JsonDocument.Parse(File.ReadAllText(receipt));
        if (contender.ExitCode != 1 || result.RootElement.GetProperty("status").GetString() != "busy"
            || result.RootElement.GetProperty("pid").GetInt32() != contender.Id)
            throw new Exception("updater busy receipt failed");
        if (File.ReadAllText(status) != initialStatus) throw new Exception("busy updater overwrote shared status");
        Console.WriteLine("PASS real updater: busy receipt belongs to loser and shared status is unchanged");

        var manifest = JsonSerializer.Serialize(new {
            version = "99.0.0",
            windows_package_url = "https://github.com/TheLayya/tk_crm/releases/download/v99.0.0/setup.exe",
            windows_sha256 = new string('a', 64),
        });
        using var post = await client.PostAsync("/apply", new StringContent(manifest, System.Text.Encoding.UTF8, "application/json"));
        if ((int)post.StatusCode != 409) throw new Exception("agent did not return busy 409");
        if (File.ReadAllText(status) != initialStatus) throw new Exception("agent busy apply overwrote shared status");
        Console.WriteLine("PASS desktop agent: concurrent POST returns 409 without changing shared status");
    }
    finally
    {
        if (!contender.HasExited) { contender.Kill(entireProcessTree: true); contender.WaitForExit(10000); }
    }
}
File.WriteAllText(status, JsonSerializer.Serialize(new { status = "waiting_exit", latest_version = "98.0.0" }));
var retryManifest = JsonSerializer.Serialize(new {
    version = "99.0.0",
    windows_package_url = "https://github.com/TheLayya/tk_crm/releases/download/v99.0.0/setup.exe",
    windows_sha256 = new string('a', 64),
});
using (var failedApply = await client.PostAsync("/apply", new StringContent(retryManifest, System.Text.Encoding.UTF8, "application/json")))
{
    if ((int)failedApply.StatusCode != 500) throw new Exception("invalid fixture was accepted by desktop agent");
    using var failedStatus = JsonDocument.Parse(File.ReadAllText(status));
    if (failedStatus.RootElement.GetProperty("status").GetString() != "failed"
        || failedStatus.RootElement.GetProperty("latest_version").GetString() != "99.0.0")
        throw new Exception("failed input did not record correct target status");
    Console.WriteLine("PASS desktop agent: stale waiting_exit is not accepted before input validation");
}
Console.WriteLine(root);

static Process StartHolder(string status, string ready)
{
    var info = new ProcessStartInfo(Environment.ProcessPath!) { UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true };
    if (Path.GetFileNameWithoutExtension(Environment.ProcessPath!).Equals("dotnet", StringComparison.OrdinalIgnoreCase)) info.ArgumentList.Add(typeof(Program).Assembly.Location);
    foreach (var argument in new[] { "hold", status, ready }) info.ArgumentList.Add(argument);
    return Process.Start(info) ?? throw new Exception("fixture process not started");
}

static async Task WaitForFile(string path)
{
    for (var i = 0; i < 100 && !File.Exists(path); i++) await Task.Delay(50);
    if (!File.Exists(path)) throw new TimeoutException(path);
}

static async Task<string?> ReadStatus(HttpClient client)
{
    using var response = await client.GetAsync("/status");
    response.EnsureSuccessStatusCode();
    using var state = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
    if (state.RootElement.GetProperty("latest_version").GetString() != "99.0.0") throw new Exception("status lost target version");
    return state.RootElement.GetProperty("status").GetString();
}
