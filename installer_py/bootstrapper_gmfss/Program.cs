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
/// CHEN-V GMFSS 补充包安装器（单文件、直接合并进已安装目录）。
///
/// 和主安装器的区别：
///   * 不创建目录、不写注册表、不建快捷方式、不动用户设置 —— 只是往一个
///     已经装好的 CHEN-V 目录里补文件，所以必须先校验目标目录对不对；
///   * 目标目录由用户选，默认从注册表 HKLM\Software\CHEN-V\InstallDir 读；
///   * 装之前检查 CHEN-V 有没有在运行，运行中覆盖 DLL 会失败。
///
/// 也支持静默安装：CHEN-V_GMFSS_Setup.exe /S:"D:\CHEN-V"
/// </summary>
class GmfssSetupApp : Form
{
    public const string APP_NAME = "CHEN-V";
    public const string APP_VER = "1.03";
    public const string APP_PUBLISHER = "辰师";
    public const string APP_URL = "https://github.com/CHENYE-SHI/CHEN-V";
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

    public GmfssSetupApp()
    {
        Text = APP_NAME + " GMFSS 补充包";
        ClientSize = new Size(660, 470);
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
        _rcCheck = new Rectangle(60, h - 58, 240, 24);
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

        if (_icon != null) g.DrawImage(_icon, new Rectangle(w / 2 - 32, 30, 64, 64));

        if (_step == Step.Welcome) DrawWelcome(g, w, h);
        else if (_step == Step.Installing) DrawInstalling(g, w, h);
        else DrawDone(g, w, h);
    }

    void DrawWelcome(Graphics g, int w, int h)
    {
        Txt(g, "GMFSS 补充包", 20f, FontStyle.Bold, Color.FromArgb(240, 245, 250),
             new RectangleF(0, 106, w, 38), StringAlignment.Center);
        Txt(g, "版本 V" + APP_VER + "  ·  " + APP_PUBLISHER, 10f, FontStyle.Regular,
             Color.FromArgb(150, 165, 182), new RectangleF(0, 144, w, 24), StringAlignment.Center);

        Txt(g, "CHEN-V 安装位置", 9.5f, FontStyle.Regular, Color.FromArgb(140, 155, 175),
             new RectangleF(60, 196, w - 120, 22), StringAlignment.Near);

        using (var path = Engine.Round(60, 220, w - 120, 38, 8))
        using (var fill = new SolidBrush(Color.FromArgb(26, 255, 255, 255)))
        using (var pen = new Pen(Color.FromArgb(44, 255, 255, 255)))
        {
            g.FillPath(fill, path);
            g.DrawPath(pen, path);
        }
        Txt(g, _target, 10f, FontStyle.Regular, Color.FromArgb(222, 232, 242),
             new RectangleF(74, 228, w - 148, 24), StringAlignment.Near);

        Txt(g, "选中已经装好 CHEN-V 的那个文件夹，文件会直接合并进去",
             9f, FontStyle.Regular, Color.FromArgb(130, 145, 165),
             new RectangleF(60, 264, w - 120, 22), StringAlignment.Near);

        Btn(g, _rcChange, "选择目录", _hot == 0, false);
        Btn(g, _rcPrimary, "开始安装", _hot == 1, true);

        Txt(g, "补充 PyTorch 运行时与 GMFSS 模型（约 4.2 GB），不写注册表、不动设置",
             8.5f, FontStyle.Regular, Color.FromArgb(104, 116, 134),
             new RectangleF(0, h - 32, w, 20), StringAlignment.Center);
    }

    void DrawInstalling(Graphics g, int w, int h)
    {
        Txt(g, _failed ? "安装失败" : "正在合并…", 19f, FontStyle.Bold,
             _failed ? Color.FromArgb(255, 138, 128) : Color.FromArgb(240, 245, 250),
             new RectangleF(0, 110, w, 38), StringAlignment.Center);
        Txt(g, "版本 V" + APP_VER + "  ·  " + APP_PUBLISHER, 9.5f, FontStyle.Regular,
             Color.FromArgb(140, 155, 175), new RectangleF(0, 148, w, 22), StringAlignment.Center);

        if (_failed)
        {
            Txt(g, _errMsg ?? "未知错误", 10f, FontStyle.Regular,
                 Color.FromArgb(220, 190, 190), new RectangleF(50, 210, w - 100, 110),
                 StringAlignment.Center);
            Btn(g, _rcPrimary, "关闭", _hot == 1, true);
            return;
        }

        Txt(g, _status, 10f, FontStyle.Regular,
             Color.FromArgb(210, 220, 230), new RectangleF(50, 238, w - 100, 24), StringAlignment.Center);

        int bx = 80, by = 278, bw = w - 160, bh = 12;
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
             new RectangleF(0, h - 52, w, 20), StringAlignment.Center);
    }

    void DrawDone(Graphics g, int w, int h)
    {
        Txt(g, "补充包安装完成", 20f, FontStyle.Bold, Color.FromArgb(240, 245, 250),
             new RectangleF(0, 108, w, 38), StringAlignment.Center);
        Txt(g, "版本 V" + APP_VER + "  ·  " + APP_PUBLISHER, 10f, FontStyle.Regular,
             Color.FromArgb(150, 165, 182), new RectangleF(0, 146, w, 24), StringAlignment.Center);

        Txt(g, "GMFSS 已合并到：", 9.5f, FontStyle.Regular, Color.FromArgb(150, 165, 182),
             new RectangleF(60, 198, w - 120, 22), StringAlignment.Near);
        Txt(g, _target, 10f, FontStyle.Regular, Color.FromArgb(226, 234, 244),
             new RectangleF(60, 222, w - 120, 24), StringAlignment.Near);
        if (!string.IsNullOrEmpty(_doneText))
            Txt(g, _doneText, 9f, FontStyle.Regular, Color.FromArgb(150, 200, 170),
                 new RectangleF(60, 250, w - 120, 22), StringAlignment.Near);

        Txt(g, "重启 CHEN-V 后，补帧模型里就会出现 GMFSS 选项",
             9f, FontStyle.Regular, Color.FromArgb(130, 145, 165),
             new RectangleF(60, 282, w - 120, 22), StringAlignment.Near);

        DrawCheck(g, _rcCheck, _runAfter, _hot == 2);
        Txt(g, "立即启动 " + APP_NAME, 9.5f, FontStyle.Regular, Color.FromArgb(214, 223, 232),
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
        else if (_failed && _rcPrimary.Contains(e.Location)) hot = 1;

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
        else if (_failed && _rcPrimary.Contains(e.Location))
        {
            _closingAllowed = 1;
            Close();
        }
    }

    int _closingAllowed = 0;
    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        if (_step == Step.Installing && _closingAllowed == 0 && !_failed)
        {
            if (MessageBox.Show(this, "正在写入文件，确定要退出吗？\n中途退出会留下不完整的文件。", APP_NAME,
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
            dlg.Description = "选择已安装 CHEN-V 的文件夹（里面应该有 CHEN-V.exe）";
            dlg.SelectedPath = Directory.Exists(_target) ? _target : Engine.DefaultDir();
            dlg.ShowNewFolderButton = false;
            if (dlg.ShowDialog(this) != DialogResult.OK) return;

            string picked = dlg.SelectedPath;
            // 用户很容易顺手上到上一级，这里自动往下探一层
            if (File.Exists(Path.Combine(picked, APP_NAME, APP_EXE)))
                picked = Path.Combine(picked, APP_NAME);

            _target = picked;
            Invalidate();
        }
    }

    void StartInstall()
    {
        if (string.IsNullOrEmpty(_target)) return;

        string err = Engine.ValidateTarget(_target);
        if (err != null)
        {
            MessageBox.Show(this, err, "目录不对", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }
        if (Engine.IsAppRunning())
        {
            MessageBox.Show(this, "CHEN-V 正在运行，请先关掉再安装。\n"
                                + "运行中的程序会锁住 Python 运行时，文件写不进去。",
                            APP_NAME, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

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
        string silent = Engine.ParseSilentArg(args);
        if (silent != null)
        {
            try
            {
                Engine.Install(silent, null);
                Engine.WriteLog("gmfss silent ok -> " + silent);
                Environment.Exit(0);
            }
            catch (Exception ex)
            {
                Engine.WriteLog("gmfss silent failed: " + ex);
                Environment.Exit(1);
            }
            return;
        }

        try
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new GmfssSetupApp());
        }
        catch (Exception ex)
        {
            MessageBox.Show("启动失败：" + ex.Message, APP_NAME,
                            MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}

/// <summary>补充包引擎：校验目标、直接解压覆盖。不碰注册表、快捷方式、用户设置。</summary>
static class Engine
{
    /// <summary>优先从注册表拿主程序装在哪，拿不到再退回默认路径。</summary>
    public static string DefaultDir()
    {
        try
        {
            using (var k = Microsoft.Win32.Registry.LocalMachine.OpenSubKey(@"Software\CHEN-V"))
            {
                if (k != null)
                {
                    string v = k.GetValue("InstallDir") as string;
                    if (!string.IsNullOrEmpty(v) && Directory.Exists(v)) return v;
                }
            }
        }
        catch { }

        string pf = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
        if (string.IsNullOrEmpty(pf)) pf = @"C:\Program Files";
        return Path.Combine(pf, GmfssSetupApp.APP_NAME);
    }

    /// <summary>返回 null 表示目录可用，否则返回给用户看的原因。</summary>
    public static string ValidateTarget(string t)
    {
        if (string.IsNullOrEmpty(t)) return "请先选择 CHEN-V 的安装目录。";
        if (!Directory.Exists(t))
            return "找不到这个文件夹：\n" + t;
        if (!File.Exists(Path.Combine(t, GmfssSetupApp.APP_EXE)))
            return "这个文件夹里没有 " + GmfssSetupApp.APP_EXE + "，不像是 CHEN-V 的安装目录。\n\n"
                 + "请选择你安装 CHEN-V 时用的那个文件夹"
                 + "（默认是 C:\\Program Files\\CHEN-V）。";
        if (!File.Exists(Path.Combine(t, "app", "gui_main.py")))
            return "程序文件不完整：缺少 app\\gui_main.py。\n\n"
                 + "请先重新安装一次 CHEN-V 主程序，再装这个补充包。";
        if (!Directory.Exists(Path.Combine(t, "vrt", "python")))
            return "运行时目录不完整：缺少 vrt\\python。\n\n请先重新安装 CHEN-V 主程序。";
        return null;
    }

    public static bool IsAppRunning()
    {
        try { return Process.GetProcessesByName(GmfssSetupApp.APP_NAME).Length > 0; }
        catch { return false; }
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

    static string ShortName(string name)
    {
        return name.Length > 28 ? name.Substring(0, 28) + "…" : name;
    }

    /// <summary>把 exe 内嵌的 ZIP 直接解压合并到 target，返回给用户的结果说明。</summary>
    public static string Install(string target, Action<string, double> report)
    {
        if (string.IsNullOrEmpty(target)) throw new Exception("请先选择 CHEN-V 的安装目录。");

        string bad = ValidateTarget(target);
        if (bad != null) throw new Exception(bad);
        if (IsAppRunning())
            throw new Exception("CHEN-V 正在运行，请先关掉再安装。");

        string self = Application.ExecutablePath;
        long total = new FileInfo(self).Length;

        long zipOffset;
        using (var fs = new FileStream(self, FileMode.Open, FileAccess.Read, FileShare.Read))
        {
            if (fs.Length < 32) throw new Exception("补充包已损坏（文件过小）。");
            fs.Seek(-8, SeekOrigin.End);
            var b8 = new byte[8];
            fs.Read(b8, 0, 8);
            zipOffset = BitConverter.ToInt64(b8, 0);
            if (zipOffset <= 0 || zipOffset >= fs.Length - 8)
                throw new Exception("补充包已损坏（找不到数据区）。");
        }

        if (report != null) report("正在合并文件…", 0.01);

        long done = 0, lastPaint = 0;
        int files = 0;

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

                rel = rel.Replace('/', Path.DirectorySeparatorChar);
                string dest = Path.Combine(target, rel);

                if (entry.Name.Length == 0)
                {
                    Directory.CreateDirectory(LP(dest));
                    continue;
                }
                Directory.CreateDirectory(LP(Path.GetDirectoryName(dest)));

                try
                {
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
                                report("正在合并 " + ShortName(entry.Name),
                                       Math.Min(0.97, (double)done / Math.Max(zipLen, 1)));
                            }
                        }
                    }
                    files++;
                }
                catch (IOException ex)
                {
                    throw new Exception("写入失败：" + rel + "\n" + ex.Message
                        + "\n\n如果 CHEN-V 还开着，请关掉后重新运行本安装器。");
                }
                catch (UnauthorizedAccessException)
                {
                    throw new Exception("没有权限写入：\n" + dest
                        + "\n\n请右键本程序，选择「以管理员身份运行」。");
                }
            }
        }

        if (report != null) report("完成", 1.0);
        return "共写入 " + files + " 个文件";
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
