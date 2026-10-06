param([Parameter(Mandatory = $true)][System.Diagnostics.Process]$DesktopProcess)

$ErrorActionPreference = 'Stop'
if (-not ('TkCrmSmokeWindow' -as [type])) {
  Add-Type @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class TkCrmSmokeWindow {
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr window, uint message, IntPtr first, IntPtr second);
    [DllImport("user32.dll")] private static extern bool EnumWindows(EnumWindowsProc callback, IntPtr state);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);
    [DllImport("user32.dll")] private static extern IntPtr GetWindow(IntPtr window, uint command);
    [DllImport("user32.dll")] private static extern IntPtr GetDlgItem(IntPtr dialog, int item);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetClassName(IntPtr window, StringBuilder name, int capacity);
    private delegate bool EnumWindowsProc(IntPtr window, IntPtr state);
    public static IntPtr FindMain(int processId) {
        IntPtr found = IntPtr.Zero;
        EnumWindows((window, state) => {
            uint owner; GetWindowThreadProcessId(window, out owner);
            var name = new StringBuilder(128); GetClassName(window, name, name.Capacity);
            if (owner == (uint)processId && GetWindow(window, 4) == IntPtr.Zero && name.ToString().StartsWith("WindowsForms10.Window.")) {
                found = window; return false;
            }
            return true;
        }, IntPtr.Zero);
        return found;
    }
    public static IntPtr FindConfirmation(int processId, IntPtr main) {
        IntPtr found = IntPtr.Zero;
        EnumWindows((window, state) => {
            uint owner; GetWindowThreadProcessId(window, out owner);
            var name = new StringBuilder(64); GetClassName(window, name, name.Capacity);
            if (owner == (uint)processId && name.ToString() == "#32770" && GetDlgItem(window, 6) != IntPtr.Zero) {
                IntPtr parent = GetWindow(window, 4);
                if (parent == main || parent == IntPtr.Zero) { found = window; return false; }
            }
            return true;
        }, IntPtr.Zero);
        return found;
    }
}
'@
}
$deadline = (Get-Date).AddSeconds(5)
$main = [IntPtr]::Zero
while ($main -eq [IntPtr]::Zero -and (Get-Date) -lt $deadline) {
  $main = [TkCrmSmokeWindow]::FindMain($DesktopProcess.Id)
  if ($main -eq [IntPtr]::Zero) { Start-Sleep -Milliseconds 100 }
}
if ($main -eq [IntPtr]::Zero) { throw 'Fixture desktop main window not found' }
if (-not [TkCrmSmokeWindow]::PostMessage($main, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)) { throw 'Fixture close request failed' }
$deadline = (Get-Date).AddSeconds(5)
$dialog = [IntPtr]::Zero
while ($dialog -eq [IntPtr]::Zero -and (Get-Date) -lt $deadline) {
  $dialog = [TkCrmSmokeWindow]::FindConfirmation($DesktopProcess.Id, $main)
  if ($dialog -eq [IntPtr]::Zero) { Start-Sleep -Milliseconds 100 }
}
if ($dialog -eq [IntPtr]::Zero) { throw 'Fixture exit confirmation not found' }
if (-not [TkCrmSmokeWindow]::PostMessage($dialog, 0x0111, [IntPtr]6, [IntPtr]::Zero)) { throw 'Fixture exit confirmation failed' }
if (-not $DesktopProcess.WaitForExit(10000)) { throw 'Fixture desktop did not exit normally' }
