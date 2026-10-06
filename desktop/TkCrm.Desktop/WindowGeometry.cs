namespace TkCrm.Desktop;

internal static class WindowGeometry
{
    public static Size ClampSize(Size requested, Size minimum, Rectangle workingArea)
    {
        var width = Math.Clamp(requested.Width, minimum.Width, workingArea.Width);
        var height = Math.Clamp(requested.Height, minimum.Height, workingArea.Height);
        return new Size(width, height);
    }

    public static Point ClampLocation(Point requested, Size windowSize, Rectangle workingArea)
    {
        return new Point(
            Math.Clamp(requested.X, workingArea.Left, workingArea.Right - windowSize.Width),
            Math.Clamp(requested.Y, workingArea.Top, workingArea.Bottom - windowSize.Height));
    }
}
