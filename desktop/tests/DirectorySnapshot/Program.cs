using TkCrm.Updater;

var root = Path.Combine(Path.GetTempPath(), "tkcrm-rollback-" + Guid.NewGuid().ToString("N"));
var installation = Path.Combine(root, "安装目录");
var data = Path.Combine(root, "用户数据");
var installBackup = Path.Combine(root, "previous-install");
var dataBackup = Path.Combine(root, "previous-data");
try
{
    Directory.CreateDirectory(Path.Combine(installation, "server"));
    Directory.CreateDirectory(data);
    File.WriteAllText(Path.Combine(installation, "TkCrm.Desktop.exe"), "old desktop");
    File.WriteAllText(Path.Combine(installation, "server", "TkCrm.Server.exe"), "old server");
    File.WriteAllText(Path.Combine(installation, "old-extra.txt"), "old extra");
    File.WriteAllText(Path.Combine(data, "monitor.db"), "old database");
    File.WriteAllText(Path.Combine(data, ".env"), "old configuration");

    DirectorySnapshot.CopyDirectory(installation, installBackup);
    DirectorySnapshot.CopyDirectory(data, dataBackup);

    Directory.Delete(installation, true);
    Directory.CreateDirectory(installation);
    File.WriteAllText(Path.Combine(installation, "new-only.txt"), "failed update");
    File.WriteAllText(Path.Combine(data, "monitor.db"), "corrupted update");
    File.WriteAllText(Path.Combine(data, "new-only.txt"), "failed update");

    DirectorySnapshot.RestoreDirectory(installBackup, installation);
    DirectorySnapshot.RestoreDirectory(dataBackup, data);

    Assert(File.ReadAllText(Path.Combine(installation, "TkCrm.Desktop.exe")) == "old desktop", "desktop restored");
    Assert(File.ReadAllText(Path.Combine(installation, "server", "TkCrm.Server.exe")) == "old server", "server restored");
    Assert(File.ReadAllText(Path.Combine(installation, "old-extra.txt")) == "old extra", "old file restored");
    Assert(!File.Exists(Path.Combine(installation, "new-only.txt")), "new install file removed");
    Assert(File.ReadAllText(Path.Combine(data, "monitor.db")) == "old database", "database restored");
    Assert(File.ReadAllText(Path.Combine(data, ".env")) == "old configuration", "configuration restored");
    Assert(!File.Exists(Path.Combine(data, "new-only.txt")), "new data file removed");
    Directory.Delete(installation, true);
    Directory.Delete(data, true);
    DirectorySnapshot.RestoreDirectory(installBackup, installation);
    DirectorySnapshot.RestoreDirectory(dataBackup, data);
    Assert(File.ReadAllText(Path.Combine(installation, "server", "TkCrm.Server.exe")) == "old server", "missing installation recreated");
    Assert(File.ReadAllText(Path.Combine(data, "monitor.db")) == "old database", "missing data directory recreated");
    Assert(File.ReadAllText(Path.Combine(data, ".env")) == "old configuration", "missing configuration recreated");
    var missingBackupRejected = false;
    try { DirectorySnapshot.RestoreDirectory(Path.Combine(root, "missing-backup"), data); }
    catch (DirectoryNotFoundException) { missingBackupRejected = true; }
    Assert(missingBackupRejected, "missing backup rejected");
    Assert(File.ReadAllText(Path.Combine(data, "monitor.db")) == "old database", "missing backup leaves data unchanged");
    Console.WriteLine("PASS: deleted installation and modified user data rollback");
}
finally
{
    if (Directory.Exists(root)) Directory.Delete(root, true);
}

static void Assert(bool condition, string name)
{
    if (!condition) throw new InvalidOperationException("Failed: " + name);
}
