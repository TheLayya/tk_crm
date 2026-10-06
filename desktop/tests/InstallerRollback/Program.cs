using TkCrm.Updater;
using System.Security.Cryptography;
using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Text.Json;

if (args.Length == 3 && args[0] == "--fixture")
{
    try
    {
        await RunFixture(args[1], args[2]);
    }
    catch (Exception error)
    {
        Console.Error.WriteLine(error.Message);
        Environment.ExitCode = 1;
    }
    return;
}
if (args.Length != 1) throw new ArgumentException("Pass the compiled failure-setup.exe path");
var root = Path.Combine(Path.GetTempPath(), "TkCRM-inno-rollback-" + Guid.NewGuid().ToString("N"));
var installation = Path.Combine(root, "中文安装目录");
var data = Path.Combine(root, "隔离数据");
Directory.CreateDirectory(Path.Combine(installation, "server"));
Directory.CreateDirectory(data);
foreach (var file in Directory.EnumerateFiles(AppContext.BaseDirectory)) File.Copy(file, Path.Combine(installation, Path.GetFileName(file)));
File.Copy(Path.Combine(AppContext.BaseDirectory, "InstallerRollback.exe"), Path.Combine(installation, "TkCrm.Desktop.exe"));
File.WriteAllText(Path.Combine(installation, "server", "TkCrm.Server.exe"), "old server");
File.WriteAllText(Path.Combine(data, "monitor.db"), "old database");
File.WriteAllText(Path.Combine(data, ".env"), "old configuration");
File.WriteAllText(Path.Combine(data, "fixture-only.txt"), "isolated guard");
File.WriteAllText(Path.Combine(installation, "fixture-only.txt"), "isolated guard");
File.WriteAllBytes(Path.Combine(data, "monitor.db-wal"), Enumerable.Range(0, 256).Select(value => (byte)value).ToArray());
File.WriteAllBytes(Path.Combine(data, "monitor.db-shm"), new byte[] { 0, 255, 128, 1 });
Directory.CreateDirectory(Path.Combine(data, "backups", "旧备份"));
File.WriteAllBytes(Path.Combine(data, "backups", "旧备份", "snapshot.bin"), new byte[] { 0, 1, 2, 3, 255 });
var originalInstallation = HashFiles(installation);
var originalData = HashFiles(data);
var backup = UpdateTransaction.Snapshot(installation, data, Path.Combine(root, "snapshot"));
Environment.SetEnvironmentVariable("TKCRM_ROLLBACK_FIXTURE_DATA", data);
Environment.SetEnvironmentVariable("TKCRM_ROLLBACK_FIXTURE_INSTALL", installation);
try
{
    try
    {
        UpdateTransaction.Install(Path.GetFullPath(args[0]), installation);
        throw new Exception("Fixture installer unexpectedly succeeded");
    }
    catch (InvalidOperationException error)
    {
        Assert(error.Message.StartsWith("安装程序退出码："), "installer failure surfaced");
        Assert(File.ReadAllText(Path.Combine(installation, "TkCrm.Desktop.exe")) == "failed installer desktop", "real installer modified program");
        Assert(File.ReadAllText(Path.Combine(data, "monitor.db")) == "failed installer database", "real installer modified data");
        Assert(File.ReadAllText(Path.Combine(data, "monitor.db-wal")) == "failed installer wal", "real installer modified WAL");
        File.Delete(Path.Combine(data, "backups", "旧备份", "snapshot.bin"));
        Assert(!File.Exists(Path.Combine(data, "backups", "旧备份", "snapshot.bin")), "simulated missing nested backup before restore");
        Console.WriteLine(error.Message);
        UpdateTransaction.Restore(backup, installation, data);
    }
    Assert(File.ReadAllText(Path.Combine(installation, "server", "TkCrm.Server.exe")) == "old server", "server preserved");
    Assert(File.ReadAllText(Path.Combine(data, "monitor.db")) == "old database", "database restored");
    Assert(File.ReadAllText(Path.Combine(data, ".env")) == "old configuration", "configuration restored");
    Assert(!File.Exists(Path.Combine(installation, "new-only.txt")), "new program file removed");
    Assert(!File.Exists(Path.Combine(data, "new-only.txt")), "new data file removed");
    Assert(HashFiles(installation).SequenceEqual(originalInstallation), "all installation file paths and hashes restored");
    Assert(HashFiles(data).SequenceEqual(originalData), "all data file paths and hashes restored including WAL, SHM and nested backup");
    var readyFile = Path.Combine(root, "recovery-ready.json");
    var launch = new ProcessStartInfo(Path.Combine(installation, "TkCrm.Desktop.exe")) { WorkingDirectory = installation, UseShellExecute = false, CreateNoWindow = true };
    launch.ArgumentList.Add("--fixture");
    launch.ArgumentList.Add(readyFile);
    launch.ArgumentList.Add(data);
    using var recovered = Process.Start(launch) ?? throw new InvalidOperationException("recovery fixture did not start");
    try
    {
        Assert(await UpdateProcess.WaitForHealthAsync(recovered, readyFile, null, TimeSpan.FromSeconds(10)), "restored executable became ready using restored data");
    }
    finally { UpdateProcess.Stop(recovered, "restored process did not stop"); }
    Assert(recovered.HasExited, "restored process exited after stop");
    Console.WriteLine("PASS: restored executable loaded restored data, became ready and stopped");
    File.Delete(readyFile);
    File.Delete(Path.Combine(data, ".env"));
    using var invalidRecovery = Process.Start(launch) ?? throw new InvalidOperationException("invalid recovery fixture did not start");
    try
    {
        Assert(!await UpdateProcess.WaitForHealthAsync(invalidRecovery, readyFile, null, TimeSpan.FromSeconds(10)), "missing restored configuration rejected");
        Assert(invalidRecovery.WaitForExit(5000) && invalidRecovery.ExitCode != 0, "invalid recovery failed explicitly");
    }
    finally
    {
        UpdateProcess.Stop(invalidRecovery, "invalid recovery process did not stop");
        UpdateTransaction.Restore(backup, installation, data);
    }
    Assert(HashFiles(data).SequenceEqual(originalData), "data still restored after negative recovery test");
    Console.WriteLine("PASS: missing restored configuration rejected without false readiness");
    Console.WriteLine("PASS: real Inno installer failure, production snapshot/install/restore operations");
    Console.WriteLine(root);
}
finally
{
    Environment.SetEnvironmentVariable("TKCRM_ROLLBACK_FIXTURE_DATA", null);
    Environment.SetEnvironmentVariable("TKCRM_ROLLBACK_FIXTURE_INSTALL", null);
}

static void Assert(bool condition, string name)
{
    if (!condition) throw new InvalidOperationException("Failed: " + name);
}

static string[] HashFiles(string directory) => Directory.EnumerateFiles(directory, "*", SearchOption.AllDirectories)
    .Select(file => Path.GetRelativePath(directory, file) + " " + Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(file))))
    .OrderBy(value => value, StringComparer.Ordinal).ToArray();

static async Task RunFixture(string readyFile, string data)
{
    Assert(File.ReadAllText(Path.Combine(data, "monitor.db")) == "old database", "restored database loaded");
    Assert(File.ReadAllText(Path.Combine(data, ".env")) == "old configuration", "restored configuration loaded");
    var listener = new TcpListener(IPAddress.Loopback, 0);
    listener.Start();
    try
    {
        var port = ((IPEndPoint)listener.LocalEndpoint).Port;
        File.WriteAllText(readyFile, JsonSerializer.Serialize(new { pid = Environment.ProcessId, port, version = "1.0.0" }));
        while (true)
        {
            using var connection = await listener.AcceptTcpClientAsync();
            await using var stream = connection.GetStream();
            using var reader = new StreamReader(stream, leaveOpen: true);
            string? line;
            do { line = await reader.ReadLineAsync(); } while (!string.IsNullOrEmpty(line));
            var body = "{\"status\":\"ok\",\"version\":\"1.0.0\"}";
            var response = System.Text.Encoding.UTF8.GetBytes("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + body.Length + "\r\nConnection: close\r\n\r\n" + body);
            await stream.WriteAsync(response);
        }
    }
    finally { listener.Stop(); }
}
