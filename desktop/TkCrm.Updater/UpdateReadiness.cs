using System.Text.Json;

namespace TkCrm.Updater;

public static class UpdateReadiness
{
    public static async Task<bool> CheckAsync(HttpClient client, string readyFile, int processId, string? expectedVersion)
    {
        try
        {
            using var ready = JsonDocument.Parse(await File.ReadAllTextAsync(readyFile));
            var receipt = ready.RootElement;
            var version = receipt.GetProperty("version").GetString();
            if (receipt.GetProperty("pid").GetInt32() != processId
                || !Version.TryParse(version, out _)
                || (expectedVersion is not null && !string.Equals(version, expectedVersion, StringComparison.OrdinalIgnoreCase))) return false;
            var port = receipt.GetProperty("port").GetInt32();
            if (port < 1 || port > 65535) return false;
            using var response = await client.GetAsync($"http://127.0.0.1:{port}/health");
            if (!response.IsSuccessStatusCode) return false;
            using var health = JsonDocument.Parse(await response.Content.ReadAsStreamAsync());
            return health.RootElement.GetProperty("status").GetString() == "ok"
                && string.Equals(health.RootElement.GetProperty("version").GetString(), version, StringComparison.OrdinalIgnoreCase);
        }
        catch (IOException) { return false; }
        catch (JsonException) { return false; }
        catch (KeyNotFoundException) { return false; }
        catch (InvalidOperationException) { return false; }
        catch (FormatException) { return false; }
        catch (HttpRequestException) { return false; }
        catch (TaskCanceledException) { return false; }
    }
}
