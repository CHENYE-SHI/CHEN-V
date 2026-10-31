using System;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Windows.Forms;

/// <summary>
/// CHEN-V 安装程序（单文件、直接安装）。
///
/// 核心思路（对齐成熟安装器的做法）：
///   1. exe 末尾拼接 [ZIP 数据][8 字节小端 = ZIP 起始偏移]；
///   2. 双击立即出界面，选定目录后【直接把 ZIP 条目解压到安装目录】，
///      不经 %TEMP% 中转 —— 只写一遍 2.3GB，不额外占 C 盘、不多花一次复制时间；
///   3. 装完写注册表卸载项、桌面快捷方式、卸载脚本，可选立即运行。
///
/// 也支持静默安装：CHEN-V_Setup.exe /S:"D:\CHEN-V"
/// </summary>
class SetupApp : Form
{
    public const string APP_NAME = "CHEN-V";
    public const string APP_VER = "1.01";
    public const string APP_PUBLISHER = "辰师";
    public const string APP_URL = "https://github.com/CHENYE-SHI/CHEN-V";
    public const string SKIP_DIR = "installer_py/";
    public const string APP_EXE = "CHEN-V.exe";

    enum Step { Welcome, Installing, Done }

    double[][] _parts;
    double _t;
    readonly System.Windows.Forms.Timer _anim;

    Step _step = Step.Welcome;
    string _target;
    string _status = "";
    double _progress;
    bool _failed;
    string _errMsg;
    bool _runAfter = true;
    string _doneText = "";

    Image _icon;

    Rectangle _rcChange, _rcPrimary, _rcCheck;
    int _hot = -1;

    public SetupApp()
    {
        Text = APP_NAME + " 安装程序";
        ClientSize = new Size(660, 460);
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = Color.FromArgb(14, 16, 26);
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer
                 | ControlStyles.UserPaint | ControlStyles.ResizeRedraw, true);

        _icon = Engine.LoadIcon();
        _parts = Engine.BuildParticles(28);
        _target = Engine.DefaultDir();

        _anim = new System.Windows.Forms.Timer();
        _anim.Interval = 33;
        _anim.Tick += delegate { _t += 0.033; Invalidate(); };
        _anim.Start();

        int w = ClientSize.Width, h = ClientSize.Height;
        _rcChange = new Rectangle(60, h - 96, 108, 40);
        _rcPrimary = new Rectangle(w - 60 - 176, h - 96, 176, 40);
        _rcCheck = new Rectangle(60, h - 60, 220, 24);
    }

    // ------------------------------------------------------------------ 绘制
    protected override void OnPaint(PaintEventArgs e)
    {
        Graphics g = e.Graphics;
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;
        int w = ClientSize.Width, h = ClientSize.Height;

        using (var bg = new LinearGradientBrush(new Rectangle(0, 0, w, h),
                   Color.FromArgb(22, 26, 44), Color.FromArgb(11, 13, 22), 90f))
            g.FillRectangle(bg, 0, 0, w, h);

        double cx = w / 2.0, cy = h * 0.44;
        foreach (var p in _parts)
        {
            double ang = p[0] + _t * p[1];
            float x = (float)(cx + Math.Cos(ang) * p[2] * w);
            float y = (float)(cy + Math.Sin(ang) * p[3] * h);
            float rad = (float)p[4];
            double twoPi = Math.PI * 2;
            double nrm = ((ang % twoPi) + twoPi) % twoPi;
            Color c = Engine.FromHue(188.0 + nrm / twoPi * 152.0);
            using (var br = new SolidBrush(Color.FromArgb((int)(p[5] * 175), c)))
                g.FillEllipse(br, x - rad, y - rad, rad * 2, rad * 2);
        }

        if (_icon != null) g.DrawImage(_icon, new Rectangle(w / 2 - 32, 34, 64, 64));

        if (_step == Step.Welcome) DrawWelcome(g, w, h);
        else if (_step == Step.Installing) DrawInstalling(g, w, h);
        else DrawDone(g, w, h);
    }

    void DrawWelcome(Graphics g, int w, int h)
    {
        Txt(g, "安装 " + APP_NAME, 20f, FontStyle.Bold, Color.FromArgb(240, 245, 250),
             new RectangleF(0, 112, w, 38), StringAlignment.Center);
        Txt(g, "版本 V" + APP_VER + "  ·  " + APP_PUBLISHER, 10f, FontStyle.Regular,
             Color.FromArgb(150, 165, 182), new RectangleF(0, 150, w, 24), StringAlignment.Center);

        Txt(g, "安装位置", 9.5f, FontStyle.Regular, Color.FromArgb(140, 155, 175),
             new RectangleF(60, 204, w - 120, 22), StringAlignment.Near);

        using (var path = Engine.Round(60, 228, w - 120, 38, 8))
        using (var fill = new SolidBrush(Color.FromArgb(26, 255, 255, 255)))
        using (var pen = new Pen(Color.FromArgb(44, 255, 255, 255)))
        {
            g.FillPath(fill, path);
            g.DrawPath(pen, path);
        }
        Txt(g, _target, 10f, FontStyle.Regular, Color.FromArgb(222, 232, 242),
             new RectangleF(74, 236, w - 148, 24), StringAlignment.Near);

        Btn(g, _rcChange, "更改", _hot == 0, false);
        Btn(g, _rcPrimary, "开始安装", _hot == 1, true);

        Txt(g, "包含程序本体、Python 运行时、模型与 VapourSynth（约 2.3 GB）",
             8.5f, FontStyle.Regular, Color.FromArgb(104, 116, 134),
             new RectangleF(0, h - 32, w, 20), StringAlignment.Center);
    }

    void DrawInstalling(Graphics g, int w, int h)
    {
        Txt(g, _failed ? "安装失败" : "正在安装…", 19f, FontStyle.Bold,
             _failed ? Color.FromArgb(255, 138, 128) : Color.FromArgb(240, 245, 250),
             new RectangleF(0, 112, w, 38), StringAlignment.Center);
        Txt(g, "版本 V" + APP_VER + "  ·  " + APP_PUBLISHER, 9.5f, FontStyle.Regular,
             Color.FromArgb(140, 155, 175), new RectangleF(0, 150, w, 22), StringAlignment.Center);

        Txt(g, _failed ? (_errMsg ?? "未知错误") : _status, 10f, FontStyle.Regular,
             Color.FromArgb(210, 220, 230), new RectangleF(50, 232, w - 100, 24), StringAlignment.Center);

        int bx = 80, by = 272, bw = w - 160, bh = 12;
        using (var path = Engine.Round(bx, by, bw, bh, 6))
        using (var track = new SolidBrush(Color.FromArgb(34, 255, 255, 255)))
            g.FillPath(track, path);
        int fill = (int)(bw * Math.Max(0, Math.Min(1, _progress)));
        if (fill > 2)
        {
            using (var path = Engine.Round(bx, by, fill, bh, 6))
            using (var grad = new LinearGradientBrush(new Rectangle(bx, by, Math.Max(fill, 2), bh),
                       Color.FromArgb(58, 123, 213), Color.FromArgb(106, 90, 205), 0f))
                g.FillPath(grad, path);
        }
        Txt(g, ((int)(_progress * 100)) + "%", 9f, FontStyle.Regular,
             Color.FromArgb(140, 155, 175), new RectangleF(0, by + 20, w, 22), StringAlignment.Center);

        Txt(g, _target, 8.5f, FontStyle.Regular, Color.FromArgb(104, 116, 134),
             new RectangleF(0, h - 58, w, 20), StringAlignment.Center);
    }

    void DrawDone(Graphics g, int w, int h)
    {
        Txt(g, "安装完成", 20f, FontStyle.Bold, Color.FromArgb(240, 245, 250),
             new RectangleF(0, 112, w, 38), StringAlignment.Center);
        Txt(g, "版本 V" + APP_VER + "  ·  " + APP_PUBLISHER, 10f, FontStyle.Regular,
             Color.FromArgb(150, 165, 182), new RectangleF(0, 150, w, 24), StringAlignment.Center);

        Txt(g, "CHEN-V 已安装到：", 9.5f, FontStyle.Regular, Color.FromArgb(150, 165, 182),
             new RectangleF(60, 208, w - 120, 22), StringAlignment.Near);
        Txt(g, _target, 10f, FontStyle.Regular, Color.FromArgb(226, 234, 244),
             new RectangleF(60, 232, w - 120, 24), StringAlignment.Near);
        if (!string.IsNullOrEmpty(_doneText))
            Txt(g, _doneText, 9f, FontStyle.Regular, Color.FromArgb(255, 190, 120),
                 new RectangleF(60, 262, w - 120, 22), StringAlignment.Near);

        DrawCheck(g, _rcCheck, _runAfter, _hot == 2);
        Txt(g, "立即运行 " + APP_NAME, 9.5f, FontStyle.Regular, Color.FromArgb(214, 223, 232),
             new RectangleF(_rcCheck.X + 28, _rcCheck.Y - 1, 240, 24), StringAlignment.Near);

        Btn(g, _rcPrimary, "完成", _hot == 1, true);
    }

    void DrawCheck(Graphics g, Rectangle r, bool on, bool hot)
    {
        var box = new Rectangle(r.X, r.Y + 3, 16, 16);
        using (var path = Engine.Round(box.X, box.Y, box.Width, box.Height, 5))
        {
            if (on)
            {
                using (var grad = new LinearGradientBrush(box, Color.FromArgb(58, 123, 213),
                           Color.FromArgb(106, 90, 205), 0f))
                    g.FillPath(grad, path);
            }
            else
            {
                using (var f = new SolidBrush(Color.FromArgb(hot ? 30 : 12, 255, 255, 255)))
                    g.FillPath(f, path);
                using (var pen = new Pen(Color.FromArgb(70, 255, 255, 255)))
                    g.DrawPath(pen, path);
            }
        }
        if (on)
        {
            using (var pen = new Pen(Color.White, 2f))
            {
                g.DrawLine(pen, box.X + 4, box.Y + 8, box.X + 7, box.Y + 11);
                g.DrawLine(pen, box.X + 7, box.Y + 11, box.X + 12, box.Y + 5);
            }
        }
    }

    void Btn(Graphics g, Rectangle r, string text, bool hot, bool primary)
    {
        using (var path = Engine.Round(r.X, r.Y, r.Width, r.Height, 9))
        {
            if (primary)
            {
                int d = hot ? 16 : 0;
                using (var grad = new LinearGradientBrush(r,
                           Color.FromArgb(58 + d, 123 + d, 213), Color.FromArgb(106 + d, 90, 205), 0f))
                    g.FillPath(grad, path);
            }
            else
            {
                using (var f = new SolidBrush(Color.FromArgb(hot ? 44 : 26, 255, 255, 255)))
                    g.FillPath(f, path);
                using (var pen = new Pen(Color.FromArgb(48, 255, 255, 255)))
                    g.DrawPath(pen, path);
            }
        }
        Txt(g, text, 10.5f, primary ? FontStyle.Bold : FontStyle.Regular,
            Color.White, r, StringAlignment.Center);
    }

    void Txt(Graphics g, string s, float size, FontStyle style, Color color,
             RectangleF rc, StringAlignment align)
    {
        using (var f = new Font("Microsoft YaHei UI", size, style))
        using (var br = new SolidBrush(color))
        using (var sf = new StringFormat
        {
            Alignment = align,
            LineAlignment = StringAlignment.Center,
            Trimming = StringTrimming.EllipsisCharacter,
            FormatFlags = StringFormatFlags.NoWrap
        })
            g.DrawString(s ?? "", f, br, rc, sf);
    }

    // ------------------------------------------------------------------ 交互
    protected override void OnMouseMove(MouseEventArgs e)
    {
        base.OnMouseMove(e);
        int hot = -1;
        if (_step == Step.Welcome)
        {
            if (_rcChange.Contains(e.Location)) hot = 0;
            else if (_rcPrimary.Contains(e.Location)) hot = 1;
        }
        else if (_step == Step.Done)
        {
            if (_rcCheck.Contains(e.Location)) hot = 2;
            else if (_rcPrimary.Contains(e.Location)) hot = 1;
        }
        if (hot != _hot)
        {
            _hot = hot;
            Cursor = hot >= 0 ? Cursors.Hand : Cursors.Default;
            Invalidate();
        }
    }

    protected override void OnMouseClick(MouseEventArgs e)
    {
        base.OnMouseClick(e);
        if (_step == Step.Welcome)
        {
            if (_rcChange.Contains(e.Location)) ChooseDir();
            else if (_rcPrimary.Contains(e.Location)) StartInstall();
        }
        else if (_step == Step.Done)
        {
            if (_rcCheck.Contains(e.Location)) { _runAfter = !_runAfter; Invalidate(); }
            else if (_rcPrimary.Contains(e.Location)) FinishAndClose();
        }
    }

    int _closingAllowed = 0;
    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        if (_step == Step.Installing && _closingAllowed == 0 && !_failed)
        {
            if (MessageBox.Show(this, "安装正在进行，确定要退出吗？", APP_NAME,
                    MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes)
            {
                e.Cancel = true;
                return;
            }
        }
        base.OnFormClosing(e);
    }

    void ChooseDir()
    {
        using (var dlg = new FolderBrowserDialog())
        {
            dlg.Description = "选择安装位置（将在该目录下创建 " + APP_NAME + " 文件夹）";
            dlg.SelectedPath = Path.GetDirectoryName(_target) ?? _target;
            dlg.ShowNewFolderButton = true;
            if (dlg.ShowDialog(this) == DialogResult.OK)
            {
                _target = Path.Combine(dlg.SelectedPath, APP_NAME);
                Invalidate();
            }
        }
    }

    void StartInstall()
    {
        if (string.IsNullOrEmpty(_target)) return;
        _step = Step.Installing;
        _failed = false;
        _progress = 0;
        _status = "准备中…";
        Invalidate();

        string target = _target;
        var th = new Thread(delegate ()
        {
            try
            {
                string note = Engine.Install(target, delegate (string s, double p)
                {
                    if (IsDisposed) return;
                    try
                    {
                        BeginInvoke((Action)delegate
                        {
                            if (_failed) return;
                            _status = s;
                            _progress = p;
                            Invalidate();
                        });
                    }
                    catch { }
                });
                if (IsDisposed) return;
                try
                {
                    BeginInvoke((Action)delegate
                    {
                        _doneText = note;
                        _step = Step.Done;
                        Invalidate();
                    });
                }
                catch { }
            }
            catch (Exception ex)
            {
                if (IsDisposed) return;
                try
                {
                    BeginInvoke((Action)delegate
                    {
                        _failed = true;
                        _errMsg = ex.Message;
                        Invalidate();
                    });
                }
                catch { }
            }
        });
        th.IsBackground = true;
        th.Start();
    }

    void FinishAndClose()
    {
        if (_runAfter)
        {
            try
            {
                Process.Start(new ProcessStartInfo
                {
                    FileName = Path.Combine(_target, APP_EXE),
                    WorkingDirectory = _target,
                    UseShellExecute = true
                });
            }
            catch { }
        }
        _closingAllowed = 1;
        Close();
    }

    [STAThread]
    static void Main(string[] args)
    {
        // 静默安装：CHEN-V_Setup.exe /S:"D:\CHEN-V"
        string silent = Engine.ParseSilentArg(args);
        if (silent != null)
        {
            try
            {
                string note = Engine.Install(silent, null);
                Engine.WriteLog("silent ok -> " + silent + (string.IsNullOrEmpty(note) ? "" : (" | " + note)));
                Environment.Exit(0);
            }
            catch (Exception ex)
            {
                Engine.WriteLog("silent failed: " + ex);
                Environment.Exit(1);
            }
            return;
        }

        try
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new SetupApp());
        }
        catch (Exception ex)
        {
            MessageBox.Show("启动失败：" + ex.Message, APP_NAME,
                            MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}

/// <summary>安装引擎：解压、写注册表、建快捷方式、生成卸载器。无 UI 依赖，可静默调用。</summary>
static class Engine
{
    public static string DefaultDir()
    {
        string pf = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
        if (string.IsNullOrEmpty(pf)) pf = @"C:\Program Files";
        return Path.Combine(pf, SetupApp.APP_NAME);
    }

    public static string ParseSilentArg(string[] args)
    {
        if (args == null) return null;
        foreach (string a in args)
        {
            if (a.StartsWith("/S:", StringComparison.OrdinalIgnoreCase))
                return a.Substring(3).Trim('"');
            if (a.Equals("/S", StringComparison.OrdinalIgnoreCase))
                return DefaultDir();
        }
        return null;
    }

    public static void WriteLog(string text)
    {
        try
        {
            File.AppendAllText(Path.Combine(Path.GetTempPath(), "chenv_install_error.log"),
                DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "  " + text + "\r\n",
                Encoding.UTF8);
        }
        catch { }
    }

    public static Image LoadIcon()
    {
        try
        {
            var asm = Assembly.GetExecutingAssembly();
            foreach (string name in asm.GetManifestResourceNames())
                if (name.EndsWith("icon.png", StringComparison.OrdinalIgnoreCase))
                    using (var s = asm.GetManifestResourceStream(name))
                        return Image.FromStream(s);
        }
        catch { }
        try
        {
            Icon ic = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            if (ic != null) return ic.ToBitmap();
        }
        catch { }
        return null;
    }

    public static double[][] BuildParticles(int n)
    {
        var rnd = new Random(20261031);
        var a = new double[n][];
        for (int i = 0; i < n; i++)
            a[i] = new double[] {
                rnd.NextDouble() * Math.PI * 2,
                (0.7 + rnd.NextDouble() * 0.8) * (i % 2 == 0 ? 1 : -1),
                0.30 + rnd.NextDouble() * 0.42,
                0.22 + rnd.NextDouble() * 0.26,
                1.1 + rnd.NextDouble() * 1.8,
                0.45 + rnd.NextDouble() * 0.5
            };
        return a;
    }

    public static GraphicsPath Round(int x, int y, int w, int h, int r)
    {
        var p = new GraphicsPath();
        int d = r * 2;
        if (w <= d || h <= d) { p.AddRectangle(new Rectangle(x, y, w, h)); return p; }
        p.AddArc(x, y, d, d, 180, 90);
        p.AddArc(x + w - d, y, d, d, 270, 90);
        p.AddArc(x + w - d, y + h - d, d, d, 0, 90);
        p.AddArc(x, y + h - d, d, d, 90, 90);
        p.CloseFigure();
        return p;
    }

    public static Color FromHue(double hue)
    {
        double hh = (hue % 360.0) / 60.0;
        int i = (int)hh % 6;
        double f = hh - Math.Floor(hh), q = 1 - f, t = f, r, gg, b;
        switch (i)
        {
            case 0: r = 1; gg = t; b = 0; break;
            case 1: r = q; gg = 1; b = 0; break;
            case 2: r = 0; gg = 1; b = t; break;
            case 3: r = 0; gg = q; b = 1; break;
            case 4: r = t; gg = 0; b = 1; break;
            default: r = 1; gg = 0; b = q; break;
        }
        return Color.FromArgb((int)(r * 255), (int)(gg * 255), (int)(b * 255));
    }

    static string LP(string p)
    {
        if (string.IsNullOrEmpty(p)) return p;
        if (p.StartsWith(@"\\?\")) return p;
        if (p.Length < 200) return p;
        if (p.StartsWith(@"\\")) return @"\\?\UNC\" + p.Substring(2);
        return @"\\?\" + p;
    }

    /// <summary>把 exe 内嵌的 ZIP 直接解压到 target，返回提醒文字（可为空）。</summary>
    public static string Install(string target, Action<string, double> report)
    {
        if (string.IsNullOrEmpty(target)) throw new Exception("安装目录为空。");

        string self = Application.ExecutablePath;
        long total = new FileInfo(self).Length;

        long zipOffset;
        using (var fs = new FileStream(self, FileMode.Open, FileAccess.Read, FileShare.Read))
        {
            if (fs.Length < 32) throw new Exception("安装包已损坏（文件过小）。");
            fs.Seek(-8, SeekOrigin.End);
            var b8 = new byte[8];
            fs.Read(b8, 0, 8);
            zipOffset = BitConverter.ToInt64(b8, 0);
            if (zipOffset <= 0 || zipOffset >= fs.Length - 8)
                throw new Exception("安装包已损坏（找不到数据区）。");
        }

        Directory.CreateDirectory(LP(target));
        if (report != null) report("正在释放文件…", 0.01);

        long done = 0, lastPaint = 0;
        using (var fs = new FileStream(self, FileMode.Open, FileAccess.Read, FileShare.Read))
        using (var sub = new SubStream(fs, zipOffset, total - 8 - zipOffset))
        using (var zip = new ZipArchive(sub, ZipArchiveMode.Read))
        {
            long zipLen = sub.Length;
            var buf = new byte[1 << 16];

            foreach (var entry in zip.Entries)
            {
                string name = entry.FullName.Replace('\\', '/');
                if (name.Length == 0) continue;

                int slash = name.IndexOf('/');
                string rel = slash >= 0 ? name.Substring(slash + 1) : name;
                if (rel.Length == 0) continue;
                if (rel.StartsWith(SetupApp.SKIP_DIR)) continue;              // 安装器自身
                if (rel.StartsWith("CHEN-V_Setup.exe")) continue;             // 旧引导器
                if (rel.StartsWith("卸载CHEN-V.bat")) continue;               // 重新生成

                rel = rel.Replace('/', Path.DirectorySeparatorChar);
                string dest = Path.Combine(target, rel);

                if (entry.Name.Length == 0)
                {
                    Directory.CreateDirectory(LP(dest));
                    continue;
                }
                Directory.CreateDirectory(LP(Path.GetDirectoryName(dest)));

                using (var input = entry.Open())
                using (var output = new FileStream(LP(dest), FileMode.Create, FileAccess.Write,
                                                   FileShare.None, 1 << 16))
                {
                    int n;
                    while ((n = input.Read(buf, 0, buf.Length)) > 0)
                    {
                        output.Write(buf, 0, n);
                        done += n;
                        if (report != null && done - lastPaint > (3 << 20))
                        {
                            lastPaint = done;
                            string nm = entry.Name.Length > 30
                                      ? entry.Name.Substring(0, 30) + "…" : entry.Name;
                            report("正在释放 " + nm, Math.Min(0.97, (double)done / zipLen));
                        }
                    }
                }
            }
        }

        if (report != null) report("正在创建快捷方式…", 0.98);
        foreach (string d in new string[] { "work", "logs" })
            Directory.CreateDirectory(LP(Path.Combine(target, d)));

        string note = "";
        try { WriteRegistry(target); }
        catch (Exception ex) { note = "注册表写入失败（" + ex.Message + "）"; }
        try { WriteShortcut(target); }
        catch { note += (note.Length > 0 ? "；" : "") + "快捷方式创建失败"; }
        try { WriteUninstaller(target); }
        catch { note += (note.Length > 0 ? "；" : "") + "卸载脚本创建失败"; }

        if (report != null) report("完成", 1.0);
        return note;
    }

    static void WriteRegistry(string target)
    {
        string key = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\" + SetupApp.APP_NAME;
        using (var k = Microsoft.Win32.Registry.LocalMachine.CreateSubKey(key))
        {
            k.SetValue("DisplayName", SetupApp.APP_NAME);
            k.SetValue("DisplayVersion", SetupApp.APP_VER);
            k.SetValue("Publisher", SetupApp.APP_PUBLISHER);
            k.SetValue("DisplayIcon", Path.Combine(target, "app", "icon.ico"));
            k.SetValue("UninstallString", "\"" + UninstallBatPath() + "\"");
            k.SetValue("InstallLocation", target);
            k.SetValue("URLInfoAbout", SetupApp.APP_URL);
            k.SetValue("NoModify", 1, Microsoft.Win32.RegistryValueKind.DWord);
            k.SetValue("NoRepair", 1, Microsoft.Win32.RegistryValueKind.DWord);
        }
        using (var k = Microsoft.Win32.Registry.LocalMachine.CreateSubKey(@"Software\" + SetupApp.APP_NAME))
        {
            k.SetValue("InstallDir", target);
            k.SetValue("Version", SetupApp.APP_VER);
        }
    }

    static void WriteShortcut(string target)
    {
        string vbs = Path.Combine(Path.GetTempPath(), "_chenv_lnk.vbs");
        var sb = new StringBuilder();
        sb.AppendLine("Set sh = CreateObject(\"WScript.Shell\")");
        sb.AppendLine("Set lnk = sh.CreateShortcut(sh.SpecialFolders(\"Desktop\") & \"\\" + SetupApp.APP_NAME + ".lnk\")");
        sb.AppendLine("lnk.TargetPath = \"" + Path.Combine(target, SetupApp.APP_EXE) + "\"");
        sb.AppendLine("lnk.WorkingDirectory = \"" + target + "\"");
        sb.AppendLine("lnk.IconLocation = \"" + Path.Combine(target, "app", "icon.ico") + "\"");
        sb.AppendLine("lnk.Save");
        File.WriteAllText(vbs, sb.ToString(), Encoding.Default);

        var psi = new ProcessStartInfo("cscript", "//nologo \"" + vbs + "\"");
        psi.CreateNoWindow = true;
        psi.UseShellExecute = false;
        using (var p = Process.Start(psi))
        {
            if (!p.WaitForExit(15000)) { try { p.Kill(); } catch { } }
        }
        try { File.Delete(vbs); } catch { }
    }

    static string UninstallBatPath()
    {
        string baseDir = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        if (string.IsNullOrEmpty(baseDir)) baseDir = Path.GetTempPath();
        return Path.Combine(Path.Combine(baseDir, SetupApp.APP_NAME), "uninstall.bat");
    }

    static void WriteUninstaller(string target)
    {
        string bat = UninstallBatPath();
        Directory.CreateDirectory(Path.GetDirectoryName(bat));

        var sb = new StringBuilder();
        sb.AppendLine("@echo off");
        sb.AppendLine("chcp 65001 >nul");
        sb.AppendLine("echo 正在卸载 " + SetupApp.APP_NAME + " ...");
        sb.AppendLine("timeout /t 1 /nobreak >nul");
        sb.AppendLine("rmdir /s /q \"" + target + "\" 2>nul");
        sb.AppendLine("reg delete \"HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\"
                      + SetupApp.APP_NAME + "\" /f >nul 2>nul");
        sb.AppendLine("reg delete \"HKLM\\Software\\" + SetupApp.APP_NAME + "\" /f >nul 2>nul");
        sb.AppendLine("del /q \"%USERPROFILE%\\Desktop\\" + SetupApp.APP_NAME + ".lnk\" >nul 2>nul");
        sb.AppendLine("del /q \"%~f0\" >nul 2>nul");
        sb.AppendLine("echo " + SetupApp.APP_NAME + " 已卸载。");
        sb.AppendLine("timeout /t 2 /nobreak >nul");
        File.WriteAllText(bat, sb.ToString(), new UTF8Encoding(true));

        var sb2 = new StringBuilder();
        sb2.AppendLine("@echo off");
        sb2.AppendLine("chcp 65001 >nul");
        sb2.AppendLine("copy /y \"" + bat + "\" \"%TEMP%\\_chenv_uninst.bat\" >nul");
        sb2.AppendLine("start \"\" \"%TEMP%\\_chenv_uninst.bat\"");
        sb2.AppendLine("exit");
        File.WriteAllText(Path.Combine(target, "卸载" + SetupApp.APP_NAME + ".bat"),
                          sb2.ToString(), new UTF8Encoding(true));
    }

    class SubStream : Stream
    {
        readonly Stream _base;
        readonly long _start, _len;
        long _pos;
        public SubStream(Stream b, long start, long len) { _base = b; _start = start; _len = len; }
        public override bool CanRead { get { return true; } }
        public override bool CanSeek { get { return true; } }
        public override bool CanWrite { get { return false; } }
        public override long Length { get { return _len; } }
        public override long Position { get { return _pos; } set { _pos = value; } }
        public override int Read(byte[] buffer, int offset, int count)
        {
            long left = _len - _pos;
            if (left <= 0) return 0;
            if (count > left) count = (int)left;
            _base.Seek(_start + _pos, SeekOrigin.Begin);
            int n = _base.Read(buffer, offset, count);
            _pos += n;
            return n;
        }
        public override long Seek(long offset, SeekOrigin origin)
        {
            long np = origin == SeekOrigin.Begin ? offset
                    : origin == SeekOrigin.Current ? _pos + offset : _len + offset;
            _pos = Math.Max(0, Math.Min(_len, np));
            return _pos;
        }
        public override void Flush() { }
        public override void SetLength(long v) { throw new NotSupportedException(); }
        public override void Write(byte[] b, int o, int c) { throw new NotSupportedException(); }
    }
}
