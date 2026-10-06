using System.Diagnostics;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;

namespace TkCrm.Desktop;

public sealed class ManagedServer : IDisposable
{
    private readonly Process process;
    private bool disposed;

    private ManagedServer(Process process, int port)
    {
        this.process = process;
        Port = port;
    }

    public int Port { get; }

    public static async Task<ManagedServer?> StartFromEnvironmentAsync(CancellationToken cancellationToken = default, string? legacyDirectory = null, string? updateAgentUrl = null, string? updateAgentToken = null)
    {
        var executable = Environment.GetEnvironmentVariable("TKCRM_SERVER_EXE");
        if (string.IsNullOrWhiteSpace(executable))
        {
            executable = Path.Combine(AppContext.BaseDirectory, "server", "TkCrm.Server.exe");
            if (!File.Exists(executable)) return null;
        }
        if (!File.Exists(executable)) throw new FileNotFoundException("找不到 TkCRM 服务程序", executable);

        var port = FindPort();
        var workingDirectory = Environment.GetEnvironmentVariable("TKCRM_SERVER_DIR")
            ?? Path.GetDirectoryName(executable)
            ?? Environment.CurrentDirectory;
        var dataDirectory = Environment.GetEnvironmentVariable("TKCRM_DATA_DIR");
        var startInfo = new ProcessStartInfo(executable)
        {
            WorkingDirectory = workingDirectory,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardInput = true,
        };
        startInfo.Environment["HOST"] = "127.0.0.1";
        startInfo.Environment["TKCRM_MANAGED"] = "1";
        startInfo.Environment["PYTHONUTF8"] = "1";
        startInfo.Environment["PORT"] = port.ToString();
        startInfo.Environment["UPDATE_CLIENT_TYPE"] = "desktop";
        startInfo.Environment["TKCRM_DESKTOP_AGENT_URL"] = updateAgentUrl ?? "";
        startInfo.Environment["TKCRM_DESKTOP_AGENT_TOKEN"] = updateAgentToken ?? "";
        if (!string.IsNullOrWhiteSpace(legacyDirectory)) startInfo.Environment["TKCRM_LEGACY_DATA_DIR"] = legacyDirectory;
        if (!string.IsNullOrWhiteSpace(dataDirectory))
        {
            Directory.CreateDirectory(dataDirectory);
            startInfo.Environment["TKCRM_DATA_DIR"] = dataDirectory;
        }
        var staticDirectory = Environment.GetEnvironmentVariable("TKCRM_STATIC_DIR");
        if (!string.IsNullOrWhiteSpace(staticDirectory)) startInfo.Environment["STATIC_DIR"] = staticDirectory;

        var process = Process.Start(startInfo) ?? throw new InvalidOperationException("无法启动 TkCRM 服务程序");
        var server = new ManagedServer(process, port);
        try
        {
            await server.WaitForHealthAsync(cancellationToken);
            return server;
        }
        catch
        {
            server.Dispose();
            throw;
        }
    }

    private async Task WaitForHealthAsync(CancellationToken cancellationToken)
    {
        using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(2) };
        var deadline = DateTime.UtcNow.AddSeconds(30);
        while (DateTime.UtcNow < deadline)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (process.HasExited) throw new InvalidOperationException($"TkCRM 服务提前退出，退出码：{process.ExitCode}");
            try
            {
                using var response = await client.GetAsync($"http://127.0.0.1:{Port}/health", cancellationToken);
                if (response.IsSuccessStatusCode) return;
            }
            catch (HttpRequestException) { }
            catch (TaskCanceledException) when (!cancellationToken.IsCancellationRequested) { }
            await Task.Delay(250, cancellationToken);
        }
        throw new TimeoutException("TkCRM 服务启动超时");
    }

    private static int FindPort()
    {
        for (var port = 8000; port < 8010; port++)
        {
            try
            {
                using var listener = new TcpListener(IPAddress.Loopback, port);
                listener.Start();
                listener.Stop();
                return port;
            }
            catch (SocketException) { }
        }
        throw new InvalidOperationException("8000-8009 端口均已被占用");
    }

    public void Dispose()
    {
        if (disposed) return;
        disposed = true;
        if (!process.HasExited)
        {
            try
            {
                process.StandardInput.WriteLine("shutdown");
                process.StandardInput.Close();
                if (!process.WaitForExit(8000))
                {
                    process.Kill(entireProcessTree: true);
                    process.WaitForExit(5000);
                }
            }
            catch (IOException)
            {
                if (!process.HasExited) process.Kill(entireProcessTree: true);
            }
        }
        process.Dispose();
    }
}
