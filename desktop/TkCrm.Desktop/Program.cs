using System.Threading;

namespace TkCrm.Desktop;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        using var instance = new Mutex(true, "TkCRM.Desktop.SingleInstance", out var created);
        if (!created)
        {
            MessageBox.Show("TkCRM 已经在运行中。", "TkCRM", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }

        ApplicationConfiguration.Initialize();
        Application.Run(new MainForm());
    }
}
