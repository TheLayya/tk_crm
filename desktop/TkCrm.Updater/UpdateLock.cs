using System.Diagnostics;

namespace TkCrm.Updater;

/// <summary>Owns the per-user update lock for the whole update transaction.</summary>
public sealed class UpdateLock : IDisposable
{
    private readonly FileStream stream;

    private UpdateLock(FileStream stream) => this.stream = stream;

    public static async Task<UpdateLock?> AcquireAsync(string statusFile, TimeSpan timeout)
    {
        var wait = Stopwatch.StartNew();
        while (true)
        {
            if (TryAcquire(statusFile, out var acquired)) return acquired;
            if (wait.Elapsed >= timeout) return null;
            await Task.Delay(50);
        }
    }

    public static bool TryAcquire(string statusFile, out UpdateLock? updateLock)
    {
        var lockPath = statusFile + ".lock";
        Directory.CreateDirectory(Path.GetDirectoryName(lockPath)!);
        try
        {
            updateLock = new UpdateLock(new FileStream(
                lockPath, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None));
            return true;
        }
        catch (IOException error) when (IsSharingViolation(error))
        {
            updateLock = null;
            return false;
        }
    }

    private static bool IsSharingViolation(IOException error)
    {
        var code = unchecked((uint)error.HResult) & 0xffff;
        return code is 32 or 33;
    }

    public void Dispose() => stream.Dispose();
}
