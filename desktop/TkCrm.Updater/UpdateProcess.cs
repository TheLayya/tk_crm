using System.Diagnostics;

namespace TkCrm.Updater;

public static class UpdateProcess
{
    public static async Task<bool> WaitForHealthAsync(Process launched, string readyFile, string? expectedVersion, TimeSpan timeout)
    {
        var deadline = DateTime.UtcNow + timeout;
        using var client = new HttpClient(new HttpClientHandler { AllowAutoRedirect = false, UseProxy = false }) { Timeout = TimeSpan.FromSeconds(2) };
        while (DateTime.UtcNow < deadline)
        {
            if (launched.HasExited) return false;
            if (await UpdateReadiness.CheckAsync(client, readyFile, launched.Id, expectedVersion) && !launched.HasExited) return true;
            await Task.Delay(500);
        }
        return false;
    }

    public static void Stop(Process process, string failureMessage)
    {
        if (process.HasExited) return;
        process.Kill(entireProcessTree: true);
        if (!process.WaitForExit(10000)) throw new InvalidOperationException(failureMessage);
    }
}
