namespace TkCrm.Updater;

public static class DirectorySnapshot
{
    public static void CopyDirectory(string source, string destination)
    {
        RejectLinks(source);
        Directory.CreateDirectory(destination);
        foreach (var directory in Directory.EnumerateDirectories(source, "*", SearchOption.AllDirectories))
            Directory.CreateDirectory(Path.Combine(destination, Path.GetRelativePath(source, directory)));
        foreach (var file in Directory.EnumerateFiles(source, "*", SearchOption.AllDirectories))
            File.Copy(file, Path.Combine(destination, Path.GetRelativePath(source, file)), true);
    }

    public static void RestoreDirectory(string backup, string destination)
    {
        if (!Directory.Exists(backup)) throw new DirectoryNotFoundException("Rollback snapshot is missing: " + backup);
        RejectLinks(backup);
        Directory.CreateDirectory(destination);
        RejectLinks(destination);
        foreach (var file in Directory.EnumerateFiles(destination, "*", SearchOption.AllDirectories))
        {
            if (!File.Exists(Path.Combine(backup, Path.GetRelativePath(destination, file))))
            {
                File.SetAttributes(file, FileAttributes.Normal);
                File.Delete(file);
            }
        }
        CopyDirectory(backup, destination);
    }

    public static void RejectLinks(string directory)
    {
        if ((File.GetAttributes(directory) & FileAttributes.ReparsePoint) != 0)
            throw new InvalidOperationException("安装目录不能包含符号链接或目录联接");
        foreach (var entry in Directory.EnumerateFileSystemEntries(directory))
        {
            var attributes = File.GetAttributes(entry);
            if ((attributes & FileAttributes.ReparsePoint) != 0)
                throw new InvalidOperationException("安装目录不能包含符号链接或目录联接");
            if ((attributes & FileAttributes.Directory) != 0) RejectLinks(entry);
        }
    }

}
