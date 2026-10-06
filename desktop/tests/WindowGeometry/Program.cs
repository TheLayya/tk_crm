using System.Drawing;
using TkCrm.Desktop;

static void Assert(bool condition, string message)
{
    if (!condition) throw new InvalidOperationException(message);
}

var normalArea = new Rectangle(0, 0, 2560, 1392);
var smallArea = new Rectangle(-1920, 0, 1280, 720);
var minimum = new Size(1180, 720);

var normal = WindowGeometry.ClampSize(new Size(1440, 900), minimum, normalArea);
Assert(normal == new Size(1440, 900), "normal size changed unexpectedly");
Assert(WindowGeometry.ClampSize(new Size(4000, 2000), minimum, normalArea) == new Size(2560, 1392), "large size not clamped");
Assert(WindowGeometry.ClampSize(new Size(400, 300), minimum, normalArea) == minimum, "small size not clamped to minimum");
Assert(WindowGeometry.ClampSize(new Size(1440, 900), minimum, smallArea) == new Size(1280, 720), "small monitor size mismatch");
Assert(WindowGeometry.ClampLocation(new Point(3000, 1300), normal, normalArea) == new Point(1120, 492), "location not clamped to primary area");
Assert(WindowGeometry.ClampLocation(new Point(-3000, -200), new Size(1180, 720), smallArea) == new Point(-1920, 0), "negative monitor location not clamped");

var combinations = 0;
foreach (var area in new[] { normalArea, smallArea, new Rectangle(0, 0, 683, 344), new Rectangle(-1366, -768, 1366, 728) })
{
    var effectiveMinimum = new Size(Math.Min(minimum.Width, area.Width), Math.Min(minimum.Height, area.Height));
    foreach (var requested in new[] { new Size(1440, 900), new Size(4000, 2000), new Size(400, 300) })
    {
        var size = WindowGeometry.ClampSize(requested, effectiveMinimum, area);
        foreach (var location in new[] { new Point(0, 0), new Point(-4000, -2000), new Point(4000, 2000) })
        {
            var clamped = WindowGeometry.ClampLocation(location, size, area);
            Assert(area.Contains(new Rectangle(clamped, size)), "window escaped working area");
            Assert(size.Width >= effectiveMinimum.Width && size.Height >= effectiveMinimum.Height, "window below effective minimum");
            combinations++;
        }
    }
}
Console.WriteLine($"PASS native window geometry: {combinations} working-area/size/location combinations");
