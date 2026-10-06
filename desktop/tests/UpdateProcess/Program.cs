using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Text.Json;
using TkCrm.Updater;

if (args.Length > 0)
{
    var mode = args[0];
    if (mode == "exit") return;
    if (mode == "leaf") { await Task.Delay(Timeout.Infinite); return; }
    var readyFile = args[1];
    if (mode == "hang")
    {
        using var leaf = Process.Start(StartInfo("leaf")) ?? throw new Exception("Leaf not started");
        File.WriteAllText(readyFile + ".child", leaf.Id.ToString());
        await Task.Delay(Timeout.Infinite);
        return;
    }
    var listener = new TcpListener(IPAddress.Loopback, 0);
    listener.Start();
    var port = ((IPEndPoint)listener.LocalEndpoint).Port;
    File.WriteAllText(readyFile, JsonSerializer.Serialize(new { pid = mode == "wrong_pid" ? Environment.ProcessId + 1 : Environment.ProcessId, port, version = "1.0.0" }));
    while (true)
    {
        using var connection = await listener.AcceptTcpClientAsync();
        await using var stream = connection.GetStream();
        var buffer = new byte[4096];
        await stream.ReadAsync(buffer);
        var body = JsonSerializer.Serialize(new { status = "ok", version = "1.0.0" });
        var response = System.Text.Encoding.UTF8.GetBytes("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + System.Text.Encoding.UTF8.GetByteCount(body) + "\r\nConnection: close\r\n\r\n" + body);
        await stream.WriteAsync(response);
    }
}

var root = Path.Combine(Path.GetTempPath(), "TkCRM-process-fixture-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(root);
foreach (var mode in new[] { "healthy", "recovery", "wrong_pid", "wrong_version", "exit", "hang" })
{
    var readyFile = Path.Combine(root, mode + ".json");
    using var process = Process.Start(StartInfo(mode == "recovery" || mode == "wrong_version" ? "healthy" : mode, readyFile)) ?? throw new Exception("Fixture not started");
    int? childPid = null;
    try
    {
        if (mode == "hang")
        {
            var deadline = DateTime.UtcNow.AddSeconds(10);
            while (!File.Exists(readyFile + ".child") && DateTime.UtcNow < deadline) await Task.Delay(100);
            childPid = int.Parse(File.ReadAllText(readyFile + ".child"));
        }
        var ready = await UpdateProcess.WaitForHealthAsync(process, readyFile, mode == "recovery" ? null : mode == "wrong_version" ? "2.0.0" : "1.0.0", TimeSpan.FromSeconds(4));
        if (ready != (mode == "healthy" || mode == "recovery")) throw new Exception("Unexpected readiness: " + mode);
        UpdateProcess.Stop(process, "Fixture process did not stop");
        if (!process.HasExited) throw new Exception("Fixture still alive");
        if (childPid.HasValue)
        {
            try { using var child = Process.GetProcessById(childPid.Value); if (!child.WaitForExit(5000)) throw new Exception("Descendant survived cleanup"); }
            catch (ArgumentException) { }
        }
        Console.WriteLine("PASS real update process: " + mode);
    }
    finally
    {
        UpdateProcess.Stop(process, "Fixture cleanup failed");
        if (childPid.HasValue)
        {
            try { using var child = Process.GetProcessById(childPid.Value); UpdateProcess.Stop(child, "Leaf cleanup failed"); }
            catch (ArgumentException) { }
        }
    }
}
Console.WriteLine(root);

static ProcessStartInfo StartInfo(params string[] arguments)
{
    var info = new ProcessStartInfo(Environment.ProcessPath!) { UseShellExecute = false, CreateNoWindow = true };
    if (Path.GetFileNameWithoutExtension(Environment.ProcessPath!).Equals("dotnet", StringComparison.OrdinalIgnoreCase)) info.ArgumentList.Add(Assembly.GetExecutingAssembly().Location);
    foreach (var argument in arguments) info.ArgumentList.Add(argument);
    return info;
}
