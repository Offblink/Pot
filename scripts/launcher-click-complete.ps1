# Click the 「✓ 完成」button of the topmost card in the launcher board's review
# column — the one acceptance step that exists only in the UI (API-level paths are
# covered by tests/test_board_routes.py, and an agent is what puts a card into
# review in the first place).
#
# The button is found by its colour, not by a hardcoded pixel: the palette's
# primary green in both themes (light #15803D, dark #4ADE80), scanned below the
# page header for a pill-sized filled run. Coordinates are recomputed every run,
# so moving or resizing the window does not break it.
#
# Usage:
#   powershell -File scripts/launcher-click-complete.ps1            # click
#   powershell -File scripts/launcher-click-complete.ps1 -DryRun    # print only
# Exit codes: 0 clicked (or -DryRun found it), 1 no window, 2 no button found.
param(
    [switch]$DryRun
)

Add-Type -AssemblyName System.Drawing
$code = @"
using System;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Text;
public class PotWin {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extra);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
}

public class PotScan {
  static bool Near(Color c, int r, int g, int b, int tol) {
    return Math.Abs(c.R - r) <= tol && Math.Abs(c.G - g) <= tol && Math.Abs(c.B - b) <= tol;
  }
  /* Topmost pill-sized horizontal run of the primary green: {cx, cy, w, h} or null.
     A run narrower than 45px is a card's status bar, wider than 220 is not a
     button; the height check rejects a one-pixel hairline. */
  public static int[] FindButton(Bitmap bmp, int minY, int r, int g, int b) {
    int w = bmp.Width, h = bmp.Height;
    for (int y = minY; y < h - 12; y++) {
      int start = -1;
      for (int x = 0; x <= w; x++) {
        bool hit = x < w && Near(bmp.GetPixel(x, y), r, g, b, 14);
        if (hit && start < 0) start = x;
        if (!hit && start >= 0) {
          int len = x - start;
          if (len >= 45 && len <= 220) {
            int mid = start + len / 2, hh = 1;
            while (y + hh < h && Near(bmp.GetPixel(mid, y + hh), r, g, b, 14)) hh++;
            if (hh >= 14 && hh <= 46) return new int[] { mid, y + hh / 2, len, hh };
          }
          start = -1;
        }
      }
    }
    return null;
  }
}
"@
Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition $code
[void][PotWin]::SetProcessDPIAware()

# ── find the launcher window (the WebUI page is titled "Pot" too: filter by process) ──
$target = [IntPtr]::Zero
[PotWin]::EnumWindows({ param($h, $l)
    if ([PotWin]::IsWindowVisible($h)) {
        $sb = New-Object System.Text.StringBuilder 256
        [void][PotWin]::GetWindowText($h, $sb, 256)
        if ($sb.ToString() -eq 'Pot') {
            $procId = 0
            [void][PotWin]::GetWindowThreadProcessId($h, [ref]$procId)
            try {
                if ((Get-Process -Id $procId -ErrorAction Stop).ProcessName -eq 'java') { $script:target = $h }
            } catch {}
        }
    }
    return $true
}, [IntPtr]::Zero) | Out-Null

if ($target -eq [IntPtr]::Zero) { Write-Output "no launcher window (is the CMP launcher running?)"; exit 1 }
[void][PotWin]::ShowWindow($target, 9)   # SW_RESTORE
Start-Sleep -Milliseconds 900            # let the restore finish painting

$r = New-Object PotWin+RECT
[void][PotWin]::GetWindowRect($target, [ref]$r)
$w = $r.Right - $r.Left
$h = $r.Bottom - $r.Top
$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($r.Left, $r.Top, 0, 0, $bmp.Size)
$g.Dispose()

# Below the page header ("+ 新建卡" is the same green and lives there), above the
# taskbar; the board's first row of cards starts around 0.25h.
$minY = [int][Math]::Max(215, $h * 0.22)
$found = [PotScan]::FindButton($bmp, $minY, 0x15, 0x80, 0x3D)
if (-not $found) { $found = [PotScan]::FindButton($bmp, $minY, 0x4A, 0xDE, 0x80) }
$bmp.Dispose()

if (-not $found) {
    Write-Output "no 完成 button found - is a card sitting in the review column?"
    exit 2
}
$cx = $r.Left + $found[0]
$cy = $r.Top + $found[1]
Write-Output ("button {0}x{1} at window ({2},{3}) -> screen ({4},{5})" -f `
    $found[2], $found[3], $found[0], $found[1], $cx, $cy)

if ($DryRun) { exit 0 }

# Click it: one pixel of motion first, then press/release (a click that arrives
# with no motion right after a window raise can be dropped).
[void][PotWin]::SetCursorPos($cx - 2, $cy - 2)
Start-Sleep -Milliseconds 120
[void][PotWin]::SetCursorPos($cx, $cy)
Start-Sleep -Milliseconds 120
[PotWin]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 70
[PotWin]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
Write-Output "clicked"
exit 0
