using System.Text.Json;
using System.Text.Json.Nodes;

namespace TkCrm.Updater;

public static class UpdateHistory
{
    public static JsonDocument LoadManifest(string path, string version, string url, string checksum)
    {
        if (new FileInfo(path).Length > 256 * 1024)
            throw new InvalidOperationException("发布清单超过大小限制");
        var document = JsonDocument.Parse(File.ReadAllText(path));
        try
        {
            var root = document.RootElement;
            if (!SameVersion(root.GetProperty("version").GetString(), version)
                || root.GetProperty("windows_package_url").GetString() != url
                || !string.Equals(root.GetProperty("windows_sha256").GetString(), checksum, StringComparison.OrdinalIgnoreCase)
                || (root.TryGetProperty("changes", out var changes)
                    && (changes.ValueKind != JsonValueKind.Array || changes.EnumerateArray().Any(item => item.ValueKind != JsonValueKind.String)))
                || (root.TryGetProperty("date", out var date) && date.ValueKind is not (JsonValueKind.String or JsonValueKind.Null)))
                throw new InvalidOperationException("发布清单与更新任务不一致");
            return document;
        }
        catch
        {
            document.Dispose();
            throw;
        }
    }

    private static bool SameVersion(string? left, string right) =>
        string.Equals(left?.TrimStart('v', 'V'), right.TrimStart('v', 'V'), StringComparison.OrdinalIgnoreCase);

    public static void Record(string dataDirectory, JsonElement manifest)
    {
        var path = Path.Combine(dataDirectory, "update-history.json");
        var history = File.Exists(path) ? JsonNode.Parse(File.ReadAllText(path)) as JsonArray : new JsonArray();
        if (history is null) throw new InvalidOperationException("更新历史格式错误，无法安全追加");
        history.Insert(0, new JsonObject
        {
            ["version"] = manifest.GetProperty("version").GetString(),
            ["date"] = manifest.TryGetProperty("date", out var date) ? JsonNode.Parse(date.GetRawText()) : null,
            ["changes"] = manifest.TryGetProperty("changes", out var changes) ? JsonNode.Parse(changes.GetRawText()) : new JsonArray(),
            ["installed_at"] = DateTimeOffset.Now.ToString("O"),
        });
        while (history.Count > 50) history.RemoveAt(history.Count - 1);
        var temporary = path + ".tmp";
        try
        {
            File.WriteAllText(temporary, history.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
            File.Move(temporary, path, true);
        }
        finally
        {
            if (File.Exists(temporary)) File.Delete(temporary);
        }
    }
}
