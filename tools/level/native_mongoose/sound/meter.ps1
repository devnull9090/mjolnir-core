param([double]$Seconds = 5)
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] public class MMEnum {}
[Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IMMDeviceEnumerator { [PreserveSig] int EnumAudioEndpoints(int f, int st, out IMMDeviceCollection c); [PreserveSig] int GetDefaultAudioEndpoint(int f, int r, out IMMDevice d); }
[Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IMMDeviceCollection { [PreserveSig] int GetCount(out int n); [PreserveSig] int Item(int i, out IMMDevice d); }
[Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IMMDevice { [PreserveSig] int Activate(ref Guid id, int ctx, IntPtr p, [MarshalAs(UnmanagedType.IUnknown)] out object o); }
[Guid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IAudioSessionManager2 { int a(); int b(); [PreserveSig] int GetSessionEnumerator(out IAudioSessionEnumerator e); }
[Guid("E2F5BB11-0570-40CA-ACDD-3AA01277DEE8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IAudioSessionEnumerator { [PreserveSig] int GetCount(out int n); [PreserveSig] int GetSession(int i, [MarshalAs(UnmanagedType.IUnknown)] out object s); }
[Guid("bfb7ff88-7239-4fc9-8fa2-07c950be9c6d"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IAudioSessionControl2 { int a(); int b(); int c(); int d(); int e(); int f(); int g(); int h(); int i(); int j(); int k(); [PreserveSig] int GetProcessId(out uint pid); }
[Guid("C02216F6-8C67-4B5B-9D00-D008E73E0064"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IAudioMeterInformation { [PreserveSig] int GetPeakValue(out float v); }
public static class Meter {
  public static float[] Read(uint pid, int ms) {
    var en = (IMMDeviceEnumerator)new MMEnum(); IMMDeviceCollection col; en.EnumAudioEndpoints(0, 1, out col); int dn; col.GetCount(out dn);
    IAudioMeterInformation m = null; int n = 0;
    for (int d = 0; d < dn; d++) { IMMDevice dev; col.Item(d, out dev);
      var id = typeof(IAudioSessionManager2).GUID; object o; dev.Activate(ref id, 23, IntPtr.Zero, out o);
      var mgr = (IAudioSessionManager2)o; IAudioSessionEnumerator se; mgr.GetSessionEnumerator(out se); int c0; se.GetCount(out c0); n += c0;
      for (int i = 0; i < c0; i++) { object s; se.GetSession(i, out s); uint p; ((IAudioSessionControl2)s).GetProcessId(out p); if (p == pid) m = (IAudioMeterInformation)s; } }
    if (m == null) return new float[] { -1, -1, n };
    float max = 0, sum = 0; int c = 0; var end = DateTime.Now.AddMilliseconds(ms);
    while (DateTime.Now < end) { float v; m.GetPeakValue(out v); if (v > max) max = v; sum += v; c++; System.Threading.Thread.Sleep(20); }
    return new float[] { max, sum / c, c };
  }
}
"@
$p = (Get-Process HaloCampaignEvolved* | Sort-Object WorkingSet64 -Descending | Select-Object -First 1).Id
$r = [Meter]::Read([uint32]$p, [int]($Seconds * 1000))
"pid $p peak {0:N4} mean {1:N4} samples {2}" -f $r[0], $r[1], $r[2]
