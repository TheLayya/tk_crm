using System.Diagnostics;
using System.Net.Http.Headers;
using System.Text.Json;
using TkCrm.Desktop;
using TkCrm.Updater;

if (args.Length > 0 && args[0] == "--parent-pid")
{
    try { await RunUpdaterFixture(args); }
    catch (Exception error) { Console.Error.WriteLine(error.Message); Environment.ExitCode = 1; }
    return;
}

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
{
using var agent = UpdateAgent.Start(installation, () => throw new Exception("status must not close app"), status);
using var client = new HttpClient { BaseAddress = new Uri(agent.Url), Timeout = TimeSpan.FromSeconds(5) };
client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", agent.Token);

foreach (var crash in new[] { false, true })
{
    var ready = Path.Combine(root, crash ? "crash.ready" : "exit.ready");
    using var holder = StartHolder(status, ready);
    Task<UpdateLock?>? pendingAcquisition = null;
    try
    {
        await WaitForFile(ready);
        if (UpdateLock.TryAcquire(status, out var unexpected))
        {
            unexpected!.Dispose();
            throw new Exception("second process lock acquisition unexpectedly succeeded");
        }
        if (await ReadStatus(client) != "running") throw new Exception("live updater status was treated as stale");
        var elapsed = Stopwatch.StartNew();
        using var timedOut = await UpdateLock.AcquireAsync(status, TimeSpan.FromMilliseconds(200));
        if (timedOut is not null || elapsed.Elapsed < TimeSpan.FromMilliseconds(200))
            throw new Exception("bounded lock acquisition did not wait and time out against the live holder");
        if (File.ReadAllText(status) != initialStatus) throw new Exception("timed out lock acquisition changed shared status");
        pendingAcquisition = UpdateLock.AcquireAsync(status, TimeSpan.FromSeconds(1));
        if (pendingAcquisition.IsCompleted) throw new Exception("pending acquisition did not observe the live holder");
        if (crash) holder.Kill(entireProcessTree: true);
        else await holder.StandardInput.WriteLineAsync("exit");
        if (!holder.WaitForExit(10000)) throw new Exception("holder did not exit");
        using (var pendingLock = await pendingAcquisition)
        {
            pendingAcquisition = null;
            if (pendingLock is null) throw new Exception("bounded acquisition did not recover after holder exit");
            if (File.ReadAllText(status) != initialStatus) throw new Exception("recovered acquisition changed shared status");
        }
        if (!UpdateLock.TryAcquire(status, out var recovered)) throw new Exception("lock was not released after owner exit");
        recovered!.Dispose();
        if (await ReadStatus(client) != "failed") throw new Exception("stale running status was not recovered");
        if (File.ReadAllText(status) != initialStatus) throw new Exception("status read overwrote shared state");
        Console.WriteLine(crash ? "PASS update lock: bounded timeout, real process crash releases pending lock and stale status recovers" : "PASS update lock: bounded timeout, pending acquisition and normal exit");
    }
    finally
    {
        if (!holder.HasExited) { holder.Kill(entireProcessTree: true); holder.WaitForExit(10000); }
        if (pendingAcquisition is not null) (await pendingAcquisition)?.Dispose();
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
}

var fixtureInstallation = Path.Combine(root, "fixture-installation");
Directory.CreateDirectory(fixtureInstallation);
File.Copy(Environment.ProcessPath!, Path.Combine(fixtureInstallation, "TkCrm.Updater.exe"));
foreach (var mode in new[] { "accepted", "wrong-pid", "no-receipt" })
{
    var fixture = Path.Combine(root, mode);
    Directory.CreateDirectory(fixture);
    var fixtureStatus = Path.Combine(fixture, "status.json");
    WriteFixtureJson(fixtureStatus, new { status = "idle", latest_version = "99.0.0" });
    var closeCount = 0;
    var closed = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
    using var fixtureAgent = UpdateAgent.Start(fixtureInstallation, () =>
    {
        Interlocked.Increment(ref closeCount);
        File.WriteAllText(Path.Combine(fixture, "stop"), "close callback");
        closed.TrySetResult(true);
        return Task.CompletedTask;
    }, fixtureStatus);
    using var fixtureClient = new HttpClient { BaseAddress = new Uri(fixtureAgent.Url), Timeout = TimeSpan.FromSeconds(20) };
    fixtureClient.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", fixtureAgent.Token);
    if (mode != "accepted")
    {
        await ExerciseRejected(fixtureClient, fixture, mode, () => Volatile.Read(ref closeCount));
        File.Delete(Path.Combine(fixture, "started.json"));
        File.Delete(Path.Combine(fixture, "release-receipt"));
        WriteFixtureJson(fixtureStatus, new { status = "idle", latest_version = "99.0.0" });
    }
    await ExerciseAccepted(fixtureClient, fixture, closed.Task, () => Volatile.Read(ref closeCount));
    Console.WriteLine(mode == "accepted"
        ? "PASS desktop agent: accepted receipt, concurrent GET/apply and exactly one automatic close"
        : $"PASS desktop agent: {mode} rejected without close, process/lock released and retry accepted");
}
Console.WriteLine(root);

static Process StartHolder(string status, string ready)
{
    var info = new ProcessStartInfo(Environment.ProcessPath!) { UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true };
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

static string FixtureManifest(string fixture, string mode) => JsonSerializer.Serialize(new
{
    version = "99.0.0",
    windows_package_url = "https://github.com/TheLayya/tk_crm/releases/download/v99.0.0/setup.exe",
    windows_sha256 = new string('a', 64),
    fixture_mode = mode,
    fixture_directory = fixture,
});

static async Task ExerciseAccepted(HttpClient client, string fixture, Task closed, Func<int> closeCount)
{
    using var body = new StringContent(FixtureManifest(fixture, "accepted"), System.Text.Encoding.UTF8, "application/json");
    var apply = client.PostAsync("/apply", body);
    Process? process = null;
    try
    {
        await WaitForFile(Path.Combine(fixture, "started.json"));
        process = ReadFixtureProcess(fixture);
        var probes = Enumerable.Range(0, 12).Select(_ => ReadStatus(client)).ToArray();
        using var duplicateBody = new StringContent(FixtureManifest(fixture, "accepted"), System.Text.Encoding.UTF8, "application/json");
        var duplicate = client.PostAsync("/apply", duplicateBody);
        if ((await Task.WhenAll(probes)).Any(value => value != "running")) throw new Exception("concurrent status read lost the live update");
        using var busy = await duplicate;
        if ((int)busy.StatusCode != 409) throw new Exception("concurrent apply was not rejected during startup handshake");
        if (closeCount() != 0 || apply.IsCompleted) throw new Exception("agent accepted or closed before startup receipt");
        File.WriteAllText(Path.Combine(fixture, "release-receipt"), "accepted");
        using var response = await apply;
        response.EnsureSuccessStatusCode();
        using var result = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        if (result.RootElement.GetProperty("status").GetString() != "running"
            || result.RootElement.GetProperty("latest_version").GetString() != "99.0.0")
            throw new Exception("accepted response lost the target version");
        if (closeCount() != 0) throw new Exception("accepted receipt closed the desktop before waiting_exit");
        File.WriteAllText(Path.Combine(fixture, "release-waiting"), "waiting_exit");
        await closed.WaitAsync(TimeSpan.FromSeconds(5));
        if (!process.WaitForExit(5000)) throw new Exception("accepted fixture did not exit after automatic close");
        if (closeCount() != 1) throw new Exception("waiting_exit did not close the desktop exactly once");
        if (await ReadStatus(client) != "completed") throw new Exception("completed fixture status was treated as stale");
    }
    finally { await FinishFixture(process, apply); }
}

static async Task ExerciseRejected(HttpClient client, string fixture, string mode, Func<int> closeCount)
{
    using var body = new StringContent(FixtureManifest(fixture, mode), System.Text.Encoding.UTF8, "application/json");
    var elapsed = Stopwatch.StartNew();
    var apply = client.PostAsync("/apply", body);
    Process? process = null;
    try
    {
        await WaitForFile(Path.Combine(fixture, "started.json"));
        process = ReadFixtureProcess(fixture);
        if (await ReadStatus(client) != "waiting_exit") throw new Exception("negative fixture did not exercise waiting_exit with an unaccepted receipt");
        if (mode == "wrong-pid") File.WriteAllText(Path.Combine(fixture, "release-receipt"), "wrong-pid");
        using var response = await apply;
        if ((int)response.StatusCode != 500) throw new Exception($"{mode} fixture was accepted");
        if (mode == "no-receipt" && elapsed.Elapsed < TimeSpan.FromSeconds(9)) throw new Exception("missing receipt did not exercise the startup timeout");
        if (closeCount() != 0) throw new Exception($"{mode} fixture closed the desktop");
        if (!process.WaitForExit(5000)) throw new Exception($"{mode} fixture was not stopped by the agent");
        var status = Path.Combine(fixture, "status.json");
        if (!UpdateLock.TryAcquire(status, out var released)) throw new Exception($"{mode} fixture retained the update lock");
        released!.Dispose();
    }
    finally { await FinishFixture(process, apply); }
}

static Process ReadFixtureProcess(string fixture)
{
    using var started = JsonDocument.Parse(File.ReadAllText(Path.Combine(fixture, "started.json")));
    return Process.GetProcessById(started.RootElement.GetProperty("pid").GetInt32());
}

static async Task FinishFixture(Process? process, Task<HttpResponseMessage> apply)
{
    if (process is not null)
    {
        if (!process.HasExited) { process.Kill(entireProcessTree: true); process.WaitForExit(10000); }
        process.Dispose();
    }
    try { using var response = await apply; }
    catch (Exception) { }
}

static async Task RunUpdaterFixture(string[] arguments)
{
    var options = new Dictionary<string, string>();
    for (var index = 0; index < arguments.Length; index += 2) options.Add(arguments[index], arguments[index + 1]);
    using var manifest = JsonDocument.Parse(File.ReadAllText(options["--manifest-file"]));
    var fixture = manifest.RootElement.GetProperty("fixture_directory").GetString()!;
    var mode = manifest.RootElement.GetProperty("fixture_mode").GetString();
    var status = options["--status-file"];
    if (!UpdateLock.TryAcquire(status, out var acquired)) throw new Exception("fake updater lock unavailable");
    using (acquired)
    {
        WriteFixtureJson(status, new { status = mode == "accepted" ? "running" : "waiting_exit", latest_version = "99.0.0" });
        WriteFixtureJson(Path.Combine(fixture, "started.json"), new { pid = Environment.ProcessId });
        if (mode == "wrong-pid")
        {
            await WaitForMarker(Path.Combine(fixture, "release-receipt"));
            WriteFixtureJson(options["--startup-receipt"], new { pid = Environment.ProcessId + 1, status = "accepted" });
        }
        if (mode == "accepted")
        {
            await WaitForMarker(Path.Combine(fixture, "release-receipt"));
            WriteFixtureJson(options["--startup-receipt"], new { pid = Environment.ProcessId, status = "accepted" });
            await WaitForMarker(Path.Combine(fixture, "release-waiting"));
            WriteFixtureJson(status, new { status = "waiting_exit", latest_version = "99.0.0" });
        }
        await WaitForMarker(Path.Combine(fixture, "stop"));
        WriteFixtureJson(status, new { status = "completed", latest_version = "99.0.0" });
    }
}

static async Task WaitForMarker(string path)
{
    var deadline = DateTime.UtcNow.AddSeconds(30);
    while (!File.Exists(path) && DateTime.UtcNow < deadline) await Task.Delay(25);
    if (!File.Exists(path)) throw new TimeoutException(path);
}

static void WriteFixtureJson(string path, object value)
{
    File.WriteAllText(path + ".tmp", JsonSerializer.Serialize(value));
    File.Move(path + ".tmp", path, true);
}
