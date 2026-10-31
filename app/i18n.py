# -*- coding: utf-8 -*-
"""CHEN-V 多语言支持：简体中文 -> 繁体中文 / English / 日本語。

以简体中文原文作为 key，切换语言时用 tr() 反查译文。
"""

LANG_NAMES = {
    "zh-CN": "简体中文",
    "zh-TW": "繁體中文",
    "en": "English",
    "ja": "日本語",
}

# 当前语言
_CURRENT = "zh-CN"


def set_lang(code):
    global _CURRENT
    if code in LANG_NAMES:
        _CURRENT = code


def lang():
    return _CURRENT


# 翻译表：简体中文 -> {zh-TW, en, ja}
_T = {
    "简体中文": {"zh-TW": "繁體中文", "en": "Simplified Chinese", "ja": "簡体中国語"},
    "繁體中文": {"zh-TW": "繁體中文", "en": "Traditional Chinese", "ja": "繁体中国語"},
    "English": {"zh-TW": "English", "en": "English", "ja": "English"},
    "日本語": {"zh-TW": "日本語", "en": "Japanese", "ja": "日本語"},

    # 导航 / 页面
    "超分补帧": {"zh-TW": "超分補幀", "en": "Super-res + Interp", "ja": "超解像と補間"},
    "进度": {"zh-TW": "進度", "en": "Progress", "ja": "進捗"},
    "官网更新": {"zh-TW": "官網更新", "en": "Updates", "ja": "アップデート"},
    "设置": {"zh-TW": "設置", "en": "Settings", "ja": "設定"},
    "关于": {"zh-TW": "關於", "en": "About", "ja": "情報"},
    "特别鸣谢": {"zh-TW": "特別鳴謝", "en": "Credits", "ja": "謝辞"},
    "界面美化": {"zh-TW": "介面美化", "en": "Appearance", "ja": "外観"},

    # 任务页
    "创建增强任务": {"zh-TW": "創建增強任務", "en": "Create Enhancement Task", "ja": "拡張タスクの作成"},
    "左边调参数，右边拉素材；设置后点开始处理。": {
        "zh-TW": "左邊調參數，右邊拉素材；設置後點開始處理。",
        "en": "Tune parameters on the left, add media on the right, then start.",
        "ja": "左でパラメータ、右で素材を追加して開始。"},
    "图片超分": {"zh-TW": "圖片超分", "en": "Image Upscale", "ja": "画像超解像"},
    "视频超分": {"zh-TW": "視頻超分", "en": "Video Upscale", "ja": "動画超解像"},
    "视频补帧": {"zh-TW": "視頻補幀", "en": "Frame Interp", "ja": "フレーム補間"},
    "超分并补帧": {"zh-TW": "超分並補幀", "en": "Upscale + Interp", "ja": "超解像＋補間"},
    "输入": {"zh-TW": "輸入", "en": "Input", "ja": "入力"},
    "尚未选择": {"zh-TW": "尚未選擇", "en": "Not selected", "ja": "未選択"},
    "输出目录": {"zh-TW": "輸出目錄", "en": "Output folder", "ja": "出力先"},
    "浏览": {"zh-TW": "瀏覽", "en": "Browse", "ja": "参照"},
    "自动文件名": {"zh-TW": "自動文件名", "en": "Auto filename", "ja": "自動ファイル名"},
    "处理设置": {"zh-TW": "處理設置", "en": "Processing Settings", "ja": "処理設定"},
    "按倍率": {"zh-TW": "按倍率", "en": "By multiplier", "ja": "倍率指定"},
    "按输出帧率": {"zh-TW": "按輸出幀率", "en": "By output FPS", "ja": "出力FPS指定"},
    "编码器": {"zh-TW": "編碼器", "en": "Encoder", "ja": "エンコーダー"},
    "CRF / Mbps": {"zh-TW": "CRF / Mbps", "en": "CRF / Mbps", "ja": "CRF / Mbps"},
    "两段式：先补帧再超分": {"zh-TW": "兩段式：先補幀再超分", "en": "Two-pass: interp then upscale", "ja": "二段階：補間→超解像"},
    "保留补帧中间片": {"zh-TW": "保留補幀中間片", "en": "Keep intermediate clip", "ja": "中間動画を保持"},
    "帧流法": {"zh-TW": "幀流法", "en": "Frame dedup", "ja": "フレーム間引き"},
    "切镜保护": {"zh-TW": "切鏡保護", "en": "Scene protection", "ja": "シーン保護"},
    "硬件解码": {"zh-TW": "硬件解碼", "en": "Hardware decode", "ja": "ハードウェアデコード"},
    "日志增速": {"zh-TW": "日誌增速", "en": "Fast logging", "ja": "高速ログ"},
    "阈值": {"zh-TW": "閾值", "en": "Threshold", "ja": "閾値"},
    "预设": {"zh-TW": "預設", "en": "Preset", "ja": "プリセット"},
    "保存预设": {"zh-TW": "保存預設", "en": "Save preset", "ja": "プリセット保存"},
    "删除": {"zh-TW": "刪除", "en": "Delete", "ja": "削除"},

    # 素材队列
    "拖入图片、视频或文件夹": {"zh-TW": "拖入圖片、視頻或文件夾", "en": "Drag images, videos or folders", "ja": "画像・動画・フォルダをドロップ"},
    "单个素材直接处理，多个素材自动加入批量队列": {
        "zh-TW": "單個素材直接處理，多個素材自動加入批量隊列",
        "en": "Single file processes directly; multiple files queue up automatically",
        "ja": "単一素材は直接処理、複数は自動でキューに追加"},
    "选择文件": {"zh-TW": "選擇文件", "en": "Add files", "ja": "ファイルを選択"},
    "选择文件夹批量": {"zh-TW": "選擇文件夾批量", "en": "Add folder", "ja": "フォルダを選択"},
    "素材队列": {"zh-TW": "素材隊列", "en": "Media queue", "ja": "素材キュー"},
    "等待加入素材": {"zh-TW": "等待加入素材", "en": "Waiting for media", "ja": "素材待ち"},
    "提示：右键可移除": {"zh-TW": "提示：右鍵可移除", "en": "Right-click to remove", "ja": "右クリックで削除"},
    "选择或拖入素材后，任务会在这里排队": {
        "zh-TW": "選擇或拖入素材後，任務會在這裡排隊",
        "en": "Tasks queue up here after adding media",
        "ja": "素材を追加するとタスクがここに並ぶ"},
    "清空队列": {"zh-TW": "清空隊列", "en": "Clear queue", "ja": "キューを空にする"},
    "移除选中": {"zh-TW": "移除選中", "en": "Remove selected", "ja": "選択を削除"},
    "△  开始队列": {"zh-TW": "△  開始隊列", "en": "△  Start Queue", "ja": "△  開始"},

    # 进度页
    "当前任务的处理进度与日志。": {"zh-TW": "當前任務的處理進度與日誌。", "en": "Current task progress and logs.", "ja": "現在のタスク進捗とログ。"},
    "尚无任务": {"zh-TW": "尚無任務", "en": "No task", "ja": "タスクなし"},
    "停止": {"zh-TW": "停止", "en": "Stop", "ja": "停止"},

    # 更新页
    "当前为本地构建；没有配置在线更新源。": {"zh-TW": "當前為本地構建；沒有配置在線更新源。", "en": "Local build; no online update source configured.", "ja": "ローカルビルド；オンライン更新元は未設定。"},
    "更新方式：替换程序目录中的 app、models、runtime、ffmpeg 即可。": {
        "zh-TW": "更新方式：替換程序目錄中的 app、models、runtime、ffmpeg 即可。",
        "en": "Update by replacing app, models, runtime, ffmpeg in the program folder.",
        "ja": "更新はプログラムフォルダの app/models/runtime/ffmpeg を置換。"},
    "打开程序目录": {"zh-TW": "打開程序目錄", "en": "Open program folder", "ja": "プログラムフォルダを開く"},
    "检查更新": {"zh-TW": "檢查更新", "en": "Check updates", "ja": "更新を確認"},

    # 设置页
    "工作目录、默认输出、运行环境与工具路径。": {
        "zh-TW": "工作目錄、默認輸出、運行環境與工具路徑。",
        "en": "Working folder, default output, runtime and tool paths.",
        "ja": "作業フォルダ、既定出力、ランタイムとツールパス。"},
    "默认输出目录": {"zh-TW": "默認輸出目錄", "en": "Default output folder", "ja": "既定の出力先"},
    "界面风格": {"zh-TW": "界面風格", "en": "Theme", "ja": "テーマ"},
    "选择配色主题，立即应用到整个界面": {"zh-TW": "選擇配色主題，立即應用到整個界面", "en": "Pick a color theme, applied instantly", "ja": "配色テーマを選択、即反映"},
    "浅色": {"zh-TW": "淺色", "en": "Light", "ja": "ライト"},
    "深色": {"zh-TW": "深色", "en": "Dark", "ja": "ダーク"},
    "紫色": {"zh-TW": "紫色", "en": "Purple", "ja": "パープル"},
    "界面颜色": {"zh-TW": "界面顏色", "en": "Interface colors", "ja": "配色"},
    "自定义主题强调色与文字颜色": {"zh-TW": "自定義主題強調色與文字顏色", "en": "Custom accent and text colors", "ja": "アクセント色と文字色をカスタム"},
    "主题色（强调色）": {"zh-TW": "主題色（強調色）", "en": "Accent color", "ja": "アクセント色"},
    "选择颜色": {"zh-TW": "選擇顏色", "en": "Pick color", "ja": "色を選択"},
    "文字颜色": {"zh-TW": "文字顏色", "en": "Text color", "ja": "文字色"},
    "恢复默认": {"zh-TW": "恢復默認", "en": "Reset", "ja": "既定に戻す"},
    "界面背景": {"zh-TW": "界面背景", "en": "Background", "ja": "背景"},
    "选择一张图片作为全窗口背景（半透明透出）": {
        "zh-TW": "選擇一張圖片作為全窗口背景（半透明透出）",
        "en": "Pick an image as the full-window background",
        "ja": "全画面背景として画像を選択"},
    "选择背景图": {"zh-TW": "選擇背景圖", "en": "Pick background", "ja": "背景画像を選択"},
    "选择壁纸目录": {"zh-TW": "選擇壁紙目錄", "en": "Pick wallpaper folder", "ja": "壁紙フォルダを選択"},
    "清除背景": {"zh-TW": "清除背景", "en": "Clear background", "ja": "背景をクリア"},
    "蒙版暗度": {"zh-TW": "蒙版暗度", "en": "Mask opacity", "ja": "マスク濃度"},
    "界面通透度": {"zh-TW": "介面通透度", "en": "Glass transparency", "ja": "ガラス透明度"},
    "自定义背景图与界面通透度，打造通透的玻璃质感。": {
        "zh-TW": "自訂背景圖與介面通透度，打造通透的玻璃質感。",
        "en": "Custom background and glass transparency for a translucent look.",
        "ja": "背景画像とガラス透明度で、透明感のある質感に。"},
    "数值越大，面板越透明，背景图透出越明显": {
        "zh-TW": "數值越大，面板越透明，背景圖透出越明顯",
        "en": "Higher value makes panels more transparent, showing the background more",
        "ja": "値が大きいほどパネルが透明になり、背景が透ける"},
    "暗度越低背景越亮，越高背景越暗；配合通透度调整": {
        "zh-TW": "暗度越低背景越亮，越高背景越暗；配合通透度調整",
        "en": "Lower opacity brightens, higher darkens the backdrop; tune with transparency",
        "ja": "暗度が低いほど背景が明るく、高いほど暗く；透明度と併用"},
    "● 已设置背景图": {"zh-TW": "● 已設定背景圖", "en": "● Background set", "ja": "● 背景画像設定済み"},
    "● 未设置背景图": {"zh-TW": "● 未設定背景圖", "en": "● No background", "ja": "● 背景画像なし"},
    "界面字体": {"zh-TW": "界面字體", "en": "Interface font", "ja": "フォント"},
    "可选择系统已安装字体": {"zh-TW": "可選擇系統已安裝字體", "en": "Choose an installed font", "ja": "インストール済みフォントを選択"},
    "运行环境": {"zh-TW": "運行環境", "en": "Runtime", "ja": "ランタイム"},
    "处理工具与组件状态": {"zh-TW": "處理工具與組件狀態", "en": "Tool and component status", "ja": "ツールとコンポーネントの状態"},
    "检查": {"zh-TW": "檢查", "en": "Check", "ja": "チェック"},
    "工具路径（高级）  ▾": {"zh-TW": "工具路徑（高級）  ▾", "en": "Tool paths (advanced)  ▾", "ja": "ツールパス（詳細）  ▾"},
    "工具路径（高级）": {"zh-TW": "工具路徑（高級）", "en": "Tool paths (advanced)", "ja": "ツールパス（詳細）"},
    "打开工作目录": {"zh-TW": "打開工作目錄", "en": "Open working folder", "ja": "作業フォルダを開く"},
    "清理缓存": {"zh-TW": "清理緩存", "en": "Clear cache", "ja": "キャッシュをクリア"},
    "保存设置": {"zh-TW": "保存設置", "en": "Save settings", "ja": "設定を保存"},
    "选择": {"zh-TW": "選擇", "en": "Choose", "ja": "選択"},
    "打开": {"zh-TW": "打開", "en": "Open", "ja": "開く"},

    # 硬件信息
    "硬件信息": {"zh-TW": "硬件信息", "en": "Hardware Info", "ja": "ハードウェア情報"},
    "系统": {"zh-TW": "系統", "en": "System", "ja": "システム"},
    "处理器": {"zh-TW": "處理器", "en": "CPU", "ja": "CPU"},
    "内存": {"zh-TW": "內存", "en": "Memory", "ja": "メモリ"},
    "主板": {"zh-TW": "主板", "en": "Motherboard", "ja": "マザーボード"},
    "操作系统": {"zh-TW": "操作系統", "en": "OS", "ja": "OS"},
    "显卡": {"zh-TW": "顯卡", "en": "GPU", "ja": "GPU"},
    "磁盘": {"zh-TW": "磁盤", "en": "Disk", "ja": "ディスク"},
    "提示": {"zh-TW": "提示", "en": "Note", "ja": "メモ"},
    "硬件配置": {"zh-TW": "硬體配置", "en": "Hardware", "ja": "ハードウェア構成"},
    "重新检测": {"zh-TW": "重新檢測", "en": "Re-detect", "ja": "再検出"},
    "本机硬件配置一览，可选中复制文字。": {
        "zh-TW": "本機硬體配置一覽，可選中複製文字。",
        "en": "Hardware overview; select text to copy.",
        "ja": "ハードウェア構成一覧。テキストを選択してコピーできます。"},
    "主题、配色、字体与背景，打造你的专属界面。": {
        "zh-TW": "主題、配色、字體與背景，打造你的專屬介面。",
        "en": "Theme, colors, fonts and background for your own look.",
        "ja": "テーマ・配色・フォント・背景で自分好みの外観に。"},

    # 关于/鸣谢
    "免责声明": {"zh-TW": "免責聲明", "en": "Disclaimer", "ja": "免責事項"},
    "第三方软件声明": {"zh-TW": "第三方軟體聲明", "en": "Third-party notices", "ja": "サードパーティ通知"},
    "完整许可文本随程序附带于 vrt/licenses/ 目录。"
    "上述组件的著作权均归各自作者所有，本程序仅在其许可范围内使用。": {
        "zh-TW": "完整授權文本隨程式附帶於 vrt/licenses/ 目錄。"
                 "上述元件的著作權均歸各自作者所有，本程式僅在其授權範圍內使用。",
        "en": "Full license texts ship with the program in the vrt/licenses/ folder. "
              "All components above remain the property of their respective authors; "
              "this program uses them only within the scope of their licenses.",
        "ja": "完全なライセンス全文は vrt/licenses/ に同梱されています。"
              "上記コンポーネントの著作権は各作者に帰属し、本プログラムはその許諾範囲内でのみ使用します。"},
    "本项目使用了以下开源项目与模型（含少量专有组件），谨向各位作者致以诚挚谢意。": {
        "zh-TW": "本項目使用了以下開源項目與模型（含少量專有組件），謹向各位作者致以誠摯謝意。",
        "en": "This project uses the following open-source projects and models "
              "(plus a few proprietary components). Our thanks to every author.",
        "ja": "本プロジェクトは以下のオープンソースプロジェクトとモデル"
              "（一部プロプライエタリを含む）を使用しています。作者の皆様に感謝します。"},
    "动漫超分模型": {"zh-TW": "動漫超分模型", "en": "Anime upscaling model", "ja": "アニメ超解像モデル"},
    "通用超分模型": {"zh-TW": "通用超分模型", "en": "General upscaling model", "ja": "汎用超解像モデル"},
    "视频补帧模型": {"zh-TW": "視頻補幀模型", "en": "Frame interpolation model", "ja": "フレーム補間モデル"},
    "音视频编解码": {"zh-TW": "音視頻編解碼", "en": "Audio / video codec", "ja": "音声・映像コーデック"},
    "推理框架": {"zh-TW": "推理框架", "en": "Inference framework", "ja": "推論フレームワーク"},
    "视频处理内核": {"zh-TW": "視頻處理內核", "en": "Video processing core", "ja": "映像処理コア"},
    "推理插件 · GPL-3.0": {"zh-TW": "推理插件 · GPL-3.0", "en": "Inference plugins · GPL-3.0",
                           "ja": "推論プラグイン · GPL-3.0"},
    "GPU 加速 · 专有许可": {"zh-TW": "GPU 加速 · 專有許可",
                            "en": "GPU acceleration · proprietary",
                            "ja": "GPU 加速 · プロプライエタリ"},
    "bilibili AI 实验室（bilibili/ailab）": {
        "zh-TW": "bilibili AI 實驗室（bilibili/ailab）",
        "en": "bilibili AI Lab (bilibili/ailab)",
        "ja": "bilibili AI ラボ（bilibili/ailab）"},
    "旷视研究院（megvii-research/RIFE）": {
        "zh-TW": "曠視研究院（megvii-research/RIFE）",
        "en": "Megvii Research (megvii-research/RIFE)",
        "ja": "Megvii Research（megvii-research/RIFE）"},
    "FFmpeg 团队": {"zh-TW": "FFmpeg 團隊", "en": "FFmpeg team", "ja": "FFmpeg チーム"},
    "界面框架": {"zh-TW": "界面框架", "en": "GUI framework", "ja": "UI フレームワーク"},
    "ONNX 推理运行时": {"zh-TW": "ONNX 推理運行時", "en": "ONNX inference runtime",
                        "ja": "ONNX 推論ランタイム"},

    # 运行环境检测项
    "视频解码与编码": {"zh-TW": "視頻解碼與編碼", "en": "Video decode / encode", "ja": "映像デコード・エンコード"},
    "动漫超分 · 降噪 / 保守": {"zh-TW": "動漫超分 · 降噪 / 保守",
                               "en": "Anime upscaling · denoise / conservative",
                               "ja": "アニメ超解像 · ノイズ除去 / 控えめ"},
    "通用超分 · 实拍修复": {"zh-TW": "通用超分 · 實拍修復",
                            "en": "General upscaling · live-action restore",
                            "ja": "汎用超解像 · 実写修復"},
    "视频补帧 · 插帧引擎": {"zh-TW": "視頻補幀 · 插幀引擎",
                            "en": "Frame interpolation engine", "ja": "フレーム補間エンジン"},
    "常驻补帧 / 超分进程": {"zh-TW": "常駐補幀 / 超分進程",
                            "en": "Resident process for interpolation / upscaling",
                            "ja": "常駐の補間・超解像プロセス"},
    "视频处理内核与推理插件": {"zh-TW": "視頻處理內核與推理插件",
                               "en": "Video core and inference plugins",
                               "ja": "映像コアと推論プラグイン"},
    "NVIDIA 显卡推理加速 · 快 2~3 倍": {
        "zh-TW": "NVIDIA 顯卡推理加速 · 快 2~3 倍",
        "en": "NVIDIA GPU acceleration · 2–3× faster",
        "ja": "NVIDIA GPU 高速化 · 2〜3 倍速"},
    "● %d 个模型": {"zh-TW": "● %d 個模型", "en": "● %d models", "ja": "● %d モデル"},
    "内置加速内核": {"zh-TW": "內置加速內核", "en": "Built-in accelerated core",
                     "ja": "内蔵高速化コア"},
    "● 未安装（可选）": {"zh-TW": "● 未安裝（可選）", "en": "● Not installed (optional)",
                         "ja": "● 未インストール（任意）"},
    "可选加速组件：装好后勾选「TensorRT 加速」可快 2~3 倍，未装则自动使用 ncnn。": {
        "zh-TW": "可選加速組件：裝好後勾選「TensorRT 加速」可快 2~3 倍，未裝則自動使用 ncnn。",
        "en": "Optional accelerator: tick \"TensorRT acceleration\" after installing for 2–3× speed; "
              "otherwise ncnn is used automatically.",
        "ja": "任意の高速化コンポーネント：導入後に「TensorRT 加速」をオンにすると 2〜3 倍速になります。"
              "未導入の場合は自動的に ncnn を使用します。"},
    "缺少：": {"zh-TW": "缺少：", "en": "Missing: ", "ja": "不足： "},
    "可选未装：": {"zh-TW": "可選未裝：", "en": "Optional, not installed: ", "ja": "任意・未導入： "},

    # 状态栏
    "环境：检查中…": {"zh-TW": "環境：檢查中…", "en": "Env: checking…", "ja": "環境：確認中…"},

    # 其它
    "补帧 + 超分 · 本地版": {"zh-TW": "補幀 + 超分 · 本地版", "en": "Frame Interp + Upscale · Local", "ja": "補間＋超解像 · ローカル版"},
    "● 已配置": {"zh-TW": "● 已配置", "en": "● Ready", "ja": "● 設定済み"},
    "● 未配置": {"zh-TW": "● 未配置", "en": "● Missing", "ja": "● 未設定"},
    "语言": {"zh-TW": "語言", "en": "Language", "ja": "言語"},
    "选择界面显示语言": {"zh-TW": "選擇界面顯示語言", "en": "Choose interface language", "ja": "表示言語を選択"},

    # 弹窗（由程序自己传入的标题与提示文字）
    "壁纸": {"zh-TW": "壁紙", "en": "Wallpaper", "ja": "壁紙"},
    "选择背景图片": {"zh-TW": "選擇背景圖片", "en": "Choose background image", "ja": "背景画像を選択"},
    "选择壁纸文件夹": {"zh-TW": "選擇壁紙文件夾", "en": "Choose wallpaper folder", "ja": "壁紙フォルダを選択"},
    "所选文件夹内没有找到壁纸文件。": {
        "zh-TW": "所選文件夾內沒有找到壁紙文件。",
        "en": "No wallpaper files found in the selected folder.",
        "ja": "選択したフォルダに壁紙ファイルが見つかりません。"},
    "支持的视频：mp4 / webm / mkv / mov / avi": {
        "zh-TW": "支持的視頻：mp4 / webm / mkv / mov / avi",
        "en": "Supported video: mp4 / webm / mkv / mov / avi",
        "ja": "対応動画：mp4 / webm / mkv / mov / avi"},
    "支持的图片：png / jpg / jpeg / webp / bmp / gif": {
        "zh-TW": "支持的圖片：png / jpg / jpeg / webp / bmp / gif",
        "en": "Supported image: png / jpg / jpeg / webp / bmp / gif",
        "ja": "対応画像：png / jpg / jpeg / webp / bmp / gif"},
    "无法加载壁纸模块：%s": {"zh-TW": "無法載入壁紙模組：%s", "en": "Failed to load wallpaper module: %s", "ja": "壁紙モジュールを読み込めません：%s"},
    "这个壁纸文件不存在。": {"zh-TW": "這個壁紙文件不存在。", "en": "This wallpaper file does not exist.", "ja": "この壁紙ファイルは存在しません。"},
    "当前是本地版 %s（%s），没有在线更新源。\n需要新版本时直接替换程序目录即可。": {
        "zh-TW": "目前是本地版 %s（%s），沒有線上更新源。\n需要新版本時直接替換程式目錄即可。",
        "en": "This is the local build %s (%s) with no online update source.\nTo update, replace the program folder directly.",
        "ja": "これはローカル版 %s（%s）で、オンライン更新元はありません。\n新しい版はプログラムフォルダを差し替えてください。"},

    "选择目录": {"zh-TW": "選擇目錄", "en": "Choose folder", "ja": "フォルダを選択"},
    "选择文件夹": {"zh-TW": "選擇文件夾", "en": "Choose folder", "ja": "フォルダを選択"},
    "选择输出目录": {"zh-TW": "選擇輸出目錄", "en": "Choose output folder", "ja": "出力先を選択"},
    "选择默认输出目录": {"zh-TW": "選擇預設輸出目錄", "en": "Choose default output folder", "ja": "既定の出力先を選択"},
    "选择素材": {"zh-TW": "選擇素材", "en": "Choose media", "ja": "素材を選択"},
    "选择视频": {"zh-TW": "選擇視頻", "en": "Choose video", "ja": "動画を選択"},
    "选择界面主题色": {"zh-TW": "選擇介面主題色", "en": "Choose accent color", "ja": "アクセントカラーを選択"},
    "选择文字颜色": {"zh-TW": "選擇文字顏色", "en": "Choose text color", "ja": "文字色を選択"},
    "图片 (*.png *.jpg *.jpeg *.webp *.bmp);;全部 (*.*)": {
        "zh-TW": "圖片 (*.png *.jpg *.jpeg *.webp *.bmp);;全部 (*.*)",
        "en": "Images (*.png *.jpg *.jpeg *.webp *.bmp);;All files (*.*)",
        "ja": "画像 (*.png *.jpg *.jpeg *.webp *.bmp);;すべて (*.*)"},
    "程序 (*.exe);;全部 (*.*)": {"zh-TW": "程式 (*.exe);;全部 (*.*)", "en": "Programs (*.exe);;All files (*.*)", "ja": "プログラム (*.exe);;すべて (*.*)"},
    "视频 (*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.ts);;全部 (*.*)": {
        "zh-TW": "視頻 (*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.ts);;全部 (*.*)",
        "en": "Video (*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.ts);;All files (*.*)",
        "ja": "動画 (*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.ts);;すべて (*.*)"},
    "素材 (*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.ts *.png *.jpg *.jpeg *.webp *.bmp);;全部 (*.*)": {
        "zh-TW": "素材 (*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.ts *.png *.jpg *.jpeg *.webp *.bmp);;全部 (*.*)",
        "en": "Media (*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.ts *.png *.jpg *.jpeg *.webp *.bmp);;All files (*.*)",
        "ja": "素材 (*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.ts *.png *.jpg *.jpeg *.webp *.bmp);;すべて (*.*)"},

    "检查完成": {"zh-TW": "檢查完成", "en": "Check complete", "ja": "確認完了"},
    "已配置 %d / %d 项工具。": {"zh-TW": "已配置 %d / %d 項工具。", "en": "%d of %d tools configured.", "ja": "%d / %d 個のツールを設定しました。"},
    "任务正在跑，等结束再加素材": {"zh-TW": "任務正在跑，等結束再加素材", "en": "A task is running; add media after it finishes.", "ja": "タスク実行中です。終了後に素材を追加してください。"},
    "先拖入或选择素材": {"zh-TW": "先拖入或選擇素材", "en": "Add or drop some media first.", "ja": "先に素材を追加してください。"},
    "已保存预设「%s」": {"zh-TW": "已保存預設「%s」", "en": "Preset \"%s\" saved.", "ja": "プリセット「%s」を保存しました。"},
    "保存失败：%s": {"zh-TW": "保存失敗：%s", "en": "Save failed: %s", "ja": "保存に失敗：%s"},
    "删除失败：%s": {"zh-TW": "刪除失敗：%s", "en": "Delete failed: %s", "ja": "削除に失敗：%s"},
    "预设名称：": {"zh-TW": "預設名稱：", "en": "Preset name:", "ja": "プリセット名："},
    "缺少 ffmpeg": {"zh-TW": "缺少 ffmpeg", "en": "ffmpeg missing", "ja": "ffmpeg が見つかりません"},
    "找不到 ffmpeg.exe": {"zh-TW": "找不到 ffmpeg.exe", "en": "ffmpeg.exe not found", "ja": "ffmpeg.exe が見つかりません"},
    "已保存": {"zh-TW": "已保存", "en": "Saved", "ja": "保存しました"},
    "任务正在跑，等结束再清理": {"zh-TW": "任務正在跑，等結束再清理", "en": "A task is running; clear the cache after it finishes.", "ja": "タスク実行中です。終了後にクリアしてください。"},
    "将删除补帧缓存和临时文件（含 C 盘旧缓存，约 %.0f MB）。\n继续？": {
        "zh-TW": "將刪除補幀緩存和臨時文件（含 C 盤舊緩存，約 %.0f MB）。\n繼續？",
        "en": "This deletes interpolation caches and temp files (including old C: caches, about %.0f MB).\nContinue?",
        "ja": "補間キャッシュと一時ファイル（C ドライブの旧キャッシュを含む、約 %.0f MB）を削除します。\n続行しますか？"},
    "已释放 %.0f MB": {"zh-TW": "已釋放 %.0f MB", "en": "Freed %.0f MB", "ja": "%.0f MB を解放しました"},

    # 壁纸选择对话框
    "选择壁纸": {"zh-TW": "選擇壁紙", "en": "Choose wallpaper", "ja": "壁紙を選択"},
    "共 %d 个壁纸（%d 个视频、%d 个图片）\n目录：%s": {
        "zh-TW": "共 %d 個壁紙（%d 個視頻、%d 個圖片）\n目錄：%s",
        "en": "%d wallpapers (%d video, %d image)\nFolder: %s",
        "ja": "壁紙 %d 件（動画 %d、画像 %d）\nフォルダ：%s"},
    "搜索壁纸文件名…": {"zh-TW": "搜尋壁紙文件名…", "en": "Search wallpaper name…", "ja": "壁紙名を検索…"},
    "选择左侧壁纸查看预览": {"zh-TW": "選擇左側壁紙查看預覽", "en": "Select a wallpaper to preview", "ja": "左の壁紙を選ぶとプレビューします"},
    "[视频]": {"zh-TW": "[視頻]", "en": "[Video]", "ja": "[動画]"},
    "[图片]": {"zh-TW": "[圖片]", "en": "[Image]", "ja": "[画像]"},
    "无预览图": {"zh-TW": "無預覽圖", "en": "No preview", "ja": "プレビューなし"},
    "设为背景": {"zh-TW": "設為背景", "en": "Set as background", "ja": "背景に設定"},
    "取消": {"zh-TW": "取消", "en": "Cancel", "ja": "キャンセル"},

    # 加速选项
    "超分按输出分辨率（更快）": {"zh-TW": "超分按輸出解析度（更快）", "en": "Super-res at output size (faster)", "ja": "出力解像度で超解像（高速）"},
    "先超分 → 再补帧（更快，推荐）": {"zh-TW": "先超分 → 再補幀（更快，推薦）",
                                     "en": "Upscale first → then interpolate (faster, recommended)",
                                     "ja": "超解像 → 補間の順（高速・推奨）"},
    "TensorRT 加速（NVIDIA 显卡）": {"zh-TW": "TensorRT 加速（NVIDIA 顯卡）", "en": "TensorRT acceleration (NVIDIA GPU)", "ja": "TensorRT アクセラレーション（NVIDIA GPU）"},

    # ---------------------------------------------------------------- 下拉选项：超分模型
    "Real-CUGAN 2x（动漫·主推）": {"zh-TW": "Real-CUGAN 2x（動漫·主推）",
                                   "en": "Real-CUGAN 2x (anime · recommended)",
                                   "ja": "Real-CUGAN 2x（アニメ・推奨）"},
    "Real-CUGAN 2x 保守（动漫）": {"zh-TW": "Real-CUGAN 2x 保守（動漫）",
                                   "en": "Real-CUGAN 2x conservative (anime)",
                                   "ja": "Real-CUGAN 2x 控えめ（アニメ）"},
    "Real-CUGAN 2x 轻降噪（动漫）": {"zh-TW": "Real-CUGAN 2x 輕降噪（動漫）",
                                     "en": "Real-CUGAN 2x light denoise (anime)",
                                     "ja": "Real-CUGAN 2x 弱ノイズ除去（アニメ）"},
    "Real-CUGAN 2x 中降噪（动漫）": {"zh-TW": "Real-CUGAN 2x 中降噪（動漫）",
                                     "en": "Real-CUGAN 2x medium denoise (anime)",
                                     "ja": "Real-CUGAN 2x 中ノイズ除去（アニメ）"},
    "Real-CUGAN 2x 无降噪（动漫）": {"zh-TW": "Real-CUGAN 2x 無降噪（動漫）",
                                     "en": "Real-CUGAN 2x no denoise (anime)",
                                     "ja": "Real-CUGAN 2x ノイズ除去なし（アニメ）"},
    "Real-CUGAN 3x 强降噪（动漫）": {"zh-TW": "Real-CUGAN 3x 強降噪（動漫）",
                                     "en": "Real-CUGAN 3x strong denoise (anime)",
                                     "ja": "Real-CUGAN 3x 強ノイズ除去（アニメ）"},
    "Real-CUGAN 3x 保守（动漫）": {"zh-TW": "Real-CUGAN 3x 保守（動漫）",
                                   "en": "Real-CUGAN 3x conservative (anime)",
                                   "ja": "Real-CUGAN 3x 控えめ（アニメ）"},
    "Real-CUGAN 3x 无降噪（动漫）": {"zh-TW": "Real-CUGAN 3x 無降噪（動漫）",
                                     "en": "Real-CUGAN 3x no denoise (anime)",
                                     "ja": "Real-CUGAN 3x ノイズ除去なし（アニメ）"},
    "Real-CUGAN 4x 强降噪（动漫）": {"zh-TW": "Real-CUGAN 4x 強降噪（動漫）",
                                     "en": "Real-CUGAN 4x strong denoise (anime)",
                                     "ja": "Real-CUGAN 4x 強ノイズ除去（アニメ）"},
    "Real-CUGAN 4x 保守（动漫）": {"zh-TW": "Real-CUGAN 4x 保守（動漫）",
                                   "en": "Real-CUGAN 4x conservative (anime)",
                                   "ja": "Real-CUGAN 4x 控えめ（アニメ）"},
    "Real-CUGAN 4x 无降噪（动漫）": {"zh-TW": "Real-CUGAN 4x 無降噪（動漫）",
                                     "en": "Real-CUGAN 4x no denoise (anime)",
                                     "ja": "Real-CUGAN 4x ノイズ除去なし（アニメ）"},
    "AnimeVideo-v3（老番修复）": {"zh-TW": "AnimeVideo-v3（老番修復）",
                                  "en": "AnimeVideo-v3 (old anime restore)",
                                  "ja": "AnimeVideo-v3（旧作修復）"},
    "Real-ESRGAN x4plus（真人/游戏）": {"zh-TW": "Real-ESRGAN x4plus（真人/遊戲）",
                                        "en": "Real-ESRGAN x4plus (live-action / games)",
                                        "ja": "Real-ESRGAN x4plus（実写・ゲーム）"},
    "（ncnn 内核）": {"zh-TW": "（ncnn 內核）", "en": " (ncnn core)", "ja": "（ncnn コア）"},

    # 下拉选项：补帧模型
    "RIFE 4.18（真人/游戏）": {"zh-TW": "RIFE 4.18（真人/遊戲）",
                               "en": "RIFE 4.18 (live-action / games)",
                               "ja": "RIFE 4.18（実写・ゲーム）"},
    "RIFE 4.26 large（高画质）": {"zh-TW": "RIFE 4.26 large（高畫質）",
                                  "en": "RIFE 4.26 large (high quality)",
                                  "ja": "RIFE 4.26 large（高画質）"},
    "RIFE 4.25 heavy（高画质）": {"zh-TW": "RIFE 4.25 heavy（高畫質）",
                                  "en": "RIFE 4.25 heavy (high quality)",
                                  "ja": "RIFE 4.25 heavy（高画質）"},
    "RIFE 4.6（通用）": {"zh-TW": "RIFE 4.6（通用）", "en": "RIFE 4.6 (general)", "ja": "RIFE 4.6（汎用）"},
    "RIFE 4.26（通用）": {"zh-TW": "RIFE 4.26（通用）", "en": "RIFE 4.26 (general)", "ja": "RIFE 4.26（汎用）"},
    "RIFE 4.25（通用）": {"zh-TW": "RIFE 4.25（通用）", "en": "RIFE 4.25 (general)", "ja": "RIFE 4.25（汎用）"},
    "RIFE 4.22（通用）": {"zh-TW": "RIFE 4.22（通用）", "en": "RIFE 4.22 (general)", "ja": "RIFE 4.22（汎用）"},

    # 下拉选项：其它
    "自动": {"zh-TW": "自動", "en": "Auto", "ja": "自動"},
    "目标码率": {"zh-TW": "目標碼率", "en": "Target bitrate", "ja": "目標ビットレート"},
    "源分辨率": {"zh-TW": "來源解析度", "en": "Source resolution", "ja": "元の解像度"},
    "PNG 序列": {"zh-TW": "PNG 序列", "en": "PNG sequence", "ja": "PNG 連番"},
    "JPG 序列": {"zh-TW": "JPG 序列", "en": "JPG sequence", "ja": "JPG 連番"},
    "WEBP 序列": {"zh-TW": "WEBP 序列", "en": "WEBP sequence", "ja": "WEBP 連番"},
    "（无预设）": {"zh-TW": "（無預設）", "en": "(no preset)", "ja": "（プリセットなし）"},
    "（没有找到超分模型）": {"zh-TW": "（沒有找到超分模型）", "en": "(no upscaler found)", "ja": "（超解像モデルが見つかりません）"},
    "（没有找到 RIFE 模型）": {"zh-TW": "（沒有找到 RIFE 模型）", "en": "(no RIFE model found)", "ja": "（RIFE モデルが見つかりません）"},
    "CRF / 质量": {"zh-TW": "CRF / 質量", "en": "CRF / quality", "ja": "CRF / 画質"},
    "目标 Mbps": {"zh-TW": "目標 Mbps", "en": "Target Mbps", "ja": "目標 Mbps"},

    # ---------------------------------------------------------------- 模型用途说明
    "默认主推动漫：平衡画质/速度/部署，漫剪素材首选": {
        "zh-TW": "預設主推動漫：平衡畫質/速度/部署，漫剪素材首選",
        "en": "Recommended for anime: balanced quality, speed and footprint; best first choice for anime edits.",
        "ja": "アニメ向け推奨：画質・速度・サイズのバランスが良く、アニメ編集の第一候補。"},
    "动漫保守修复：更少改动原画风，线条更自然": {
        "zh-TW": "動漫保守修復：更少改動原畫風，線條更自然",
        "en": "Anime conservative restore: keeps the original look, more natural lines.",
        "ja": "アニメ控えめ修復：元の絵柄を保ち、線が自然になります。"},
    "动漫轻降噪：轻度去噪": {
        "zh-TW": "動漫輕降噪：輕度去噪",
        "en": "Anime light denoise: gentle noise reduction.",
        "ja": "アニメ弱ノイズ除去：軽めのノイズ低減。"},
    "动漫中降噪：中等去噪强度": {
        "zh-TW": "動漫中降噪：中等去噪強度",
        "en": "Anime medium denoise: moderate strength.",
        "ja": "アニメ中ノイズ除去：中程度の強さ。"},
    "动漫无降噪：仅放大不降噪": {
        "zh-TW": "動漫無降噪：僅放大不降噪",
        "en": "Anime no denoise: upscale only, no noise reduction.",
        "ja": "アニメノイズ除去なし：拡大のみ。"},
    "动漫 3x：一步放大到 3 倍，强降噪，画质增强更明显": {
        "zh-TW": "動漫 3x：一步放大到 3 倍，強降噪，畫質增強更明顯",
        "en": "Anime 3x: one-step 3× upscale with strong denoise; more visible enhancement.",
        "ja": "アニメ 3x：一度に 3 倍へ、強ノイズ除去で効果が分かりやすい。"},
    "动漫 3x：更少改动原画风": {
        "zh-TW": "動漫 3x：更少改動原畫風",
        "en": "Anime 3x: keeps the original look.",
        "ja": "アニメ 3x：元の絵柄を保ちます。"},
    "动漫 3x：仅放大不降噪": {
        "zh-TW": "動漫 3x：僅放大不降噪",
        "en": "Anime 3x: upscale only, no denoise.",
        "ja": "アニメ 3x：拡大のみ。"},
    "动漫 4x：一步放大到 4K，强降噪，画质增强最强": {
        "zh-TW": "動漫 4x：一步放大到 4K，強降噪，畫質增強最強",
        "en": "Anime 4x: one-step upscale to 4K with strong denoise; strongest enhancement.",
        "ja": "アニメ 4x：一度に 4K へ、強ノイズ除去で最大の効果。"},
    "动漫 4x：更少改动原画风": {
        "zh-TW": "動漫 4x：更少改動原畫風",
        "en": "Anime 4x: keeps the original look.",
        "ja": "アニメ 4x：元の絵柄を保ちます。"},
    "动漫 4x：仅放大不降噪": {
        "zh-TW": "動漫 4x：僅放大不降噪",
        "en": "Anime 4x: upscale only, no denoise.",
        "ja": "アニメ 4x：拡大のみ。"},
    "老番/压缩严重素材：动漫视频专用修复": {
        "zh-TW": "老番/壓縮嚴重素材：動漫視頻專用修復",
        "en": "Old or heavily compressed anime: dedicated video restoration.",
        "ja": "旧作・圧縮の強い素材：アニメ動画専用の修復。"},
    "真人/游戏录屏：通用照片与实拍": {
        "zh-TW": "真人/遊戲錄屏：通用照片與實拍",
        "en": "Live-action and game captures: general photos and real footage.",
        "ja": "実写・ゲーム録画：写真や実写全般。"},
    "来自 SVFI 的 Real-CUGAN 模型（ncnn 内核）": {
        "zh-TW": "來自 SVFI 的 Real-CUGAN 模型（ncnn 內核）",
        "en": "Real-CUGAN model from SVFI (ncnn core).",
        "ja": "SVFI 由来の Real-CUGAN モデル（ncnn コア）。"},
    "真人 / 游戏录屏：大运动更稳": {
        "zh-TW": "真人 / 遊戲錄屏：大運動更穩",
        "en": "Live-action / game captures: steadier on large motion.",
        "ja": "実写・ゲーム録画：大きな動きに強い。"},
    "画质上限高，显存消耗较大（最新版大模型）": {
        "zh-TW": "畫質上限高，顯存消耗較大（最新版大模型）",
        "en": "High quality ceiling, heavier VRAM use (latest large model).",
        "ja": "画質の上限が高いが VRAM 消費大（最新の大型モデル）。"},
    "画质上限最高，显存消耗最大（真 heavy 大模型，社区公认最稳）": {
        "zh-TW": "畫質上限最高，顯存消耗最大（真 heavy 大模型，社群公認最穩）",
        "en": "Highest quality ceiling, heaviest VRAM use (true heavy model, widely regarded as most stable).",
        "ja": "画質の上限が最高、VRAM 消費も最大（真の heavy モデル、最も安定と評判）。"},
    "通用：2 代稳定老模型，非整数倍率": {
        "zh-TW": "通用：2 代穩定老模型，非整數倍率",
        "en": "General: stable 2nd-gen model, non-integer multipliers.",
        "ja": "汎用：第 2 世代の安定モデル、非整数倍に対応。"},
    "通用：较新标准版，均衡画质与速度": {
        "zh-TW": "通用：較新標準版，均衡畫質與速度",
        "en": "General: newer standard model, balanced quality and speed.",
        "ja": "汎用：新しい標準モデル、画質と速度のバランス型。"},
    "通用：标准版，均衡": {
        "zh-TW": "通用：標準版，均衡",
        "en": "General: standard model, balanced.",
        "ja": "汎用：標準モデル、バランス型。"},
    "通用：标准版": {
        "zh-TW": "通用：標準版", "en": "General: standard model.", "ja": "汎用：標準モデル。"},

    # ---------------------------------------------------------------- 模式提示
    "图片超分：按超分模型倍率放大，输出 PNG / JPG / WEBP。": {
        "zh-TW": "圖片超分：按超分模型倍率放大，輸出 PNG / JPG / WEBP。",
        "en": "Image upscale: enlarge by the model's scale factor, output PNG / JPG / WEBP.",
        "ja": "画像超解像：モデルの倍率で拡大し、PNG / JPG / WEBP で出力。"},
    "视频超分：按源帧率输出，只做超分。": {
        "zh-TW": "視頻超分：按來源幀率輸出，只做超分。",
        "en": "Video upscale: keep the source frame rate, upscale only.",
        "ja": "動画超解像：元のフレームレートで出力、超解像のみ。"},
    "视频补帧：只补帧，输出到目标帧率。": {
        "zh-TW": "視頻補幀：只補幀，輸出到目標幀率。",
        "en": "Frame interpolation: interpolate only, output at the target frame rate.",
        "ja": "フレーム補間：補間のみ、目標フレームレートで出力。"},
    "逐段完成超分与补帧，兼顾清晰度、流畅度和临时空间。": {
        "zh-TW": "逐段完成超分與補幀，兼顧清晰度、流暢度和臨時空間。",
        "en": "Upscale and interpolate in stages, balancing sharpness, smoothness and disk use.",
        "ja": "超解像と補間を段階的に実行し、画質・滑らかさ・一時領域を両立。"},
    "超分：%s": {"zh-TW": "超分：%s", "en": "Upscale: %s", "ja": "超解像：%s"},
    "补帧：%s（%s）": {"zh-TW": "補幀：%s（%s）", "en": "Interp: %s (%s)", "ja": "補間：%s（%s）"},
    "帧流法：内置内核原生（改参数不重启）": {
        "zh-TW": "幀流法：內置內核原生（改參數不重啟）",
        "en": "Frame flow: native in the built-in core (parameter change needs no restart)",
        "ja": "フレームフロー：内蔵コアのネイティブ（パラメータ変更で再起動不要）"},

    # ---------------------------------------------------------------- 参数区标签与状态
    "内核": {"zh-TW": "內核", "en": "Core", "ja": "コア"},
    "推理设备": {"zh-TW": "推理設備", "en": "Device", "ja": "推論デバイス"},
    "超分模型": {"zh-TW": "超分模型", "en": "Upscaler", "ja": "超解像モデル"},
    "补帧模型": {"zh-TW": "補幀模型", "en": "Interpolation model", "ja": "補間モデル"},
    "补帧方式": {"zh-TW": "補幀方式", "en": "Interp method", "ja": "補間方法"},
    "输出帧率": {"zh-TW": "輸出幀率", "en": "Output FPS", "ja": "出力フレームレート"},
    "码率": {"zh-TW": "碼率", "en": "Bitrate", "ja": "ビットレート"},
    "输出分辨率": {"zh-TW": "輸出解析度", "en": "Output resolution", "ja": "出力解像度"},
    "输出格式": {"zh-TW": "輸出格式", "en": "Output format", "ja": "出力形式"},
    "分块": {"zh-TW": "分塊", "en": "Tile size", "ja": "タイルサイズ"},
    "开始队列": {"zh-TW": "開始隊列", "en": "Start queue", "ja": "キュー開始"},
    "共 %d 个素材": {"zh-TW": "共 %d 個素材", "en": "%d items", "ja": "素材 %d 件"},
    "已选择 %d 个素材": {"zh-TW": "已選擇 %d 個素材", "en": "%d items selected", "ja": "素材 %d 件を選択"},
    "构建：%s": {"zh-TW": "構建：%s", "en": "Build: %s", "ja": "ビルド：%s"},
    "哔哩哔哩主页": {"zh-TW": "嗶哩嗶哩主頁", "en": "bilibili page", "ja": "bilibili ページ"},
    "GitHub 官网": {"zh-TW": "GitHub 官網", "en": "GitHub", "ja": "GitHub"},
    "打开 CHEN-V 的 GitHub 项目主页（源码、更新日志、提 Issue）": {
        "zh-TW": "開啟 CHEN-V 的 GitHub 專案主頁（原始碼、更新日誌、回報 Issue）",
        "en": "Open the CHEN-V GitHub project page (source code, changelog, report an issue)",
        "ja": "CHEN-V の GitHub プロジェクトページを開く（ソースコード、更新履歴、Issue 報告）"},
    "字体描边": {"zh-TW": "字體描邊", "en": "Text outline", "ja": "文字の縁取り"},
    "数值越大，文字描边越明显，背景复杂时更清晰（0=关闭）": {
        "zh-TW": "數值越大，文字描邊越明顯，背景複雜時更清晰（0=關閉）",
        "en": "Higher values make the outline stronger, which helps on busy backgrounds (0 = off).",
        "ja": "値を大きくするほど縁取りが強くなり、複雑な背景でも読みやすくなります（0＝オフ）。"},
    "拖动时暂停动态壁纸": {"zh-TW": "拖動時暫停動態壁紙",
                          "en": "Pause animated wallpaper while dragging",
                          "ja": "ドラッグ中は動く壁紙を停止"},
    "系统默认": {"zh-TW": "系統預設", "en": "System default", "ja": "システム既定"},
    "工作目录": {"zh-TW": "工作目錄", "en": "Working folder", "ja": "作業フォルダ"},
    "缓存目录": {"zh-TW": "緩存目錄", "en": "Cache folder", "ja": "キャッシュフォルダ"},
    "Xintao Wang 等（xinntao/Real-ESRGAN）": {
        "zh-TW": "Xintao Wang 等（xinntao/Real-ESRGAN）",
        "en": "Xintao Wang et al. (xinntao/Real-ESRGAN)",
        "ja": "Xintao Wang ら（xinntao/Real-ESRGAN）"},
    "腾讯优图 nihui 等（Tencent/ncnn）": {
        "zh-TW": "騰訊優圖 nihui 等（Tencent/ncnn）",
        "en": "Tencent Youtu, nihui et al. (Tencent/ncnn)",
        "ja": "Tencent Youtu の nihui ら（Tencent/ncnn）"},
    "Fredrik Mellbin 等": {
        "zh-TW": "Fredrik Mellbin 等",
        "en": "Fredrik Mellbin et al.",
        "ja": "Fredrik Mellbin ら"},
    "Microsoft": {"zh-TW": "Microsoft", "en": "Microsoft", "ja": "Microsoft"},
    "The Qt Company": {"zh-TW": "The Qt Company", "en": "The Qt Company", "ja": "The Qt Company"},
    "NVIDIA Corporation": {"zh-TW": "NVIDIA Corporation", "en": "NVIDIA Corporation", "ja": "NVIDIA Corporation"},
    "AmusementClub（vs-mlrt）": {"zh-TW": "AmusementClub（vs-mlrt）",
                                 "en": "AmusementClub (vs-mlrt)",
                                 "ja": "AmusementClub（vs-mlrt）"},

    # ---------------------------------------------------------------- 关于页（长段落，按标识取译文）
    "about.free.1": {
        "zh-TW": "該應用由辰師獨立開發，所有功能免費使用。你可以轉載與分享本軟體，"
                 "但請勿將其收費出售。",
        "en": "This app is independently developed by Chenshi. Every feature is free to use. "
              "You may redistribute and share it, but please do not sell it for profit.",
        "ja": "本アプリは辰師が個人で開発したもので、すべての機能を無料で利用できます。"
              "再配布・共有は自由ですが、有償での販売はご遠慮ください。"},

    # 支持作者（官网更新页按钮 + 打赏弹窗）
    "支持 CHEN-V": {"zh-TW": "支持 CHEN-V", "en": "Support CHEN-V", "ja": "CHEN-V を支援"},
    "所有功能完全免费。如果这个工具帮你省下了时间，可以请作者喝杯咖啡。": {
        "zh-TW": "所有功能完全免費。如果這個工具幫你省下了時間，可以請作者喝杯咖啡。",
        "en": "Every feature is completely free. If this tool saved you some time, "
              "you can buy the author a coffee.",
        "ja": "すべての機能は完全無料です。このツールがお役に立てば、"
              "作者にコーヒーを一杯おごっていただけると嬉しいです。"},
    "微信支付": {"zh-TW": "微信支付", "en": "WeChat Pay", "ja": "WeChat Pay"},
    "支付宝": {"zh-TW": "支付寶", "en": "Alipay", "ja": "Alipay"},
    "点击用系统看图工具打开，方便扫码": {
        "zh-TW": "點擊用系統看圖工具打開，方便掃碼",
        "en": "Click to open in your image viewer for easier scanning",
        "ja": "クリックで画像ビューアが開き、読み取りやすくなります"},
    "自愿支持作者。捐赠与否不影响任何功能使用。": {
        "zh-TW": "自願支持作者。捐贈與否不影響任何功能使用。",
        "en": "Supporting the author is entirely voluntary. "
              "Donating or not does not affect any functionality.",
        "ja": "作者への支援は任意です。寄付の有無にかかわらず、"
              "すべての機能をご利用いただけます。"},
    "关闭": {"zh-TW": "關閉", "en": "Close", "ja": "閉じる"},
    "没有找到收款码图片（素材目录：assets）。\n程序所有功能依然可以正常使用。": {
        "zh-TW": "沒有找到收款碼圖片（素材目錄：assets）。\n程式所有功能依然可以正常使用。",
        "en": "No payment QR images found (assets folder).\n"
              "All features still work normally.",
        "ja": "支払い用 QR 画像が見つかりません（assets フォルダ）。\n"
              "すべての機能は通常どおり利用できます。"},

    # 加入聊群（官网更新页按钮 + 群二维码弹窗）
    "加入聊群": {"zh-TW": "加入聊群", "en": "Join the chat", "ja": "チャットに参加"},
    "欢迎加入 CHEN-V 交流群，反馈问题、交流用法、获取更新。": {
        "zh-TW": "歡迎加入 CHEN-V 交流群，回報問題、交流用法、獲取更新。",
        "en": "Welcome to the CHEN-V group — report issues, share tips and get updates.",
        "ja": "CHEN-V 交流グループへようこそ。不具合報告や使い方の共有、更新情報をお届けします。"},
    "群号：1130651819": {"zh-TW": "群號：1130651819", "en": "Group ID: 1130651819", "ja": "グループID：1130651819"},
    "群聊二维码图片无法读取。": {
        "zh-TW": "群聊二維碼圖片無法讀取。",
        "en": "The group QR image could not be read.",
        "ja": "グループQR画像を読み込めませんでした。"},
    "没有找到群聊二维码图片（素材目录：assets）。\n程序所有功能依然可以正常使用。": {
        "zh-TW": "沒有找到群聊二維碼圖片（素材目錄：assets）。\n程式所有功能依然可以正常使用。",
        "en": "No group QR image found (assets folder).\n"
              "All features still work normally.",
        "ja": "グループQR画像が見つかりません（assets フォルダ）。\n"
              "すべての機能は通常どおり利用できます。"},

    "about.intro.1": {
        "zh-TW": "CHEN-V · 補幀 + 超分",
        "en": "CHEN-V · Frame interpolation + upscaling",
        "ja": "CHEN-V · フレーム補間 + 超解像"},
    "about.intro.2": {
        "zh-TW": "RIFE ncnn 補幀 + Real-CUGAN / Real-ESRGAN 超分，"
                 "支援視頻 / 圖片 / 批量隊列 / 圖片序列輸出。",
        "en": "RIFE ncnn interpolation + Real-CUGAN / Real-ESRGAN upscaling. "
              "Supports video, images, batch queues and image-sequence output.",
        "ja": "RIFE ncnn による補間 + Real-CUGAN / Real-ESRGAN による超解像。"
              "動画・画像・バッチキュー・連番画像の出力に対応します。"},
    "about.intro.3": {
        "zh-TW": "內置加速內核常駐運行，底層使用本地 ncnn / ONNX 模型。",
        "en": "The built-in accelerated core stays resident and runs local ncnn / ONNX models.",
        "ja": "内蔵の高速化コアが常駐し、ローカルの ncnn / ONNX モデルで動作します。"},

    "about.disclaimer.1": {
        "zh-TW": "1. 本軟體為本地視頻處理工具，僅供個人學習、研究與合法用途，"
                 "請勿用於任何違反法律法規的活動。",
        "en": "1. This software is a local video processing tool for personal study, research "
              "and lawful use. Do not use it for any activity that violates the law.",
        "ja": "1. 本ソフトはローカル動画処理ツールであり、個人の学習・研究・合法な用途のみを"
              "目的とします。法令に反する行為には使用しないでください。"},
    "about.disclaimer.2": {
        "zh-TW": "2. 軟體內置的超分與補幀模型均來自第三方開源項目，其著作權歸原作者所有；"
                 "本軟體僅提供推理調用，不主張對模型權重的任何權利。",
        "en": "2. The upscaling and interpolation models bundled here come from third-party "
              "open-source projects and remain the property of their authors. This software "
              "only invokes them for inference and claims no rights over the model weights.",
        "ja": "2. 内蔵の超解像・補間モデルは第三者によるオープンソースプロジェクト由来で、"
              "著作権は各作者に帰属します。本ソフトは推論のために呼び出すだけで、"
              "モデル重みに関する権利を主張しません。"},
    "about.disclaimer.3": {
        "zh-TW": "3. 處理結果的質量取決於來源素材，本軟體不對輸出內容的準確性、"
                 "可用性或商業價值作任何明示或默示保證。",
        "en": "3. Output quality depends on the source material. This software makes no express "
              "or implied warranty as to the accuracy, usability or commercial value of results.",
        "ja": "3. 処理結果の品質は元素材に依存します。本ソフトは出力内容の正確性・"
              "有用性・商業的価値についていかなる保証も行いません。"},
    "about.disclaimer.4": {
        "zh-TW": "4. 使用本軟體處理他人作品時，請自行確認已獲得相應授權，"
                 "遵守相關版權與肖像權規定。",
        "en": "4. When processing other people's work, make sure you hold the necessary "
              "authorization and comply with copyright and likeness rules.",
        "ja": "4. 他人の作品を処理する場合は、必要な許諾を得ていることをご自身で確認し、"
              "著作権・肖像権の規定を守ってください。"},
    "about.disclaimer.5": {
        "zh-TW": "5. 因使用本軟體造成的任何直接或間接損失，開發者不承擔相關責任。",
        "en": "5. The developer assumes no liability for any direct or indirect loss arising "
              "from the use of this software.",
        "ja": "5. 本ソフトの使用により生じた直接的・間接的な損害について、"
              "開発者は一切の責任を負いません。"},

    "lic.ffmpeg": {
        "zh-TW": "採用 GNU LGPL 2.1 或更高版本許可；包含 GPL 組件的構建受 GPL 約束。",
        "en": "Licensed under GNU LGPL 2.1 or later; builds that include GPL components are "
              "subject to the GPL.",
        "ja": "GNU LGPL 2.1 以降で提供されます。GPL コンポーネントを含むビルドは GPL に従います。"},
    "lic.esrgan": {
        "zh-TW": "版權歸其作者所有（Xintao Wang 等），採用 BSD 3-Clause 許可。",
        "en": "Copyright its authors (Xintao Wang et al.), licensed under BSD 3-Clause.",
        "ja": "著作権は作者（Xintao Wang ら）に帰属し、BSD 3-Clause ライセンスです。"},
    "lic.cugan": {
        "zh-TW": "版權歸 bilibili AI 實驗室所有，採用 MIT 許可；本軟體僅調用隨軟體提供的"
                 "本地模型與組件，不對模型權重主張任何權利。",
        "en": "Copyright bilibili AI Lab, licensed under MIT. This software only calls the local "
              "models and components shipped with it and claims no rights over the model weights.",
        "ja": "著作権は bilibili AI ラボに帰属し、MIT ライセンスです。本ソフトは同梱の"
              "ローカルモデルとコンポーネントを呼び出すだけで、モデル重みに関する権利を主張しません。"},
    "lic.rife": {
        "zh-TW": "版權歸曠視研究院所有，rife-ncnn-vulkan 採用 MIT 許可，模型源自 RIFE 項目。",
        "en": "Copyright Megvii Research. rife-ncnn-vulkan is MIT-licensed; the models come "
              "from the RIFE project.",
        "ja": "著作権は Megvii Research に帰属します。rife-ncnn-vulkan は MIT ライセンスで、"
              "モデルは RIFE プロジェクト由来です。"},
    "lic.ncnn": {
        "zh-TW": "版權歸騰訊優圖 nihui 等所有（Tencent/ncnn），採用 BSD 3-Clause 許可。",
        "en": "Copyright Tencent Youtu, nihui et al. (Tencent/ncnn), licensed under BSD 3-Clause.",
        "ja": "著作権は Tencent Youtu の nihui ら（Tencent/ncnn）に帰属し、BSD 3-Clause ライセンスです。"},
    "lic.vsmlrt": {
        "zh-TW": "版權歸 Amusement Club 及其貢獻者所有，採用 GNU GPL 3.0 許可。"
                 "本軟體將 vsncnn 作為內置內核在獨立進程中運行，僅通過標準輸入輸出管道傳遞任務，"
                 "主程式碼與其不構成鏈接關係。許可全文見 vrt/licenses/GPL-3.0.txt，"
                 "源碼：https://github.com/AmusementClub/vs-mlrt 。",
        "en": "Copyright Amusement Club and its contributors, licensed under GNU GPL 3.0. "
              "This software runs vsncnn as a built-in core in a separate process and passes "
              "jobs only through stdin/stdout pipes, so the main program does not link against it. "
              "Full license text: vrt/licenses/GPL-3.0.txt; "
              "source: https://github.com/AmusementClub/vs-mlrt .",
        "ja": "著作権は Amusement Club とその貢献者に帰属し、GNU GPL 3.0 ライセンスです。"
              "本ソフトは vsncnn を内蔵コアとして別プロセスで実行し、標準入出力のパイプのみで"
              "処理を渡すため、本体コードとはリンクしません。"
              "ライセンス全文：vrt/licenses/GPL-3.0.txt、"
              "ソース：https://github.com/AmusementClub/vs-mlrt 。"},
    "lic.vapoursynth": {
        "zh-TW": "版權歸 Fredrik Mellbin 等所有，採用 GNU LGPL 2.1 許可，作為視頻處理內核。",
        "en": "Copyright Fredrik Mellbin et al., licensed under GNU LGPL 2.1, "
              "used as the video processing core.",
        "ja": "著作権は Fredrik Mellbin らに帰属し、GNU LGPL 2.1 ライセンスで、"
              "映像処理コアとして使用しています。"},
    "lic.onnxruntime": {
        "zh-TW": "版權歸 Microsoft 所有，採用 MIT 許可，用於 ONNX 模型推理。",
        "en": "Copyright Microsoft, licensed under MIT, used for ONNX model inference.",
        "ja": "著作権は Microsoft に帰属し、MIT ライセンスで、ONNX モデルの推論に使用しています。"},
    "lic.tensorrt": {
        "zh-TW": "版權歸 NVIDIA Corporation 所有，為閉源專有軟體，"
                 "受 NVIDIA Software License Agreement 約束；"
                 "可隨本軟體以二進制形式免費分發，僅限在 NVIDIA GPU 上運行，"
                 "不得單獨分發、逆向工程或用於非 NVIDIA 硬體。",
        "en": "Copyright NVIDIA Corporation. Proprietary closed-source software governed by the "
              "NVIDIA Software License Agreement. It may be redistributed in binary form together "
              "with this software, runs only on NVIDIA GPUs, and must not be distributed "
              "separately, reverse-engineered or used on non-NVIDIA hardware.",
        "ja": "著作権は NVIDIA Corporation に帰属するクローズドソースの専有ソフトで、"
              "NVIDIA Software License Agreement に従います。本ソフトと共にバイナリ形式で"
              "無償配布できますが、NVIDIA GPU 上でのみ動作し、単独での配布・リバースエンジニアリング・"
              "NVIDIA 以外のハードでの利用は禁止されています。"},
    "lic.qt": {
        "zh-TW": "版權歸 The Qt Company 所有，採用 LGPL/GPL 許可，用於圖形介面。",
        "en": "Copyright The Qt Company, licensed under LGPL/GPL, used for the graphical interface.",
        "ja": "著作権は The Qt Company に帰属し、LGPL/GPL ライセンスで、GUI に使用しています。"},

    # 启动过渡页
    "正在启动…": {"zh-TW": "正在啟動…", "en": "Starting…", "ja": "起動中…"},
    "正在搭建界面…": {"zh-TW": "正在建立介面…", "en": "Building the interface…",
                      "ja": "画面を構築しています…"},
    "正在恢复设置…": {"zh-TW": "正在還原設定…", "en": "Restoring settings…",
                      "ja": "設定を復元しています…"},
    "正在应用外观…": {"zh-TW": "正在套用外觀…", "en": "Applying appearance…",
                      "ja": "外観を適用しています…"},
    "即将完成…": {"zh-TW": "即將完成…", "en": "Almost ready…", "ja": "まもなく完了…"},
    "补帧 + 超分 · 本地运行": {"zh-TW": "補幀 + 超分 · 本機執行",
                               "en": "Super-res + Interp · on device",
                               "ja": "補間 + 超解像 · ローカル"},
    "正在检测本机硬件…": {"zh-TW": "正在偵測本機硬體…", "en": "Detecting hardware…",
                          "ja": "ハードウェアを検出しています…"},
    "首次打开时自动检测本机硬件…": {"zh-TW": "首次打開時自動偵測本機硬體…",
                                     "en": "Hardware is detected the first time you open this page…",
                                     "ja": "このページを最初に開いたときにハードウェアを検出します…"},

    # ---------------------------------------------------------------- 控件提示（tooltip）
    # 模式按钮的说明（gui_main._mode_tips）
    "图片超分：用超分模型把图片放大并增强画质，输出 PNG/JPG/WEBP": {
        "zh-TW": "圖片超分：用超分模型把圖片放大並增強畫質，輸出 PNG/JPG/WEBP",
        "en": "Image upscale: enlarge and sharpen images with an upscale model; outputs PNG/JPG/WEBP",
        "ja": "画像超解像：超解像モデルで画像を拡大し画質を強化、PNG/JPG/WEBP で出力"},
    "视频超分：保持源帧率不变，只用超分模型放大画面、增强清晰度": {
        "zh-TW": "影片超分：保持來源幀率不變，只用超分模型放大畫面、增強清晰度",
        "en": "Video upscale: keep the source frame rate and only upscale/enhance the picture",
        "ja": "動画超解像：元のフレームレートを保ち、超解像のみで画質を向上"},
    "视频补帧：用 RIFE 模型在两帧之间插帧，提升流畅度（帧率翻倍），不超分": {
        "zh-TW": "影片補幀：用 RIFE 模型在兩幀之間插幀，提升流暢度（幀率翻倍），不超分",
        "en": "Frame interpolation: insert frames with RIFE for smoother motion (frame rate doubles); no upscaling",
        "ja": "フレーム補間：RIFE でフレーム間に補間し滑らかに（フレームレート2倍）。超解像なし"},
    "超分并补帧：先补帧再超分，同时提升流畅度和清晰度（效果最好，耗时最长）": {
        "zh-TW": "超分並補幀：先補幀再超分，同時提升流暢度和清晰度（效果最好，耗時最長）",
        "en": "Upscale + interpolate: interpolate then upscale for both smoothness and clarity (best result, slowest)",
        "ja": "超解像＋補間：補間してから超解像。滑らかさと鮮明さを両立（最高画質・最も低速）"},
    '参数预设：一键加载已保存的整套参数组合': {"zh-TW": '參數預設：一鍵載入已保存的整套參數組合', "en": 'Presets: load a saved parameter set in one click', "ja": 'プリセット：保存したパラメータ一式をワンクリックで読み込みます'},
    '把当前所有参数保存为一个命名预设': {"zh-TW": '把目前所有參數儲存為一個命名預設', "en": 'Save all current settings as a named preset', "ja": '現在の全設定を名前付きプリセットとして保存します'},
    '删除当前选中的预设': {"zh-TW": '刪除目前選取的預設', "en": 'Delete the selected preset', "ja": '選択中のプリセットを削除します'},
    '选择一个或多个视频/图片文件加入队列': {"zh-TW": '選擇一個或多個影片/圖片檔案加入佇列', "en": 'Pick one or more video/image files to add to the queue', "ja": '動画・画像ファイルを1つ以上選んでキューに追加します'},
    '选择整个文件夹，自动加入其中所有可处理的视频/图片素材': {"zh-TW": '選擇整個資料夾，自動加入其中所有可處理的影片/圖片素材', "en": 'Pick a whole folder; every supported video/image inside is added automatically', "ja": 'フォルダを選ぶと、対応する動画・画像をまとめて追加します'},
    '清空素材队列中的所有任务（不影响正在处理的任务）': {"zh-TW": '清空素材佇列中的所有任務（不影響正在處理的任務）', "en": 'Clear all tasks in the queue (the running task keeps going)', "ja": 'キューの全タスクを消去します（実行中のタスクは継続）'},
    '从队列中移除当前选中的素材（也可右键选移除）': {"zh-TW": '從佇列中移除目前選取的素材（也可右鍵選移除）', "en": 'Remove the selected item from the queue (or right-click → Remove)', "ja": '選択中の素材をキューから削除します（右クリック→削除も可）'},
    '开始依次处理队列中的所有素材，并跳转到进度页查看实时日志': {"zh-TW": '開始依序處理佇列中的所有素材，並跳轉到進度頁檢視即時日誌', "en": 'Process the whole queue in order and switch to Progress for live logs', "ja": 'キューの全素材を順番に処理し、進捗ページでログを表示します'},
    '超分模型分类：动漫主推 / 老番修复 / 真人游戏等，悬停查看用途': {"zh-TW": '超分模型分類：動漫主推 / 老番修復 / 真人遊戲等，懸停檢視用途', "en": 'Upscale model groups: anime-recommended / old-anime restore / live action & games; hover an item for its use case', "ja": '超解像モデルの分類：アニメ推奨／旧作修復／実写・ゲームなど。項目にカーソルを合わせると用途が出ます'},
    'RIFE 补帧模型：动漫向 / 真人游戏 / 高画质 heavy 等分类，悬停查看用途': {"zh-TW": 'RIFE 補幀模型：動漫向 / 真人遊戲 / 高畫質 heavy 等分類，懸停檢視用途', "en": 'RIFE interpolation models: anime / live action & games / high-quality heavy; hover an item for its use case', "ja": 'RIFE 補間モデル：アニメ向け／実写・ゲーム向け／高画質 heavy など。項目にカーソルで用途表示'},
    '补帧倍率：2× 即每两帧之间插一帧，帧率翻倍。\n倍率越高画面越流畅，但帧数越多、耗时越长、体积越大。': {"zh-TW": '補幀倍率：2× 即每兩幀之間插一幀，幀率翻倍。\n倍率越高畫面越流暢，但幀數越多、耗時越長、體積越大。', "en": 'Interpolation factor: 2× inserts one frame between every two, doubling the frame rate.\nHigher factors look smoother but mean more frames, longer runs and bigger files.', "ja": '補間倍率：2× は2フレームごとに1枚挿入し、フレームレートが2倍になります。\n倍率を上げるほど滑らかになりますが、フレーム数・処理時間・ファイルサイズが増えます。'},
    '按倍率补帧：选择 2×/3×/4×/5×，在源帧率基础上翻倍（如 24fps→48fps）': {"zh-TW": '按倍率補幀：選擇 2×/3×/4×/5×，在來源幀率基礎上翻倍（如 24fps→48fps）', "en": 'Interpolate by factor: pick 2×/3×/4×/5× to multiply the source frame rate (e.g. 24 → 48 fps)', "ja": '倍率で補間：2×/3×/4×/5× を選ぶと元のフレームレートを整数倍します（例 24fps→48fps）'},
    '按输出帧率补帧：直接指定目标帧率（如 60fps、120fps），\n适合把任意源帧率统一到标准帧率': {"zh-TW": '按輸出幀率補幀：直接指定目標幀率（如 60fps、120fps），\n適合把任意來源幀率統一至標準幀率', "en": 'Interpolate to a target FPS: set the output frame rate directly (e.g. 60 or 120 fps);\nuseful for normalising any source frame rate', "ja": '出力FPS指定：目標フレームレートを直接指定します（例 60fps、120fps）。\n元のフレームレートを規格値に揃えたいときに便利です'},
    '目标输出帧率：60 流畅、120 顺滑。帧率越高帧数越多，\n耗时和体积成正比增加，建议按素材类型选择': {"zh-TW": '目標輸出幀率：60 流暢、120 順滑。幀率越高幀數越多，\n耗時和體積成正比增加，建議依素材類型選擇', "en": 'Target output FPS: 60 is smooth, 120 is very smooth. More frames means proportionally longer runs and bigger files, so pick per source type', "ja": '目標出力FPS：60 で滑らか、120 で非常に滑らか。フレーム数に比例して処理時間とサイズが増えるため、素材に応じて選んでください'},
    '编码器：H265 比 H264 体积更小、画质更好；NVENC 走英伟达显卡\n硬件编码，速度快、几乎不占 CPU；10bit 色彩过渡更平滑': {"zh-TW": '編碼器：H265 比 H264 體積更小、畫質更好；NVENC 走 NVIDIA 顯卡\n硬體編碼，速度快、幾乎不佔 CPU；10bit 色彩過渡更平滑', "en": 'Encoder: H265 is smaller and sharper than H264; NVENC uses the NVIDIA GPU for hardware encoding, which is fast and barely touches the CPU; 10-bit gives smoother colour gradients', "ja": 'エンコーダー：H265 は H264 より小さく高画質。NVENC は NVIDIA GPU のハードウェアエンコードで高速かつ CPU 負荷ほぼゼロ。10bit は色の階調が滑らかになります'},
    '编码器：H265 比 H264 体积更小、画质更好；NVENC/AMF/QSV 分别走\n英伟达 / AMD / 英特尔显卡硬件编码，速度快、几乎不占 CPU；\n10bit 色彩过渡更平滑。列表只显示当前显卡能用的硬件档': {"zh-TW": '編碼器：H265 比 H264 體積更小、畫質更好；NVENC/AMF/QSV 分別走\nNVIDIA / AMD / Intel 顯卡硬體編碼，速度快、幾乎不佔 CPU；\n10bit 色彩過渡更平滑。清單只顯示目前顯卡可用的硬體檔', "en": 'Encoder: H265 is smaller and sharper than H264; NVENC/AMF/QSV use the NVIDIA / AMD / Intel GPU for hardware encoding, which is fast and barely touches the CPU;\n10-bit gives smoother colour gradients. Only hardware tiers your GPU supports are listed', "ja": 'エンコーダー：H265 は H264 より小さく高画質。NVENC/AMF/QSV はそれぞれ NVIDIA／AMD／Intel GPU のハードウェアエンコードで高速かつ CPU 負荷ほぼゼロ。\n10bit は色の階調が滑らかになります。一覧には現在の GPU で使えるハードウェアのみ表示されます'},
    '码率控制方式：CRF 按质量恒定（推荐，画质稳定）；\n目标码率按固定码率（体积可控，但复杂画面可能糊）': {"zh-TW": '碼率控制方式：CRF 按品質恆定（推薦，畫質穩定）；\n目標碼率按固定碼率（體積可控，但複雜畫面可能糊）', "en": 'Rate control: CRF keeps quality constant (recommended, stable output);\ntarget bitrate fixes the bitrate (predictable size, but complex scenes may blur)', "ja": 'レート制御：CRF は品質一定（推奨、画質が安定）。\n目標ビットレートは固定レート（サイズ予測可、ただし複雑な映像は潰れる場合あり）'},
    'CRF 越大体积越小、画质略降（推荐 18~23）；\n16 接近无损但体积很大，20 是高画质与体积的平衡点，23 更省空间': {"zh-TW": 'CRF 越大體積越小、畫質略降（推薦 18~23）；\n16 接近無損但體積很大，20 是高畫質與體積的平衡點，23 更省空間', "en": 'Higher CRF means smaller files and slightly lower quality (18~23 recommended);\n16 is near-lossless but huge, 20 balances quality and size, 23 saves more space', "ja": 'CRF が大きいほど小さく画質は少し低下（18~23 推奨）。\n16 はほぼ可逆だが巨大、20 は画質とサイズのバランス、23 は容量節約'},
    '输出分辨率：源分辨率=保持原样（超分后按模型倍率放大输出）；\n百分比=缩放；HD/UHD 预设=固定分辨率。注意超分模型自带固定倍率，\n最终尺寸由「超分倍率 × 源分辨率」决定': {"zh-TW": '輸出解析度：來源解析度=保持原樣（超分後按模型倍率放大輸出）；\n百分比=縮放；HD/UHD 預設=固定解析度。注意超分模型自帶固定倍率，\n最終尺寸由「超分倍率 × 來源解析度」決定', "en": "Output resolution: Source keeps the original size (the model's own factor applies);\npercentage scales it; HD/UHD presets pin a fixed size. Note each upscale model has a fixed factor,\nso the final size is factor × source resolution", "ja": '出力解像度：元の解像度はそのまま（モデルの倍率で拡大）。\nパーセントは拡大縮小、HD/UHD プリセットは固定解像度。超解像モデルは固定倍率を持つため、\n最終サイズは「倍率 × 元解像度」で決まります'},
    '输出格式：MP4/MKV 为视频文件；PNG/JPG/WEBP 序列为逐帧图片，\n适合后期再处理，但比视频慢很多': {"zh-TW": '輸出格式：MP4/MKV 為影片檔案；PNG/JPG/WEBP 序列為逐幀圖片，\n適合後期再處理，但比影片慢很多', "en": 'Output format: MP4/MKV are video files; PNG/JPG/WEBP sequences write one image per frame —\nhandy for further post work but much slower than video', "ja": '出力形式：MP4/MKV は動画ファイル。PNG/JPG/WEBP 連番は1フレーム1画像で、\n後工程向けですが動画より大幅に遅くなります'},
    '推理设备：GPU 走显卡（快几十倍，推荐）；CPU 走处理器（慢，\n仅显卡不支持时使用）': {"zh-TW": '推論裝置：GPU 走顯卡（快數十倍，推薦）；CPU 走處理器（慢，\n僅顯卡不支援時使用）', "en": 'Inference device: GPU uses the graphics card (tens of times faster, recommended); CPU uses the processor (slow — only when the GPU is unsupported)', "ja": '推論デバイス：GPU はグラフィックスカード（数十倍高速、推奨）。CPU はプロセッサ（低速、GPU 非対応時のみ）'},
    '分块大小：超分时把画面切成小方块逐块推理。\n自动 = 160（实测在本机 1080p 上最快，比 256 快约 17%）；\n显存吃紧或超大分辨率时可手动选 256 / 512': {"zh-TW": '分塊大小：超分時把畫面切成小方塊逐塊推論。\n自動 = 160（實測在本機 1080p 上最快，比 256 快約 17%）；\n顯存吃緊或超大解析度時可手動選 256 / 512', "en": 'Tile size: upscaling works on small blocks of the frame.\nAuto = 160 (fastest for 1080p on this machine, ~17% faster than 256);\npick 256/512 manually if VRAM is tight or the resolution is huge', "ja": 'タイルサイズ：超解像時に画面を小さなブロックに分けて推論します。\n自動 = 160（この環境の 1080p で最速、256 より約17%高速）。\nVRAM が厳しい場合や超高解像度では 256 / 512 を選択'},
    '内置加速内核：常驻 VapourSynth 运行时，模型只加载一次，\n连续处理多个视频无需反复初始化，大幅缩短启动时间': {"zh-TW": '內建加速內核：常駐 VapourSynth 執行環境，模型只載入一次，\n連續處理多部影片無需反覆初始化，大幅縮短啟動時間', "en": "Built-in accelerated core: keeps the VapourSynth runtime resident and loads models once,\nso consecutive videos don't re-initialise — start-up time drops sharply", "ja": '内蔵高速コア：VapourSynth ランタイムを常駐させ、モデルは一度だけ読み込みます。\n連続処理でも再初期化が不要で、起動時間が大幅に短縮されます'},
    '勾选（推荐）：先超分，缩到目标分辨率，最后再做补帧。\n超分只跑源帧（例如 24 帧/秒），补帧在目标分辨率上进行，实测快 3~9 倍。\n\n取消勾选：先把视频补帧到高帧率，再对每一帧超分（原顺序）。\n超分的帧数会被放大 5 倍，明显更慢。': {"zh-TW": '勾選（推薦）：先超分，縮到目標解析度，最後再做補幀。\n超分只跑來源幀（例如 24 幀/秒），補幀在目標解析度上進行，實測快 3~9 倍。\n\n取消勾選：先把影片補幀到高幀率，再對每一幀超分（原順序）。\n超分的幀數會被放大 5 倍，明顯更慢。', "en": 'Checked (recommended): upscale first, scale to the target resolution, then interpolate.\nOnly source frames go through upscaling (e.g. 24 fps) and interpolation runs at the target resolution — measured 3~9× faster.\n\nUnchecked: interpolate to the high frame rate first, then upscale every frame (original order).\nThat multiplies upscaled frames by 5 and is noticeably slower.', "ja": 'オン（推奨）：先に超解像して目標解像度に縮小し、最後に補間します。\n超解像は元フレームのみ（例 24fps）、補間は目標解像度で行うため実測 3~9 倍高速です。\n\nオフ：先に高フレームレートへ補間し、その全フレームを超解像（従来の順序）。\n超解像するフレームが5倍になり、明らかに遅くなります。'},
    '勾选：先把画面缩到「目标分辨率 ÷ 超分倍数」再超分。\n例：1080p 源、输出 1080p、2× 模型 → 先缩到 540p 再超分到 1080p。\n省掉「先放大到 4K 再缩回 1080p」的无效算力，超分环节实测快约 3 倍。\n\n代价：源画面会被先缩小一次，极细的纹理/噪点会被磨平一些，\n动漫线条影响很小，真人实拍细节优先的话建议不勾。': {"zh-TW": '勾選：先把畫面縮到「目標解析度 ÷ 超分倍數」再超分。\n例：1080p 來源、輸出 1080p、2× 模型 → 先縮到 540p 再超分到 1080p。\n省掉「先放大到 4K 再縮回 1080p」的無效算力，超分環節實測快約 3 倍。\n\n代價：來源畫面會被先縮小一次，極細的紋理/噪點會被磨平一些，\n動漫線條影響很小，真人實拍細節優先的話建議不勾。', "en": 'Checked: downscale to target ÷ upscale factor before upscaling.\ne.g. 1080p source, 1080p output, 2× model → downscale to 540p, then upscale to 1080p.\nThis skips the wasted "upscale to 4K then shrink back to 1080p" work — about 3× faster upscaling.\n\nCost: the source is downscaled once, so very fine texture/noise is smoothed a little.\nAnime lines are barely affected; for live-action detail, leave it unchecked.', "ja": 'オン：目標解像度 ÷ 超解像倍率まで縮小してから超解像します。\n例：1080p 元、1080p 出力、2× モデル → 540p に縮小してから 1080p へ超解像。\n「4K に拡大して 1080p に戻す」無駄を省き、超解像が実測約3倍高速になります。\n\n代償：元映像を一度縮小するため、細かなテクスチャ／ノイズはやや平滑化されます。\nアニメの線にはほぼ影響しません。実写の細部を優先するならオフ推奨。'},
    '勾选：超分+补帧拆成两段跑，第 1 段先落一个中间片（MKV）到\n「片子名_补帧中间片」目录里（勾了「先超分」则是 _超分中间片），\n方便对比画质或单独复用。代价是多一次编码+解码，整体大约慢一倍。\n\n不勾选：补帧和超分在同一条流水线里一次跑完，不产生中间文件（更快）。': {"zh-TW": '勾選：超分+補幀拆成兩段跑，第 1 段先落一個中間片（MKV）到\n「影片名_補幀中間片」目錄裡（勾了「先超分」則是 _超分中間片），\n方便對比畫質或單獨複用。代價是多一次編碼+解碼，整體大約慢一倍。\n\n不勾選：補幀和超分在同一條流水線裡一次跑完，不產生中間檔案（更快）。', "en": 'Checked: upscale and interpolation run as two passes; pass 1 writes an intermediate clip (MKV)\ninto "name_interp-clip" (or "name_upscale-clip" when "Upscale first" is on),\nso you can compare quality or reuse it. Cost: one extra encode+decode, roughly 2× slower.\n\nUnchecked: interpolation and upscaling complete in a single pipeline with no intermediate file (faster).', "ja": 'オン：超解像と補間を2段階に分け、1段目で中間ファイル（MKV）を\n「名前_補間中間」フォルダに書き出します（「先に超解像」オンの場合は _超解像中間）。\n画質比較や再利用ができます。代償としてエンコード＋デコードが1回増え、全体で約2倍遅くなります。\n\nオフ：補間と超解像を1本のパイプラインで完了し、中間ファイルを作りません（高速）。'},
    '帧流法：扫描相邻源帧，删除重复帧后重建时间轴，\n再按目标帧率插帧，避免把重复帧也拿去补帧造成伪影': {"zh-TW": '幀流法：掃描相鄰來源幀，刪除重複幀後重建時間軸，\n再按目標幀率插幀，避免把重複幀也拿去補幀造成偽影', "en": "Frame dedup: scan neighbouring source frames, drop duplicates and rebuild the timeline,\nthen interpolate to the target rate so duplicates don't create artefacts", "ja": 'フレーム重複除去：隣接フレームを走査して重複を削除し、タイムラインを再構築してから\n目標フレームレートへ補間します。重複フレームによるアーティファクトを防ぎます'},
    '切镜保护：检测镜头切换，在切镜处不插帧，避免转场时出现\n撕裂/重影；动漫和剪辑视频建议开启': {"zh-TW": '切鏡保護：偵測鏡頭切換，在切鏡處不插幀，避免轉場時出現\n撕裂/重影；動漫和剪輯影片建議開啟', "en": 'Scene protection: detect shot changes and skip interpolation there, avoiding tearing/ghosting on cuts;\nrecommended for anime and edited videos', "ja": 'シーン保護：カットチェンジを検出し、その箇所では補間しません。\nトランジションの破綻やゴーストを防ぎます。アニメや編集動画に推奨'},
    '硬件解码：用显卡解码源视频，减轻 CPU 负担、加快读取速度；\n个别特殊编码格式可能需关闭': {"zh-TW": '硬體解碼：用顯卡解碼來源影片，減輕 CPU 負擔、加快讀取速度；\n個別特殊編碼格式可能需關閉', "en": 'Hardware decode: decode the source on the GPU to ease CPU load and read faster;\nturn it off for a few unusual codecs', "ja": 'ハードウェアデコード：GPU で元動画をデコードし CPU 負荷を軽減、読み込みも高速化。\n一部の特殊なコーデックではオフにしてください'},
    '日志增速：降低日志刷新频率、精简非关键日志，减少界面线程开销，\n从而加快处理速度；同时启用超分 fp16 推理（约快 2~3 倍）': {"zh-TW": '日誌增速：降低日誌刷新頻率、精簡非關鍵日誌，減少介面執行緒開銷，\n從而加快處理速度；同時啟用超分 fp16 推論（約快 2~3 倍）', "en": 'Fast logging: refresh logs less often and drop non-critical lines to cut UI-thread overhead,\nwhich speeds processing up; also enables fp16 upscaling (about 2~3× faster)', "ja": '高速ログ：ログ更新頻度を下げ、重要でない行を削減して UI スレッド負荷を軽減し、\n処理を高速化します。同時に超解像の fp16 推論を有効化（約2~3倍高速）'},
    '用 NVIDIA TensorRT 跑超分，比默认的 ncnn 快约 2~4 倍。\n第一次处理某个模型 + 分辨率组合时要先构建引擎（几分钟），\n引擎会缓存复用，之后每次都秒开。\n\n要求：NVIDIA 显卡，且 vrt/plugins 内已放置 vstrt.dll 与 TensorRT 运行库。\n不满足条件时不生效，自动回退 ncnn，不影响正常处理。': {"zh-TW": '用 NVIDIA TensorRT 跑超分，比預設的 ncnn 快約 2~4 倍。\n第一次處理某個模型 + 解析度組合時要先建置引擎（幾分鐘），\n引擎會快取複用，之後每次都秒開。\n\n要求：NVIDIA 顯卡，且 vrt/plugins 內已放置 vstrt.dll 與 TensorRT 執行庫。\n不滿足條件時不生效，自動回退 ncnn，不影響正常處理。', "en": 'Run upscaling on NVIDIA TensorRT — about 2~4× faster than the default ncnn.\nThe first run of each model + resolution pair builds an engine (a few minutes);\nthe engine is cached and reused, so later runs start instantly.\n\nRequires an NVIDIA GPU plus vstrt.dll and the TensorRT runtime in vrt/plugins.\nIf unmet, this is ignored and ncnn is used — normal processing is unaffected.', "ja": '超解像を NVIDIA TensorRT で実行します（既定の ncnn より約2~4倍高速）。\nモデル＋解像度の組み合わせごとに初回はエンジン構築が必要（数分）。\n構築後はキャッシュされ、次回から即起動します。\n\n要件：NVIDIA GPU、および vrt/plugins に vstrt.dll と TensorRT ランタイム。\n満たさない場合は無効化され、自動的に ncnn へ戻ります（通常処理に影響なし）。'},
    '当前模式不做超分，TensorRT 用不上': {"zh-TW": '目前模式不做超分，TensorRT 用不上', "en": 'This mode does no upscaling, so TensorRT is not used', "ja": 'このモードでは超解像を行わないため、TensorRT は使いません'},
    '当前超分模型不是 ONNX 格式，TensorRT 只支持 ONNX；\n带「ncnn 内核」字样的模型不走 TensorRT，直接用 ncnn 内核即可': {"zh-TW": '目前超分模型不是 ONNX 格式，TensorRT 只支援 ONNX；\n帶「ncnn 內核」字樣的模型不走 TensorRT，直接用 ncnn 內核即可', "en": 'This upscaling model is not ONNX and TensorRT only supports ONNX;\nmodels marked "ncnn kernel" skip TensorRT — just use the ncnn kernel', "ja": 'この超解像モデルは ONNX ではないため TensorRT（ONNX 専用）は使えません。\n「ncnn カーネル」表記のモデルは TensorRT を通らないので ncnn のままで構いません'},
    '未检测到 NVIDIA 显卡，TensorRT 用不了（处理时会自动回退 ncnn 内核，\n画质一样，只是慢一些）': {"zh-TW": '未偵測到 NVIDIA 顯卡，TensorRT 用不了（處理時會自動回退 ncnn 內核，\n畫質一樣，只是慢一些）', "en": 'No NVIDIA GPU detected, so TensorRT cannot be used\n(processing falls back to the ncnn kernel — same quality, just slower)', "ja": 'NVIDIA GPU が見つからないため TensorRT は使用できません\n（処理は自動的に ncnn カーネルへ戻ります。画質は同じで、少し遅くなるだけです）'},
    '缺少 TensorRT 运行库：vrt/plugins 内需要 vstrt.dll，\n以及 vsmlrt-cuda 里的 TensorRT DLL（含 trtexec.exe）': {"zh-TW": '缺少 TensorRT 執行庫：vrt/plugins 內需要 vstrt.dll，\n以及 vsmlrt-cuda 裡的 TensorRT DLL（含 trtexec.exe）', "en": 'TensorRT runtime missing: vrt/plugins needs vstrt.dll\nplus the TensorRT DLLs in vsmlrt-cuda (including trtexec.exe)', "ja": 'TensorRT ランタイムが不足しています：vrt/plugins に vstrt.dll、\nおよび vsmlrt-cuda 内の TensorRT DLL（trtexec.exe を含む）が必要です'},
    '缺少当前显卡架构的 TensorRT 构建资源（nvinfer_builder_resource_smXX_10.dll）；\n从 TensorRT 10.16 官方包的 bin 目录拷贝对应架构那份进来即可，\n暂不补也能用，勾选后会回退 ncnn 内核': {"zh-TW": '缺少目前顯卡架構的 TensorRT 建置資源（nvinfer_builder_resource_smXX_10.dll）；\n從 TensorRT 10.16 官方包的 bin 目錄複製對應架構那份進來即可，\n暫不補也能用，勾選後會回退 ncnn 內核', "en": 'TensorRT build resources for this GPU architecture are missing (nvinfer_builder_resource_smXX_10.dll);\ncopy the matching file from the bin folder of the TensorRT 10.16 package.\nIt still works without it — ticking will fall back to the ncnn kernel', "ja": 'この GPU アーキテクチャ用の TensorRT ビルドリソースがありません（nvinfer_builder_resource_smXX_10.dll）。\nTensorRT 10.16 公式パッケージの bin から該当アーキテクチャのファイルをコピーしてください。\n未補填でも動作し、オンにすると ncnn カーネルへ戻ります'},
    '帧流法阈值：相邻帧差低于该值按重复帧丢弃；填 0 等于关闭。\n数值越大判定越宽松、删得越多；默认 0.25 适合大多数素材': {"zh-TW": '幀流法閾值：相鄰幀差低於該值按重複幀丟棄；填 0 等於關閉。\n數值越大判定越寬鬆、刪得越多；預設 0.25 適合大多數素材', "en": 'Dedup threshold: neighbour-frame differences below this are treated as duplicates; 0 disables it.\nHigher values are more lenient and drop more frames; 0.25 suits most footage', "ja": '重複除去しきい値：隣接フレーム差がこの値未満なら重複として削除。0 で無効。\n値が大きいほど判定が緩く、より多く削除されます。既定 0.25 は多くの素材に適します'},
    '作者独立开发、全部功能免费；如果它帮到了你，可以自愿支持一下': {"zh-TW": '作者獨立開發、全部功能免費；如果它幫到了你，可以自願支持一下', "en": "Independently built, every feature free; if it helps you, you're welcome to support it", "ja": '個人開発・全機能無料。役に立ったら任意で支援できます'},
    '开启后：拖着文件经过程序窗口时临时暂停视频壁纸，把显卡与主线程让给拖放响应，\n拖动手感更跟手；松手或拖走立即恢复播放。\n关闭后：壁纸全程连续播放（默认）。': {"zh-TW": '開啟後：拖著檔案經過程式視窗時暫時暫停影片壁紙，把顯卡與主執行緒讓給拖放回應，\n拖動手感更跟手；放手或拖走立即恢復播放。\n關閉後：壁紙全程連續播放（預設）。', "en": 'On: pause the video wallpaper while a file is dragged over the window, freeing the GPU and main thread for drag response,\nso dragging feels tighter; playback resumes on release or drag-out.\nOff: the wallpaper plays continuously (default).', "ja": 'オン：ファイルをウィンドウ上にドラッグしている間だけ動画壁紙を一時停止し、\nGPU とメインスレッドをドラッグ応答に回します。離すか外に出ると再生を再開。\nオフ：壁紙は常に連続再生（既定）。'},
}


def tr(text):
    """把简体中文原文翻译为当前语言；找不到译文时原样返回。"""
    if not text or _CURRENT == "zh-CN":
        return text
    entry = _T.get(text)
    if not entry:
        return text
    return entry.get(_CURRENT, text)


# 反向索引：任意语言的译文 -> 简体中文 key（用于切换语言时还原）
_REVERSE = {}
for _key, _m in _T.items():
    _REVERSE[_key] = _key
    for _v in _m.values():
        _REVERSE[_v] = _key


def to_key(text):
    """把当前显示的任意语言文字还原成简体中文 key；非译文原样返回。"""
    if not text:
        return text
    return _REVERSE.get(text, text)


def kv(key, default=""):
    """按标识符取长文本译文（关于页的免责声明、许可说明等）。

    这类文本整段做 key 容易因一个标点对不上而失败，改用 "about.disclaimer.1"
    这样的稳定标识；简体中文或查不到时返回代码里的原文 default。
    """
    if not key:
        return default
    entry = _T.get(key)
    if not entry or _CURRENT == "zh-CN":
        return default or key
    return entry.get(_CURRENT, default or key)


def translate(text):
    """切换语言用：先还原成中文 key，再翻译成当前语言。"""
    return tr(to_key(text))


# ------------------------------------------------------------------ Qt 内置对话框
# QColorDialog / QFontDialog / QMessageBox / QFileDialog 等由 Qt 自己绘制的对话框，
# 内部文字（"基本颜色""自定义颜色""确定""取消"等）来自 Qt 官方语言包 qtbase_*.qm，
# 不在上面的翻译表里。切换语言时同步装载对应的语言包即可。
_QT_LOCALE = {"zh-CN": "zh_CN", "zh-TW": "zh_TW", "en": "en", "ja": "ja"}

_qt_translator = None


def install_qt_translator(app=None):
    """装载当前语言对应的 Qt 官方语言包，让内置对话框的文字跟随界面语言。"""
    global _qt_translator
    try:
        import os
        import PySide6
        from PySide6.QtCore import QTranslator, QCoreApplication

        if app is None:
            app = QCoreApplication.instance()
        if app is None:
            return False
        if _qt_translator is not None:
            try:
                app.removeTranslator(_qt_translator)
            except Exception:
                pass
            _qt_translator = None
        loc = _QT_LOCALE.get(_CURRENT, "zh_CN")
        tdir = os.path.join(os.path.dirname(PySide6.__file__), "translations")
        t = QTranslator()
        if t.load(os.path.join(tdir, "qtbase_%s.qm" % loc)):
            app.installTranslator(t)
            _qt_translator = t
            return True
    except Exception:
        pass
    return False
