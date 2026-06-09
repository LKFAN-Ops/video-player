# 播放器 · BofangQi

> 一个带「实时中俄字幕」的本地视频播放器 —— 离线、免代理、开箱即用。
> A local video player with **real-time Chinese / Russian subtitles** — offline, no proxy, ready to use.

---

## 缘起 / Why this exists

最初做这个，纯粹是为了我自己和女朋友。我们平时一起看视频，常常碰到**没有中文或俄语字幕**的片源，看得很费劲。市面上的工具要么要联网开代理、要么收费、要么把视频上传到别人服务器，都不太合适。于是干脆自己写了这个播放器：**在本地把语音识别成文字、再翻译成中文/俄文字幕**，全程不需要代理，也不会把视频传到任何地方。

目前最大的缺点是**识别和翻译的精度还不够高**（CPU + 轻量模型，为了能实时跑做了取舍）。后续我会不断优化，但更新**可能不定期**——这是个业余时间维护的小项目，随缘更新，敬请见谅 🙂

> I originally built this just for me and my girlfriend. We watch videos together a lot and kept running into sources with **no Chinese or Russian subtitles**. Existing tools either needed a VPN/proxy, cost money, or uploaded your video to someone else's server. So I wrote my own player that **transcribes the audio and translates it into Chinese/Russian subtitles entirely on your own machine** — no proxy, nothing uploaded.
>
> The main weakness right now is that **recognition and translation accuracy is still not great** (CPU + lightweight models, traded off to keep it real-time). I'll keep improving it, but updates may be **irregular** — it's a small side project maintained in spare time. Thanks for your understanding 🙂

---

## ✨ 功能 / Features

- 🎬 本地视频播放（mp4 / mkv / mov / webm / avi / ts 等）/ Local video playback
- 🗣️ **实时语音转字幕**：基于 [faster-whisper](https://github.com/SYSTRAN/faster-whisper)，边播边识别 / Real-time speech-to-subtitle
- 🌏 **实时翻译**：英 ⇄ 中 ⇄ 俄，基于 Meta [M2M100](https://huggingface.co/facebook/m2m100_418M) / Real-time translation (EN ⇄ ZH ⇄ RU)
- 📂 加载外挂字幕（.srt / .vtt）/ Load external subtitles
- 💾 导出带硬字幕的视频（FFmpeg 内嵌，无需另装）/ Export video with burned-in subtitles
- 🚫 **免代理、可离线**：使用 [hf-mirror.com](https://hf-mirror.com) 国内镜像下载模型，运行时强制直连 / No proxy, offline-capable

## 🧩 技术栈 / Tech stack

| 部分 / Part | 用的什么 / What |
| --- | --- |
| 界面 / UI | Electron |
| 语音识别 / ASR | faster-whisper（tiny / base / small / medium）|
| 机器翻译 / MT | M2M100 418M（默认实时）/ 1.2B（可选高精度）+ Helsinki-NLP MarianMT 兜底 |
| 音视频 / Media | FFmpeg（`ffmpeg-static` 内置）|
| 模型下载 / Models | HuggingFace + hf-mirror 镜像 |

---

## 🚀 安装与运行 / Install & Run

### 1. 前置环境 / Prerequisites

- **Node.js** 18+（用于 Electron）
- **Python** 3.8+（用于识别与翻译服务）
- FFmpeg 已通过 `ffmpeg-static` 内置，**无需单独安装** / bundled, no separate install needed

### 2. 安装依赖 / Install dependencies

```bash
# 前端依赖 / frontend
npm install

# Python 依赖 / Python
pip install -r requirements.txt
```

### 3. 下载模型 / Download models（首次必做 / required on first run）

模型不随仓库分发（太大，约数 GB）。运行下面的脚本，会自动**通过国内镜像下载并转换为 safetensors**，全程免代理：

Models are not shipped in the repo (several GB). The script below downloads them **via the China mirror and converts them to safetensors**, no proxy required:

```bash
python scripts/download_models.py
```

> 默认下载实时翻译模型 `m2m100_418M` + `faster-whisper-small/medium`，并可选 `m2m100_1.2B`。
> Downloads `m2m100_418M` (real-time) + `faster-whisper-small/medium`, optionally `m2m100_1.2B`.

### 4. 启动 / Start

```bash
npm start
```

Windows 下也可直接双击 `start.bat`。/ On Windows you can also double-click `start.bat`.

---

## 🎛️ 使用 / Usage

1. 打开应用 → **打开视频** 选择本地文件 / Open the app → **Open Video**
2. 勾选 **实时字幕**，选择目标语言（中 / 俄 / 英）/ Enable **Live subtitles**, pick target language
3. 想要离线高质量字幕，可先**生成整片字幕**再播放 / For higher quality, **generate full subtitles** first
4. 也可**加载外挂字幕**或**导出带字幕的视频** / Or **load external subtitles** / **export burned-in video**

### 精度 / 速度切换 / Quality vs. speed

| 模式 / Mode | 翻译模型 / MT model | 说明 / Notes |
| --- | --- | --- |
| 默认 / Default | m2m100 **418M** | CPU 上约 0.2~0.5 秒/句，适合实时 / fast, real-time |
| 高精度 / High | m2m100 **1.2B** | 设置环境变量 `MODEL_PRECISION=ultra`；质量更高但 CPU 较慢、约 6.5GB 内存 / set `MODEL_PRECISION=ultra`; better but slower |

---

## ⚠️ 已知不足 / Known limitations

- 识别 / 翻译精度有限，尤其是口音、专有名词、口语化内容 / Accuracy is limited, especially with accents, proper nouns, and casual speech
- 纯 CPU 推理，长视频整片转写较慢 / CPU-only inference; full-video transcription can be slow
- 目前主要面向 **英 / 中 / 俄** 三语 / Currently focused on **EN / ZH / RU**
- 更新不定期 / Updates are irregular

## 🗺️ 后续计划 / Roadmap（随缘 / when time allows）

- [ ] 提升翻译精度（更好的模型 / 上下文 / 术语表）/ Better translation quality
- [ ] 可选 GPU 加速 / Optional GPU acceleration
- [ ] 更多语言 / More languages
- [ ] 字幕样式与时间轴微调 / Subtitle styling & timing tweaks

## 🙏 致谢 / Acknowledgements

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) · [Meta M2M100](https://huggingface.co/facebook/m2m100_418M) · [Helsinki-NLP OPUS-MT](https://huggingface.co/Helsinki-NLP) · [hf-mirror.com](https://hf-mirror.com) · [Electron](https://www.electronjs.org/) · [FFmpeg](https://ffmpeg.org/)

## 📄 许可 / License

MIT —— 自由使用，但不提供任何担保。/ Free to use, provided "as is" without warranty.

---

*Made with ❤️ for movie nights. / 为了能和家人朋友安心看片而做。*
