using System.Net;
using System.Text.Json;
using TkCrm.Updater;

var root = Path.Combine(Path.GetTempPath(), "TkCRM-readiness-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(root);
var readyFile = Path.Combine(root, "ready.json");
using var handler = new FixtureHandler();
using var client = new HttpClient(handler);
foreach (var testCase in new[] { "valid", "wrong_pid", "wrong_receipt_version", "invalid_port", "missing_port", "partial_json", "wrong_health_version", "unhealthy", "http_error", "redirect", "invalid_health_json", "offline", "timeout" })
{
    var receipt = new Dictionary<string, object> { ["pid"] = 42, ["port"] = 12345, ["version"] = "1.2.3" };
    if (testCase == "wrong_pid") receipt["pid"] = 41;
    if (testCase == "wrong_receipt_version") receipt["version"] = "1.2.2";
    if (testCase == "invalid_port") receipt["port"] = 65536;
    if (testCase == "missing_port") receipt.Remove("port");
    File.WriteAllText(readyFile, testCase == "partial_json" ? "{" : JsonSerializer.Serialize(receipt));
    handler.TestCase = testCase;
    var actual = await UpdateReadiness.CheckAsync(client, readyFile, 42, "1.2.3");
    if (actual != (testCase == "valid")) throw new Exception("Failed: " + testCase);
    Console.WriteLine("PASS readiness: " + testCase);
}
Console.WriteLine(root);
foreach (var testCase in new[] { "valid", "wrong_health_version", "empty_version", "invalid_version", "wrong_pid" })
{
    File.WriteAllText(readyFile, JsonSerializer.Serialize(new { pid = testCase == "wrong_pid" ? 41 : 42, port = 12345, version = testCase == "empty_version" ? "" : testCase == "invalid_version" ? "unknown" : "1.2.3" }));
    handler.TestCase = testCase;
    var actual = await UpdateReadiness.CheckAsync(client, readyFile, 42, null);
    if (actual != (testCase == "valid")) throw new Exception("Recovery failed: " + testCase);
    Console.WriteLine("PASS recovery readiness: " + testCase);
}

sealed class FixtureHandler : HttpMessageHandler
{
    public string TestCase { get; set; } = "valid";
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        if (request.RequestUri?.ToString() != "http://127.0.0.1:12345/health") throw new Exception("Unexpected health URL");
        if (TestCase == "offline") throw new HttpRequestException("offline");
        if (TestCase == "timeout") throw new TaskCanceledException("timeout");
        var status = TestCase == "http_error" ? HttpStatusCode.ServiceUnavailable : TestCase == "redirect" ? HttpStatusCode.Redirect : HttpStatusCode.OK;
        var body = TestCase == "invalid_health_json" ? "{" : JsonSerializer.Serialize(new { status = TestCase == "unhealthy" ? "error" : "ok", version = TestCase == "wrong_health_version" ? "1.2.2" : "1.2.3" });
        return Task.FromResult(new HttpResponseMessage(status) { Content = new StringContent(body) });
    }
}
