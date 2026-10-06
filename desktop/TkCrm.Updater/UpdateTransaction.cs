using System.Diagnostics;

namespace TkCrm.Updater;

public sealed record UpdateBackup(string Installation, string Data);

public static class UpdateTransaction
{
    public static UpdateBackup Snapshot(string installDirectory, string dataDirectory, string workDirectory)
    {
        var backup = new UpdateBackup(
            Path.Combine(workDirectory, "previous-install"),
            Path.Combine(workDirectory, "previous-data"));
        DirectorySnapshot.CopyDirectory(installDirectory, backup.Installation);
        DirectorySnapshot.CopyDirectory(dataDirectory, backup.Data);
        return backup;
    }

    public static void Install(string installer, string installDirectory)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = installer,
            WorkingDirectory = Path.GetDirectoryName(installer)!,
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        foreach (var argument in new[] { "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOCLOSEAPPLICATIONS", "/NORESTARTAPPLICATIONS", "/DIR=" + installDirectory })
            startInfo.ArgumentList.Add(argument);
        using var process = Process.Start(startInfo) ?? throw new InvalidOperationException("无法启动安装程序");
        process.WaitForExit();
        if (process.ExitCode != 0) throw new InvalidOperationException($"安装程序退出码：{process.ExitCode}");
    }

    public static void Restore(UpdateBackup backup, string installDirectory, string dataDirectory)
    {
        DirectorySnapshot.RestoreDirectory(backup.Installation, installDirectory);
        DirectorySnapshot.RestoreDirectory(backup.Data, dataDirectory);
    }
}
