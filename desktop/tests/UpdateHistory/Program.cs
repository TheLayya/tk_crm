using System.Text.Json;
using TkCrm.Updater;

var directory = Path.Combine(Path.GetTempPath(), "TkCRM-history-test-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(directory);
var manifestPath = Path.Combine(directory, "release.json");
var url = "https://github.com/TheLayya/tk_crm/releases/download/v2.0.0/setup.exe";
var checksum = new string('a', 64);
File.WriteAllText(manifestPath, JsonSerializer.Serialize(new { version = "2.0.0", windows_package_url = url, windows_sha256 = checksum, date = "2026-10-05", changes = new[] { "保留中文更新说明" } }));
using var manifest = UpdateHistory.LoadManifest(manifestPath, "v2.0.0", url, checksum);
var historyPath = Path.Combine(directory, "update-history.json");
File.WriteAllText(historyPath, "[{\"version\":\"1.0.0\"}]");
UpdateHistory.Record(directory, manifest.RootElement);
using (var history = JsonDocument.Parse(File.ReadAllText(historyPath)))
{
    if (history.RootElement.GetArrayLength() != 2
        || history.RootElement[0].GetProperty("changes")[0].GetString() != "保留中文更新说明"
        || history.RootElement[1].GetProperty("version").GetString() != "1.0.0")
        throw new Exception("History append failed");
}
for (var index = 0; index < 55; index++) UpdateHistory.Record(directory, manifest.RootElement);
using (var history = JsonDocument.Parse(File.ReadAllText(historyPath)))
    if (history.RootElement.GetArrayLength() != 50) throw new Exception("History limit failed");
File.WriteAllText(historyPath, "invalid history");
try { UpdateHistory.Record(directory, manifest.RootElement); throw new Exception("Corrupt history accepted"); }
catch (JsonException) { }
if (File.ReadAllText(historyPath) != "invalid history") throw new Exception("Corrupt history overwritten");
try { using var invalid = UpdateHistory.LoadManifest(manifestPath, "3.0.0", url, checksum); throw new Exception("Mismatched manifest accepted"); }
catch (InvalidOperationException) { }
Console.WriteLine("PASS: append, Unicode, retention, corrupt-history preservation, manifest mismatch");
Console.WriteLine(directory);
