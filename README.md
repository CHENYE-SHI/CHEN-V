# CHEN-V

**视频补帧 + 超分增强工具**（Windows · 本地运行 · 免费）

CHEN-V 是一款基于 RIFE ncnn 补帧 + Real-CUGAN / Real-ESRGAN 超分的本地视频画质增强工具，支持视频 / 图片 / 批量队列 / 图片序列输出，内置 ncnn（Vulkan）与 TensorRT 加速内核。

## 功能特性

- **补帧**：RIFE ncnn，把低帧率视频补到 60/120fps；可选 **GMFSS Fortuna Union**（光流补帧，动漫/线条画质更好，速度较慢）
- **超分**：Real-CUGAN / Real-ESRGAN（AnimeJaNai 等），最高 4K
- **一键「超分并补帧」**：单次流水线完成两步
- **批量队列**：多文件排队处理，进度实时显示
- **多格式输出**：MP4 / MKV / MOV / GIF / WEBP / PNG 序列 / JPG 序列
- **硬件加速**：
  - NVIDIA 显卡：TensorRT 内核（需驱动 ≥ 580）
  - AMD / Intel：ncnn Vulkan 内核
  - 导出编码支持 NVENC / AMF / QSV 硬件编码
- **多语言界面**：简体中文 / 繁体中文 / English / 日本語

## 下载与安装

从 [Releases](https://github.com/CHENYE-SHI/CHEN-V/releases) 页面下载 `CHEN-V_Setup_v1.02.exe`，双击安装即可。安装器把文件直接释放到你选的目录，不经过系统临时目录，也不额外占用 C 盘。

> 首次运行时若使用 TensorRT，需要为本机 GPU 构建引擎（每个模型 + 分辨率组合一次，约几分钟），后续即时加载。

备用下载渠道见 [个人仓库页](https://chen-74900.app.workbuddy.host)，提供夸克网盘与百度网盘。

### 补充包：GMFSS Fortuna Union

GMFSS 走 PyTorch 推理，光运行时就有 4.2 GB，所以没跟主包放在一起。需要的话单独下载 `CHEN-V_GMFSS_Setup_v1.02.exe`（约 2.7 GB）：

1. 先装好 CHEN-V 主程序，再双击补充包，点「选择目录」选中你装 CHEN-V 的那个文件夹
2. 安装器会校验目录里有没有 `CHEN-V.exe` 和 `app\gui_main.py`，选错直接拦下；装完重启 CHEN-V，「补帧模型」下拉框里就会出现 **GMFSS Fortuna Union**

补充包只往已有目录里合并文件，不写注册表、不建快捷方式、不动你的设置。

速度参考（RTX 5060 Laptop，1080p fp16）：每帧约 1.0 秒，显存约 2.8GB。
要求 NVIDIA 显卡 + 驱动支持 CUDA 12.8（50 系需要）；不装该组件不影响 RIFE 补帧。

## 系统要求

- Windows 10 / 11（64 位）
- 显卡：NVIDIA（TensorRT 加速）/ AMD / Intel 核显（ncnn Vulkan）
- 显存建议 4 GB 以上（超分 4K 建议 8 GB）

## 许可

**本软件为闭源软件，保留所有权利（All rights reserved）。**

- 允许免费下载、安装并用于个人或商业项目
- 允许在保留原始出处的前提下转载下载链接
- **禁止**反编译、反汇编、逆向工程或提取其中的代码与资源
- **禁止**二次打包、改名后重新发布，或用于收费转卖
- 源代码不对外公开

内嵌的第三方组件（Real-ESRGAN、Real-CUGAN、RIFE ncnn、GMFSS Fortuna（98mxr，MIT）、FFmpeg、VapourSynth、TensorRT 等）各自遵循其原始许可，著作权归原作者所有。

## 更新与公告

- 程序内「官网更新」页可一键检查新版本、查看作者公告
- 更新源：GitHub Releases（版本号）+ 仓库根目录 `announce.json`（公告）

## 反馈与交流

- GitHub Issues：[提交问题](https://github.com/CHENYE-SHI/CHEN-V/issues)
- 哔哩哔哩主页：[作者主页](https://b23.tv/X2FYRsA)
- QQ 交流群：1130651819（程序内「加入聊群」可扫码）

## 致谢

感谢以下开源项目，本项目的超分与补帧能力建立在这些工作之上（模型与算法版权归各原作者所有）：

- [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN)（Xintao Wang 等）
- [Real-CUGAN](https://github.com/bilibili/ailab)（bilibili 人工智能实验室）
- [RIFE](https://github.com/hzwer/ECCV2022-RIFE) / [rife-ncnn-vulkan](https://github.com/nihui/rife-ncnn-vulkan)
- [ncnn](https://github.com/Tencent/ncnn)（腾讯）
- [FFmpeg](https://ffmpeg.org/)
- [VapourSynth](https://www.vapoursynth.com/) / [vs-mlrt](https://github.com/AmusementClub/vs-mlrt)
- [NVIDIA TensorRT](https://developer.nvidia.com/tensorrt)
