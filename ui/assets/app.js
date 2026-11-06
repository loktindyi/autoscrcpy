/* ==========================================================================
   AutoScrcpy front-end
   No build step, no framework. The backend serves this file and talks JSON
   over /ws. All scrcpy arguments are built here; the backend only executes.
   ========================================================================== */

(() => {
  "use strict";

  const ACCENTS = {
    teal: {
      label: "青碧",
      dark: ["#3ddcc4", "#58a8ff"],
      light: ["#2f756e", "#3b63b8"],
    },
    blue: {
      label: "海蓝",
      dark: ["#5da8ff", "#7cd6ff"],
      light: ["#3457c4", "#226b96"],
    },
    indigo: {
      label: "靛蓝",
      dark: ["#8b9dff", "#b48bff"],
      light: ["#5b55cc", "#6f3bb0"],
    },
    violet: {
      label: "紫罗兰",
      dark: ["#c58bff", "#ff8bc8"],
      light: ["#7c3fbb", "#a83a5f"],
    },
    rose: {
      label: "玫瑰",
      dark: ["#ff7fa8", "#ffa27a"],
      light: ["#b23a63", "#a8552a"],
    },
    amber: {
      label: "琥珀",
      dark: ["#ffc45e", "#ff9d5c"],
      light: ["#a85f26", "#a8552a"],
    },
    lime: {
      label: "青柠",
      dark: ["#a8e26a", "#5fd6a0"],
      light: ["#5b7a2a", "#2f756e"],
    },
    slate: {
      label: "石墨",
      dark: ["#bec9dc", "#93a7c8"],
      light: ["#55606f", "#46505f"],
    },
  };

  // Temporary experiment: light mode reuses the dark-mode accent colours so
  // their readability on white can be judged.  Set this to false and restore
  // the light accent rules in app.css to bring the darker variants back.
  const SHARED_ACCENT_PALETTE = true;

  const APPEARANCES = {
    light: "浅色",
    dark: "深色",
    system: "跟随系统",
  };

  const LEGACY_THEME_ACCENTS = {
    midnight: "teal",
    ember: "amber",
    paper: "slate",
    terminal: "lime",
  };

  const STORAGE_KEY = "autoscrcpy.settings.v1";
  const MAX_LOG_LINES = 2500;

  const T = (id, title, arg, short, detail, defaultValue = false, extra = {}) => ({
    id,
    type: "toggle",
    title,
    arg,
    short,
    detail,
    default: defaultValue,
    ...extra,
  });

  const S = (id, title, flag, short, detail, choices, defaultValue = "", extra = {}) => ({
    id,
    type: "select",
    title,
    flag,
    short,
    detail,
    choices,
    default: defaultValue,
    ...extra,
  });

  const X = (id, title, flag, short, detail, placeholder, extra = {}) => ({
    id,
    type: "text",
    title,
    flag,
    short,
    detail,
    placeholder,
    default: "",
    ...extra,
  });

  const N = (id, title, flag, short, detail, unit = "", extra = {}) => ({
    id,
    type: "number",
    title,
    flag,
    short,
    detail,
    unit,
    default: "",
    ...extra,
  });

  const C = (
    id,
    title,
    flag,
    short,
    detail,
    presets,
    defaultValue,
    suffix = "",
    extra = {}
  ) => ({
    id,
    type: "combo",
    title,
    flag,
    short,
    detail,
    presets,
    default: defaultValue,
    suffix,
    ...extra,
  });

  const AUDIO = { option: "noAudio", equals: false };
  const CAMERA = { option: "videoSource", equals: "camera" };
  const ANDROID_NAMES = {
    21: "5.0",
    22: "5.1",
    23: "6.0",
    24: "7.0",
    25: "7.1",
    26: "8.0",
    27: "8.1",
    28: "9",
    29: "10",
    30: "11",
    31: "12",
    32: "12L",
    33: "13",
    34: "14",
    35: "15",
  };

  const GROUPS = [
    {
      id: "video",
      title: "画面",
      icon: "i-monitor",
      note: "清晰度、帧率、码率与窗口",
      options: [
        C(
          "maxSize",
          "分辨率上限",
          "--max-size",
          "限制画面长边像素，可选项或直接输入数值",
          "对应 --max-size。官方默认 0（原始分辨率），选择默认值不会附加参数。可直接输入像素值，例如 1440；scrcpy 会按屏幕比例缩放。",
          [
            { value: "0", label: "原始分辨率（默认）" },
            { value: "3840", label: "3840 px（4K）" },
            { value: "2560", label: "2560 px" },
            { value: "2160", label: "2160 px" },
            { value: "1920", label: "1920 px" },
            { value: "1600", label: "1600 px" },
            { value: "1440", label: "1440 px" },
            { value: "1280", label: "1280 px（推荐）" },
            { value: "1080", label: "1080 px" },
            { value: "1024", label: "1024 px" },
            { value: "900", label: "900 px" },
            { value: "800", label: "800 px" },
            { value: "720", label: "720 px" },
            { value: "640", label: "640 px" },
          ],
          "0",
          "",
          { comboKind: "size", placeholder: "例如 1440" }
        ),
        C(
          "maxFps",
          "帧率上限",
          "--max-fps",
          "限帧，不选则由 scrcpy 不限制",
          "对应 --max-fps。官方不指定时为不限制，选择「不限」不会附加参数。预设为不限、30、60、90、120 fps。",
          [
            { value: "0", label: "不限" },
            { value: "30", label: "30 fps" },
            { value: "60", label: "60 fps" },
            { value: "90", label: "90 fps" },
            { value: "120", label: "120 fps" },
          ],
          "0",
          "",
          {
            comboKind: "fps",
            quick: true,
            quickPresets: [
              { value: "0", label: "不限" },
              { value: "30", label: "30" },
              { value: "60", label: "60" },
              { value: "90", label: "90" },
              { value: "120", label: "120" },
            ],
          }
        ),
        C(
          "bitRate",
          "视频码率",
          "--video-bit-rate",
          "输入数字自动补全；默认 8M",
          "对应 --video-bit-rate（简写 -b）。官方默认 8M，选择或输入 8M 都不会附加参数。可以直接输入数字，程序会自动补上 M，例如输入 12 得到 12M；也支持 K 后缀。",
          [
            { value: "1M", label: "1 Mbps" },
            { value: "2M", label: "2 Mbps" },
            { value: "4M", label: "4 Mbps" },
            { value: "6M", label: "6 Mbps" },
            { value: "8M", label: "8 Mbps（默认）" },
            { value: "12M", label: "12 Mbps" },
            { value: "16M", label: "16 Mbps" },
            { value: "24M", label: "24 Mbps" },
            { value: "32M", label: "32 Mbps" },
            { value: "48M", label: "48 Mbps" },
            { value: "64M", label: "64 Mbps" },
          ],
          "8M",
          "M",
          { comboKind: "bitrate", placeholder: "输入 12 自动补为 12M" }
        ),
        S(
          "videoCodec",
          "视频编码",
          "--video-codec",
          "H.264 兼容性最好，H.265 更省带宽",
          "对应 --video-codec。官方默认 H.264，选择默认值不会附加参数。H.265 通常更省带宽，AV1/VP8/VP9 需要设备有对应编码器。",
          [
            { value: "h264", label: "H.264（默认）", arg: null },
            { value: "h265", label: "H.265 / HEVC" },
            { value: "av1", label: "AV1" },
            { value: "vp8", label: "VP8" },
            { value: "vp9", label: "VP9" },
          ],
          "h264"
        ),
        S(
          "hwdec",
          "硬件解码（电脑）",
          "--hwdec",
          "默认优先显卡解码，失败时回退软件解码",
          "对应 --hwdec，scrcpy 5.0 起新增。默认自动：优先使用可用的硬件解码器，失败时回退软件解码；「软件解码」强制关闭硬件解码；D3D11VA 强制使用 Windows 的 D3D11VA 硬解，显卡或驱动不支持时会直接启动失败（不会回退），不确定时请用默认的自动。硬件解码只影响电脑端播放，必须有视频播放，所以「无窗口运行」时不可用。Windows 上播放 H.265 时建议使用 scrcpy 5.0.1 或更高版本。",
          [
            { value: "", label: "自动（默认）" },
            { value: "disabled", label: "软件解码" },
            { value: "d3d11va", label: "D3D11VA" },
          ],
          ""
        ),
        S(
          "orientation",
          "整体方向（预览+录制）",
          "--orientation",
          "0/90/180/270 为顺时针角度，同时作用于预览和录制",
          "对应 --orientation。它等价于同时设置 --display-orientation 和 --record-orientation。数值表示顺时针旋转角度，只支持 0/90/180/270；录制方向不支持翻转，所以这里不提供 flip。若同时设置了「仅预览方向」，以本项为准。",
          [
            { value: "0", label: "0°（默认）", arg: null },
            { value: "90", label: "90°" },
            { value: "180", label: "180°" },
            { value: "270", label: "270°" },
          ],
          "0"
        ),
        S(
          "displayOrientation",
          "仅预览方向",
          "--display-orientation",
          "只改变电脑上的预览，角度为顺时针，不影响录制文件",
          "对应 --display-orientation。它只作用于 scrcpy 窗口的显示，不会改变录制内容。官方默认 0°，选择默认值不会附加参数。数值表示顺时针旋转角度；flip 前缀表示先水平翻转再旋转。如果设置了「整体方向」，本项会被覆盖。",
          [
            { value: "0", label: "0°（默认）", arg: null },
            { value: "90", label: "90°" },
            { value: "180", label: "180°" },
            { value: "270", label: "270°" },
            { value: "flip0", label: "水平翻转" },
            { value: "flip90", label: "水平翻转 + 90°" },
            { value: "flip180", label: "水平翻转 + 180°" },
            { value: "flip270", label: "水平翻转 + 270°" },
          ],
          "0"
        ),
        S(
          "captureOrientation",
          "采集方向（设备侧）",
          "--capture-orientation",
          "设备端顺时针变换，预览和录制都会受影响",
          "对应 --capture-orientation。官方默认 0°，选择默认值不会附加参数。数值表示顺时针旋转角度。变换发生在采集编码前，所以预览和录制文件都会包含该方向。flip 前缀表示先水平翻转再旋转；flip180 = 水平翻转 + 180°，常用来把后摄画面调成镜子。它可以和「整体方向」组合使用。",
          [
            { value: "0", label: "0°（默认）", arg: null },
            { value: "90", label: "90°" },
            { value: "180", label: "180°" },
            { value: "270", label: "270°" },
            { value: "flip0", label: "水平翻转" },
            { value: "flip90", label: "水平翻转 + 90°" },
            { value: "flip180", label: "水平翻转 + 180°" },
            { value: "flip270", label: "水平翻转 + 270°" },
          ],
          "0"
        ),
        T(
          "fullscreen",
          "全屏启动",
          "--fullscreen",
          "启动后直接占满整个屏幕",
          "对应 --fullscreen（简写 -f）。适合专注查看或演示，按 scrcpy 的快捷键（默认 Alt+F 或 F11）可退出全屏。"
        ),
        T(
          "alwaysOnTop",
          "窗口置顶",
          "--always-on-top",
          "让镜像窗口始终保持在其他窗口上方",
          "对应 --always-on-top。适合边看手机边操作电脑，但可能挡住其他窗口。"
        ),
        T(
          "borderless",
          "无边框窗口",
          "--window-borderless",
          "去掉窗口标题栏和边框，观感更干净",
          "对应 --window-borderless。窗口仍然可以拖动和缩放，只是不显示系统边框。"
        ),
      ],
    },
    {
      id: "behavior",
      title: "设备行为",
      icon: "i-device",
      note: "唤醒、熄屏与系统状态",
      options: [
        T(
          "stayAwake",
          "保持设备唤醒",
          "--stay-awake",
          "镜像期间阻止设备自动熄屏",
          "对应 --stay-awake（简写 -w）。通过 USB 或无线连接调试时，让设备在 scrcpy 运行期间不自动锁屏，退出后会恢复原设置。scrcpy 默认不开启。"
        ),
        T(
          "turnScreenOff",
          "关闭设备屏幕",
          "--turn-screen-off",
          "设备屏幕熄灭，但电脑上的镜像继续显示",
          "对应 --turn-screen-off（简写 -S）。启动时立即熄灭设备物理屏幕以省电，镜像画面不受影响。点击或按键可以让屏幕重新亮起。"
        ),
        T(
          "showTouches",
          "显示触摸位置",
          "--show-touches",
          "在设备画面上显示触摸点",
          "对应 --show-touches（简写 -t）。只显示设备上的真实触摸，不显示鼠标点击。适合演示或录制操作。"
        ),
        T(
          "powerOffOnClose",
          "退出时熄屏",
          "--power-off-on-close",
          "关闭 scrcpy 时顺便关闭设备屏幕",
          "对应 --power-off-on-close。适合希望镜像结束就立即锁屏/熄屏的场景。"
        ),
      ],
    },
    {
      id: "audio",
      title: "声音",
      icon: "i-volume",
      note: "声音转发、音源与编码",
      options: [
        T(
          "noAudio",
          "静音镜像",
          "--no-audio",
          "不把设备声音转发到电脑",
          "对应 --no-audio。勾选后 scrcpy 完全不采集设备音频，可减少带宽和兼容性问题。Android 11 以下没有音频转发能力，scrcpy 会自动跳过音频。",
          false
        ),
        S(
          "audioSource",
          "声音来源",
          "--audio-source",
          "选择输出、播放或麦克风",
          "对应 --audio-source。默认转发设备整体输出；playback 捕获应用播放的声音（scrcpy 5.0 起会包含所有音频 usage），需要 Android 13+；mic 采集设备麦克风，需要 Android 11+。",
          [
            { value: "output", label: "设备输出（默认）", arg: null },
            { value: "playback", label: "应用播放", minSdk: 33 },
            { value: "mic", label: "设备麦克风", minSdk: 30 },
          ],
          "output",
          { minSdk: 30, requires: AUDIO }
        ),
        S(
          "audioCodec",
          "音频编码",
          "--audio-codec",
          "Opus 延迟低，AAC 兼容性好",
          "对应 --audio-codec。官方默认 Opus，选择默认值不会附加参数。不同编码器对设备和录制容器的支持不同。",
          [
            { value: "opus", label: "Opus（默认）", arg: null },
            { value: "aac", label: "AAC" },
            { value: "flac", label: "FLAC（无损）" },
            { value: "raw", label: "RAW" },
          ],
          "opus",
          { minSdk: 30, requires: AUDIO }
        ),
        C(
          "audioBitRate",
          "音频码率",
          "--audio-bit-rate",
          "输入 96 会自动变成 96K；默认 128K 不附加参数",
          "对应 --audio-bit-rate。官方默认 128K，选择或输入 128K 都不会附加参数。输入纯数字会自动补 K，例如输入 96 得到 96K。",
          [
            { value: "32K", label: "32 Kbps" },
            { value: "48K", label: "48 Kbps" },
            { value: "64K", label: "64 Kbps" },
            { value: "96K", label: "96 Kbps" },
            { value: "128K", label: "128 Kbps（默认）" },
            { value: "160K", label: "160 Kbps" },
            { value: "192K", label: "192 Kbps" },
            { value: "256K", label: "256 Kbps" },
            { value: "320K", label: "320 Kbps" },
          ],
          "128K",
          "K",
          {
            comboKind: "bitrate",
            placeholder: "输入 96 自动补为 96K",
            minSdk: 30,
            requires: AUDIO,
          }
        ),
        T(
          "audioDup",
          "设备同时外放",
          "--audio-dup",
          "电脑播放声音时，设备也继续播放",
          "对应 --audio-dup。只在声音来源选择「应用播放」时有效，适合一边录音一边让设备继续出声；这个捕获方式需要 Android 13+。",
          false,
          { minSdk: 33, requires: { option: "audioSource", equals: "playback" } }
        ),
        T(
          "requireAudio",
          "无声音则失败",
          "--require-audio",
          "音频不可用时让 scrcpy 直接报错退出",
          "对应 --require-audio。默认情况下音频失败仍会继续镜像画面；勾选后会严格要求音频成功。",
          false,
          { minSdk: 30, requires: AUDIO }
        ),
        T(
          "noAudioPlayback",
          "仅转发不播放",
          "--no-audio-playback",
          "保留音频数据但不从电脑扬声器播放",
          "对应 --no-audio-playback。适合录制时不想被电脑声音打扰，同时仍保留声音轨。",
          false,
          { minSdk: 30, requires: AUDIO }
        ),
      ],
    },
    {
      id: "camera",
      title: "摄像头",
      icon: "i-camera",
      note: "把设备摄像头当作视频源",
      options: [
        S(
          "videoSource",
          "视频来源",
          "--video-source",
          "镜像屏幕，或采集设备摄像头",
          "对应 --video-source。默认显示屏幕；选择摄像头后传 --video-source=camera。摄像头采集需要 Android 12 及以上。",
          [
            { value: "display", label: "设备屏幕（默认）", arg: null },
            {
              value: "camera",
              label: "设备摄像头",
              arg: "--video-source=camera",
              minSdk: 31,
            },
          ],
          "display"
        ),
        S(
          "cameraFacing",
          "使用哪颗摄像头",
          "--camera-facing",
          "前置、后置或外接摄像头",
          "对应 --camera-facing。留空让 scrcpy 自动选择；外接摄像头不一定存在。",
          [
            { value: "", label: "自动（默认）" },
            { value: "front", label: "前置" },
            { value: "back", label: "后置" },
            { value: "external", label: "外接" },
          ],
          "",
          { minSdk: 31, requires: CAMERA }
        ),
        C(
          "cameraSize",
          "采集尺寸",
          "--camera-size",
          "指定摄像头画面尺寸，可选项或直接输入",
          "对应 --camera-size。留空使用设备默认值。可选择常见尺寸或直接输入，例如 1920x1080。并非所有尺寸都被摄像头支持，可先用 scrcpy --list-camera-sizes 查看。",
          [
            { value: "640x480", label: "640×480" },
            { value: "1280x720", label: "1280×720" },
            { value: "1920x1080", label: "1920×1080" },
            { value: "2560x1440", label: "2560×1440" },
            { value: "3840x2160", label: "3840×2160" },
            { value: "4096x2160", label: "4096×2160" },
          ],
          "",
          "",
          {
            comboKind: "dimensions",
            placeholder: "例如 1920x1080",
            minSdk: 31,
            requires: CAMERA,
          }
        ),
        C(
          "cameraFps",
          "摄像头帧率",
          "--camera-fps",
          "摄像头采集帧率，预设 30 / 60 / 120",
          "对应 --camera-fps。官方默认使用 Android 的 30 fps，选择默认值不会附加参数。预设为 30、60、120 fps。",
          [
            { value: "30", label: "30 fps（默认）" },
            { value: "60", label: "60 fps" },
            { value: "120", label: "120 fps" },
          ],
          "30",
          "",
          {
            comboKind: "fps",
            quick: true,
            quickPresets: [
              { value: "30", label: "30" },
              { value: "60", label: "60" },
              { value: "120", label: "120" },
            ],
            minSdk: 31,
            requires: CAMERA,
          }
        ),
        X(
          "cameraId",
          "摄像头 ID",
          "--camera-id",
          "直接指定某颗摄像头的编号",
          "对应 --camera-id。优先级高于 --camera-facing；可用 scrcpy --list-cameras 查看设备上的摄像头编号。",
          "例如 0",
          { minSdk: 31, requires: CAMERA }
        ),
        T(
          "cameraTorch",
          "打开补光灯",
          "--camera-torch",
          "采集摄像头时同时打开闪光灯",
          "对应 --camera-torch。只在摄像头模式有效，且设备需要有可控补光灯。",
          false,
          { minSdk: 31, requires: CAMERA }
        ),
        N(
          "cameraZoom",
          "初始变焦",
          "--camera-zoom",
          "设置摄像头启动时的放大倍数",
          "对应 --camera-zoom。留空使用设备默认值。数值越大画面越近，可用 scrcpy 快捷键继续调整。",
          "×",
          { minSdk: 31, requires: CAMERA, min: 0.1, max: 10, step: 0.1 }
        ),
        T(
          "cameraHighSpeed",
          "高速采集模式",
          "--camera-high-speed",
          "尝试使用高帧率摄像头模式",
          "对应 --camera-high-speed。仅部分摄像头和特定分辨率支持，开启后如果失败请关闭。",
          false,
          { minSdk: 31, requires: CAMERA }
        ),
        X(
          "cameraAr",
          "宽高比筛选",
          "--camera-ar",
          "按比例自动选择摄像头尺寸，例如 16:9",
          "对应 --camera-ar。可填 sensor、4:3、16:9 或 1.6 这样的比例；用于在支持的尺寸中自动挑选。",
          "16:9",
          { minSdk: 31, requires: CAMERA }
        ),
      ],
    },
    {
      id: "virtual",
      title: "虚拟显示",
      icon: "i-vdisplay",
      note: "新开虚拟屏幕、启动应用或镜像指定显示",
      options: [
        C(
          "newDisplay",
          "虚拟显示尺寸",
          "--new-display",
          "新开一块虚拟屏幕，与手机当前画面互不影响",
          "对应 --new-display。留空表示正常镜像设备当前屏幕。选择「主屏尺寸与 DPI」会附加裸参数 --new-display（尺寸和 DPI 取自主屏）；也可以直接输入 1920x1080、1920x1080/420、/240 这样的值。虚拟显示需要 Android 10+，旧设备上相关选项会自动禁用。",
          [
            { value: "", label: "关闭（镜像当前屏幕，默认）" },
            { value: "main", label: "主屏尺寸与 DPI" },
            { value: "1920x1080", label: "1920×1080" },
            { value: "1280x720", label: "1280×720" },
            { value: "2560x1440", label: "2560×1440" },
            { value: "3840x2160", label: "3840×2160" },
            { value: "1080x1920", label: "竖屏 1080×1920" },
            { value: "1920x1080/420", label: "1920×1080 · 420 DPI" },
            { value: "/240", label: "主屏尺寸 · 240 DPI" },
          ],
          "",
          "",
          {
            comboKind: "display",
            placeholder: "例如 1920x1080/420，输入 main 使用主屏",
            minSdk: 29,
          }
        ),
        N(
          "displayId",
          "镜像显示 ID",
          "--display-id",
          "镜像设备上已有的某块显示，0 是主屏",
          "对应 --display-id。默认 0（主屏），填 0 不会附加参数。可用 scrcpy --list-displays 查看设备上的显示 ID。它与「虚拟显示尺寸」互斥：已开启虚拟显示时不能再指定显示 ID。",
          "",
          { min: 0, step: 1, omitValues: ["0"], conflictsWithVirtual: true }
        ),
        X(
          "startApp",
          "启动应用",
          "--start-app",
          "在虚拟屏幕或当前屏幕上启动指定应用",
          "对应 --start-app。填写完整包名，例如 org.mozilla.firefox；前缀 ? 表示按名称模糊匹配，前缀 + 表示启动前先强制停止，例如 +?firefox。配合虚拟显示使用时，应用会启动在新屏幕上。",
          "例如 +?firefox"
        ),
        T(
          "flexDisplay",
          "窗口尺寸联动虚拟屏",
          "--flex-display",
          "拖动窗口时持续调整虚拟显示分辨率",
          "对应 --flex-display。开启后虚拟显示会跟随窗口尺寸变化，画面按原始像素呈现（不再默认留黑边）。需要先开启「虚拟显示尺寸」。",
          false,
          { requiresVirtualDisplay: true }
        ),
        T(
          "noVdDestroyContent",
          "关闭后保留虚拟屏应用",
          "--no-vd-destroy-content",
          "移除虚拟屏时把应用移回主屏，而不是销毁",
          "对应 --no-vd-destroy-content。默认关闭虚拟显示时会销毁上面的应用；开启后，应用会被移动到主屏继续运行。需要先开启「虚拟显示尺寸」。",
          false,
          { requiresVirtualDisplay: true }
        ),
        T(
          "noVdSystemDecorations",
          "隐藏虚拟屏系统装饰",
          "--no-vd-system-decorations",
          "去掉虚拟屏上的状态栏等系统装饰",
          "对应 --no-vd-system-decorations。开启后虚拟显示不显示状态栏、导航栏等系统装饰，画面更像一块纯应用屏幕。需要先开启「虚拟显示尺寸」。",
          false,
          { requiresVirtualDisplay: true }
        ),
        S(
          "displayImePolicy",
          "输入法显示位置",
          "--display-ime-policy",
          "控制输入法显示在哪块屏幕上",
          "对应 --display-ime-policy。local 显示在当前屏幕；fallback 回退到主屏；hide 不显示输入法。与虚拟显示配合使用。",
          [
            { value: "local", label: "当前（默认）", arg: null },
            { value: "fallback", label: "主屏" },
            { value: "hide", label: "隐藏" },
          ],
          "local",
          { requiresVirtualDisplay: true }
        ),
      ],
    },
    {
      id: "control",
      title: "控制",
      icon: "i-mouse",
      note: "键盘鼠标、剪贴板与只读",
      options: [
        T(
          "noControl",
          "只读模式",
          "--no-control",
          "电脑只能看，不能操作设备",
          "对应 --no-control（简写 -n）。禁用所有点击、滑动和键盘注入，适合演示或安全查看。"
        ),
        S(
          "keyboard",
          "键盘输入方式",
          "--keyboard",
          "选择系统 API 或模拟实体键盘",
          "对应 --keyboard。默认 sdk 使用 Android 系统接口；uhid 会模拟实体键盘，兼容性更广但需要 Android 6+（部分旧系统可能受 UHID 权限限制），并需要在设备上配置键盘布局；disabled 完全禁用键盘。",
          [
            { value: "sdk", label: "系统 API（默认）", arg: null },
            { value: "uhid", label: "模拟实体键盘", minSdk: 23 },
            { value: "disabled", label: "禁用键盘" },
          ],
          "sdk"
        ),
        S(
          "mouse",
          "鼠标输入方式",
          "--mouse",
          "选择相对鼠标或系统指针",
          "对应 --mouse。官方默认 sdk，选择默认值不会附加参数。uhid 会捕获电脑鼠标并模拟实体鼠标，适合游戏；disabled 完全禁用鼠标。",
          [
            { value: "sdk", label: "系统 API（默认）", arg: null },
            { value: "uhid", label: "模拟实体鼠标", minSdk: 23 },
            { value: "disabled", label: "禁用鼠标" },
          ],
          "sdk"
        ),
        S(
          "gamepad",
          "手柄输入",
          "--gamepad",
          "把电脑手柄转发给设备",
          "对应 --gamepad。官方默认禁用，选择默认值不会附加参数；uhid 模拟实体手柄，需要 Android 6+（部分旧系统可能受 UHID 权限限制）。",
          [
            { value: "disabled", label: "禁用（默认）", arg: null },
            { value: "uhid", label: "模拟实体手柄", minSdk: 23 },
          ],
          "disabled"
        ),
        T(
          "noKeyRepeat",
          "不重复按键",
          "--no-key-repeat",
          "按住按键时不连续触发",
          "对应 --no-key-repeat。某些游戏或输入场景下，长按重复会带来意外行为，可开启此项。"
        ),
        T(
          "preferText",
          "优先输入文本",
          "--prefer-text",
          "把字母和空格作为文本输入而不是按键",
          "对应 --prefer-text。能改善特殊字符输入，但会破坏游戏中 WASD 这类按键行为。"
        ),
        T(
          "legacyPaste",
          "兼容粘贴模式",
          "--legacy-paste",
          "用逐键输入的方式粘贴电脑剪贴板",
          "对应 --legacy-paste。部分设备无法通过系统接口设置剪贴板时，可用这个兼容方案。"
        ),
        T(
          "noClipboardAutosync",
          "禁用剪贴板同步",
          "--no-clipboard-autosync",
          "停止自动同步电脑与设备的剪贴板",
          "对应 --no-clipboard-autosync。默认双向自动同步；如果剪贴板冲突或涉及敏感内容，可以关闭。"
        ),
      ],
    },
    {
      id: "record",
      title: "录制与后台",
      icon: "i-record",
      note: "保存画面、后台运行与限时",
      options: [
        X(
          "record",
          "录制到文件",
          "--record",
          "把镜像画面保存为视频文件",
          "对应 --record（简写 -r）。填写完整路径即可，例如 D:\\Videos\\phone.mp4；只填文件名会保存到当前用户目录。留空则不录制。",
          "D:\\Videos\\phone.mp4"
        ),
        S(
          "recordFormat",
          "录制格式",
          "--record-format",
          "指定容器格式，留空按扩展名判断",
          "对应 --record-format。通常不需要指定；当文件扩展名缺失或想强制 MKV/音频格式时使用。",
          [
            { value: "", label: "自动（按扩展名，默认）" },
            { value: "mp4", label: "MP4" },
            { value: "mkv", label: "MKV" },
            { value: "m4a", label: "M4A（音频）" },
            { value: "mka", label: "MKA（音频）" },
            { value: "opus", label: "Opus（音频）" },
            { value: "aac", label: "AAC（音频）" },
            { value: "flac", label: "FLAC（音频）" },
            { value: "wav", label: "WAV（音频）" },
          ],
          "",
          { requiresRecord: true }
        ),
        T(
          "noWindow",
          "无窗口运行",
          "--no-window",
          "隐藏 scrcpy 窗口，仅在后台运行",
          "对应 --no-window。适合只录制不观看；如果没有填写录制文件，scrcpy 会禁用视频，通常没有必要这样运行。"
        ),
        N(
          "timeLimit",
          "自动停止时限",
          "--time-limit",
          "运行指定秒数后自动结束",
          "对应 --time-limit。留空或 0 表示不限时，适合定时录制或自动化测试。",
          "秒",
          { min: 0, step: 1, omitValues: ["0"] }
        ),
      ],
    },
    {
      id: "advanced",
      title: "高级",
      icon: "i-sliders",
      note: "窗口细节、缓冲与兼容性",
      options: [
        X(
          "windowTitle",
          "窗口标题",
          "--window-title",
          "自定义 scrcpy 窗口显示的标题",
          "对应 --window-title。留空使用默认标题，支持空格和中文。",
          "我的手机"
        ),
        N(
          "windowX",
          "窗口 X 坐标",
          "--window-x",
          "窗口左上角的水平位置，可使用负坐标",
          "对应 --window-x。留空为自动（auto）。多显示器或把窗口放到屏幕左侧时可以使用负数，例如 -1440。",
          "px",
          { step: 1 }
        ),
        N(
          "windowY",
          "窗口 Y 坐标",
          "--window-y",
          "窗口左上角的垂直位置，可使用负坐标",
          "对应 --window-y。留空为自动（auto）。多显示器或把窗口放到屏幕上方时可以使用负数，例如 -1120。",
          "px",
          { step: 1 }
        ),
        N(
          "windowWidth",
          "窗口宽度",
          "--window-width",
          "指定启动时的窗口宽度",
          "对应 --window-width。留空或 0 为自动（官方默认，不附加参数）。可设置超过当前屏幕的尺寸，例如竖屏 1440×2560。",
          "px",
          { min: 0, step: 1, omitValues: ["0"] }
        ),
        N(
          "windowHeight",
          "窗口高度",
          "--window-height",
          "指定启动时的窗口高度",
          "对应 --window-height。留空或 0 为自动（官方默认，不附加参数）。可设置超过当前屏幕的尺寸，例如竖屏 1440×2560。",
          "px",
          { min: 0, step: 1, omitValues: ["0"] }
        ),
        S(
          "renderFit",
          "画面适配方式",
          "--render-fit",
          "窗口缩放时如何填充画面",
          "对应 --render-fit。letterbox 保持比例并留黑边；stretched 拉伸铺满；unscaled 按原始像素显示。",
          [
            { value: "letterbox", label: "保持比例 / 黑边（默认）", arg: null },
            { value: "stretched", label: "拉伸铺满" },
            { value: "unscaled", label: "原始像素" },
          ],
          "letterbox"
        ),
        N(
          "videoBuffer",
          "视频缓冲",
          "--video-buffer",
          "增加视频延迟以换取更平稳的播放",
          "对应 --video-buffer，单位毫秒。官方默认 0，输入 0 不会附加参数。网络抖动明显时可以适当增加，但会增加操作延迟。",
          "ms",
          { min: 0, step: 10, omitValues: ["0"] }
        ),
        N(
          "audioBuffer",
          "音频缓冲",
          "--audio-buffer",
          "增加音频延迟以减少爆音和卡顿",
          "对应 --audio-buffer，单位毫秒。官方默认 50，输入 50 不会附加参数。设置过小可能导致音频断续。",
          "ms",
          { min: 0, step: 10, omitValues: ["50"] }
        ),
        T(
          "noCleanup",
          "退出时不还原设备状态",
          "--no-cleanup",
          "保留触摸显示、常亮等临时设置",
          "对应 --no-cleanup。默认 scrcpy 退出时会恢复设备状态；开启后不清理，可能让设备的「显示触摸」或常亮保持开启。",
          false
        ),
        T(
          "disableScreensaver",
          "运行时禁用屏保",
          "--disable-screensaver",
          "防止电脑屏保在镜像时启动",
          "对应 --disable-screensaver。适合长时间展示，但会增加电脑耗电。"
        ),
        T(
          "keepActive",
          "模拟用户活跃",
          "--keep-active",
          "通过模拟活动保持设备不休眠",
          "对应 --keep-active。和「保持唤醒」类似，但会模拟用户活动；部分设备上更可靠。"
        ),
        T(
          "noPowerOn",
          "不自动唤醒设备",
          "--no-power-on",
          "启动时不点亮设备屏幕",
          "对应 --no-power-on。默认 scrcpy 会尝试在连接时点亮设备；如果设备已经亮着或不想被唤醒，可开启。"
        ),
        S(
          "verbosity",
          "日志详细程度",
          "--verbosity",
          "控制输出日志的多少",
          "对应 --verbosity。默认 info；排查问题时选择 debug 或 verbose。日志显示在右侧结果面板。",
          [
            { value: "info", label: "信息（默认）", arg: null },
            { value: "verbose", label: "全部日志" },
            { value: "debug", label: "调试" },
            { value: "warn", label: "警告" },
            { value: "error", label: "仅错误" },
          ],
          "info"
        ),
      ],
    },
  ];

  const OPTIONS = GROUPS.flatMap((group) => group.options);
  const OPTION_MAP = new Map(OPTIONS.map((option) => [option.id, option]));
  const GROUP_MAP = new Map(GROUPS.map((group) => [group.id, group]));
  const DEFAULT_OPTIONS = Object.fromEntries(
    OPTIONS.map((option) => [option.id, option.default])
  );
  const DEFAULT_COLLAPSED = ["advanced", "record"];
  const PRESET_SCALE_STEPS = [75, 100, 125, 150, 175, 200, 225, 250];
  const SCALE_MIN = 70;
  const SCALE_MAX = 250;
  // When the UI is zoomed, keep three columns until the middle column would
  // be narrower than this.  Was 430px; the middle only needs about 70% of
  // that before switching to the two-column layout.
  const COMPACT_CENTER_MIN = 300;
  const AFTER_START_CHOICES = [
    {
      value: "focus",
      label: "仅聚焦到投屏窗口",
      detail: "开始投屏后只把投屏窗口切到最前，控制台保持原样",
    },
    {
      value: "minimize",
      label: "最小化控制台",
      detail: "开始投屏后把投屏窗口切到最前，再把控制台最小化到任务栏",
    },
    {
      value: "tray",
      label: "最小化到托盘",
      detail:
        "开始投屏后把投屏窗口切到最前，把控制台收进托盘并停止界面，只保留托盘与后端服务",
    },
  ];
  const DEFAULT_AFTER_START = "focus";
  const DEFAULT_SETTINGS = {
    version: 2,
    updatedAt: 0,
    accent: "teal",
    appearance: "system",
    uiScale: "system",
    afterStart: DEFAULT_AFTER_START,
    autoOpenConsole: true,
    keepInBackground: true,
    selectedDevice: "",
    wirelessAddress: "",
    collapsedSections: [...DEFAULT_COLLAPSED],
    options: { ...DEFAULT_OPTIONS },
    extraArgs: "",
    profiles: [],
    lastProfile: null,
  };

  const DEVICE_STATE_LABELS = {
    device: "在线",
    unauthorized: "未授权",
    offline: "离线",
    connecting: "连接中",
    authorizing: "授权中",
    recovery: "恢复中",
    "no permissions": "无权限",
  };

  const state = {
    settings: normalizeSettings(loadLocalSettings() || {}),
    devices: [],
    devicesLoading: true,
    devicesError: null,
    selectedDeviceSerial: "",
    search: "",
    ws: null,
    wsOpen: false,
    helloReceived: false,
    helloTimeout: null,
    socketAttempts: 0,
    server: null,
    tools: null,
    trayAvailable: true,
    windowBackend: "",
    currentArgv: ["scrcpy"],
    starting: false,
    running: false,
    stopping: false,
    pendingRestart: false,
    runStartedAt: 0,
    runTimer: null,
    runBadgeMode: "idle",
    runBadgeText: "尚未运行",
    logLines: [],
    stickToBottom: true,
    saveTimer: null,
    pageHidden: false,
    shuttingDown: false,
    overlayAction: "close",
    lastCommand: "scrcpy",
    pendingRunSnapshot: null,
    profileDialogResolver: null,
    activeProfileId: "",
  };

  const dom = {};

  function byId(id) {
    return document.getElementById(id);
  }

  function svgIcon(name, className = "icon") {
    return `<svg class="${className}"><use href="#${name}"></use></svg>`;
  }

  // -----------------------------------------------------------------------
  // Settings
  // -----------------------------------------------------------------------

  function normalizeComboValue(option, rawValue) {
    const text = String(rawValue ?? "").trim();
    if (!text) {
      return option.default || "";
    }
    if (option.comboKind === "bitrate") {
      const match = text.match(/^(\d+(?:\.\d+)?)\s*(k|m|kbps|mbps)?$/i);
      if (!match) {
        return text;
      }
      const number = String(Number(match[1]));
      let suffix = (match[2] || option.suffix || "M").toUpperCase();
      if (suffix.endsWith("BPS")) {
        suffix = suffix.slice(0, 1);
      }
      return `${number}${suffix}`;
    }
    if (option.comboKind === "size") {
      const match = text.match(/^(\d+(?:\.\d+)?)\s*(?:px)?$/i);
      return match ? String(Number(match[1])) : text;
    }
    if (option.comboKind === "fps") {
      const match = text.match(/^(\d+(?:\.\d+)?)\s*(?:fps)?$/i);
      return match ? String(Number(match[1])) : text;
    }
    if (option.comboKind === "dimensions") {
      const cleaned = text.replace(/×/g, "x").replace(/\s+/g, "");
      const match = cleaned.match(/^(\d+)x(\d+)$/i);
      return match ? `${match[1]}x${match[2]}` : text;
    }
    if (option.comboKind === "display") {
      const cleaned = text.replace(/×/g, "x").replace(/\s+/g, "");
      if (/^(main|主屏|主屏幕)$/i.test(cleaned)) {
        return "main";
      }
      const sized = cleaned.match(/^(\d{2,4})x(\d{3,5})(?:\/(\d{2,4}))?$/i);
      if (sized) {
        return `${sized[1]}x${sized[2]}${
          sized[3] ? `/${sized[3]}` : ""
        }`;
      }
      const dpiOnly = cleaned.match(/^\/(\d{2,4})$/);
      if (dpiOnly) {
        return `/${dpiOnly[1]}`;
      }
      return cleaned;
    }
    return text;
  }

  function normalizeOptionValue(option, rawValue) {
    if (option.type === "toggle") {
      return typeof rawValue === "boolean" ? rawValue : option.default;
    }
    if (option.type === "select") {
      const value = rawValue == null ? "" : String(rawValue);
      return option.choices.some((choice) => choice.value === value)
        ? value
        : option.default;
    }
    if (option.type === "combo") {
      const normalized = normalizeComboValue(option, rawValue);
      if (
        option.quick &&
        !(option.quickPresets || []).some(
          (preset) =>
            normalizeComboValue(option, preset.value) === normalized
        )
      ) {
        return normalizeComboValue(option, option.default);
      }
      return normalized;
    }
    if (option.type === "number") {
      if (typeof rawValue === "number" && Number.isFinite(rawValue)) {
        return String(rawValue);
      }
      if (typeof rawValue === "string" && rawValue.length <= 80) {
        return rawValue;
      }
      return option.default;
    }
    if (typeof rawValue === "string") {
      return rawValue.slice(0, 1000);
    }
    return option.default;
  }

  function normalizeOptions(raw) {
    const options = { ...DEFAULT_OPTIONS };
    if (raw && typeof raw === "object") {
      for (const option of OPTIONS) {
        if (Object.prototype.hasOwnProperty.call(raw, option.id)) {
          options[option.id] = normalizeOptionValue(option, raw[option.id]);
        }
      }
    }
    return options;
  }

  function normalizeProfile(raw, { last = false } = {}) {
    if (!raw || typeof raw !== "object") {
      return null;
    }
    const id = last ? "last" : String(raw.id || "").slice(0, 100);
    const name = last ? "上一次" : String(raw.name || "").trim().slice(0, 60);
    if (
      !id ||
      !name ||
      (!last && (id === "last" || name === "上一次"))
    ) {
      return null;
    }
    const createdAt =
      typeof raw.createdAt === "number" && Number.isFinite(raw.createdAt)
        ? Math.max(0, raw.createdAt)
        : 0;
    const updatedAt =
      typeof raw.updatedAt === "number" && Number.isFinite(raw.updatedAt)
        ? Math.max(0, raw.updatedAt)
        : 0;
    const argv = Array.isArray(raw.argv)
      ? raw.argv.filter((arg) => typeof arg === "string").slice(0, 200)
      : [];
    const optionCount =
      typeof raw.optionCount === "number" && Number.isFinite(raw.optionCount)
        ? Math.max(0, Math.min(500, Math.round(raw.optionCount)))
        : 0;
    return {
      id,
      name,
      createdAt,
      updatedAt,
      selectedDevice:
        typeof raw.selectedDevice === "string"
          ? raw.selectedDevice.slice(0, 300)
          : "",
      deviceLabel:
        typeof raw.deviceLabel === "string" ? raw.deviceLabel.slice(0, 120) : "",
      command:
        typeof raw.command === "string" ? raw.command.slice(0, 16_000) : "",
      optionCount,
      options: normalizeOptions(raw.options),
      extraArgs:
        typeof raw.extraArgs === "string" ? raw.extraArgs.slice(0, 4000) : "",
      argv,
    };
  }

  function normalizeProfiles(raw) {
    if (!Array.isArray(raw)) {
      return [];
    }
    const profiles = [];
    const seen = new Set();
    for (const item of raw.slice(0, 100)) {
      const profile = normalizeProfile(item);
      if (!profile || seen.has(profile.id)) {
        continue;
      }
      seen.add(profile.id);
      profiles.push(profile);
    }
    return profiles;
  }

  function parseUiScalePercent(value) {
    const match = String(value ?? "")
      .trim()
      .match(/^(\d{2,3})\s*%?$/);
    if (!match) {
      return null;
    }
    const percent = Number(match[1]);
    return percent >= SCALE_MIN && percent <= SCALE_MAX ? percent : null;
  }

  function normalizeUiScale(value) {
    if (value === "system") {
      return "system";
    }
    const percent = parseUiScalePercent(value);
    return percent === null ? "system" : String(percent);
  }

  function normalizeAfterStart(value) {
    return AFTER_START_CHOICES.some((choice) => choice.value === value)
      ? value
      : DEFAULT_AFTER_START;
  }

  function normalizeAccent(value, legacyTheme) {
    if (Object.prototype.hasOwnProperty.call(ACCENTS, value)) {
      return value;
    }
    if (Object.prototype.hasOwnProperty.call(LEGACY_THEME_ACCENTS, legacyTheme)) {
      return LEGACY_THEME_ACCENTS[legacyTheme];
    }
    return "teal";
  }

  function normalizeAppearance(value) {
    return Object.prototype.hasOwnProperty.call(APPEARANCES, value)
      ? value
      : "system";
  }

  function normalizeSettings(raw) {
    const source = raw && typeof raw === "object" ? raw : {};
    const options = normalizeOptions(source.options);
    let collapsed = [...DEFAULT_COLLAPSED];
    if (Array.isArray(source.collapsedSections)) {
      collapsed = [...new Set(source.collapsedSections)].filter((id) =>
        GROUP_MAP.has(id)
      );
    }
    return {
      version: 2,
      updatedAt:
        typeof source.updatedAt === "number" &&
        Number.isFinite(source.updatedAt) &&
        source.updatedAt > 0
          ? source.updatedAt
          : 0,
      accent: normalizeAccent(source.accent, source.theme),
      appearance: normalizeAppearance(source.appearance),
      uiScale: normalizeUiScale(source.uiScale),
      afterStart: normalizeAfterStart(source.afterStart),
      autoOpenConsole:
        typeof source.autoOpenConsole === "boolean"
          ? source.autoOpenConsole
          : true,
      keepInBackground:
        typeof source.keepInBackground === "boolean"
          ? source.keepInBackground
          : true,
      selectedDevice:
        typeof source.selectedDevice === "string"
          ? source.selectedDevice.slice(0, 300)
          : "",
      wirelessAddress:
        typeof source.wirelessAddress === "string"
          ? source.wirelessAddress.slice(0, 300)
          : "",
      collapsedSections: collapsed,
      options,
      extraArgs:
        typeof source.extraArgs === "string"
          ? source.extraArgs.slice(0, 4000)
          : "",
      profiles: normalizeProfiles(source.profiles),
      lastProfile: normalizeProfile(source.lastProfile, { last: true }),
    };
  }

  function loadLocalSettings() {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) {
        return null;
      }
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : null;
    } catch {
      return null;
    }
  }

  function persistLocalSettings() {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state.settings));
    } catch {
      /* localStorage may be unavailable; backend persistence still works. */
    }
  }

  function setSaveStatus(mode, text) {
    if (!dom.saveIndicator) {
      return;
    }
    dom.saveIndicator.classList.toggle("is-saving", mode === "saving");
    dom.saveIndicator.classList.toggle("is-error", mode === "error");
    dom.saveText.textContent = text;
  }

  function markSettingsChanged(options = {}) {
    state.settings.updatedAt = Date.now();
    persistLocalSettings();
    if (options.hint !== false) {
      setSaveStatus(
        "saving",
        options.debounce ? "保存中…" : "自动保存中…"
      );
    }
    if (state.saveTimer) {
      window.clearTimeout(state.saveTimer);
      state.saveTimer = null;
    }
    if (!options.debounce) {
      flushSettings();
      return;
    }
    state.saveTimer = window.setTimeout(flushSettings, 150);
  }

  function flushSettings() {
    if (state.saveTimer) {
      window.clearTimeout(state.saveTimer);
      state.saveTimer = null;
    }
    if (!state.wsOpen || !state.helloReceived) {
      setSaveStatus("error", "本地已保存，等待后端");
      return;
    }
    if (!sendMessage({ type: "save_settings", settings: state.settings })) {
      setSaveStatus("error", "设置未能保存");
    }
  }

  // -----------------------------------------------------------------------
  // Appearance and accent colour
  // -----------------------------------------------------------------------

  function currentAppearance() {
    return document.documentElement.dataset.appearance === "light"
      ? "light"
      : "dark";
  }

  function resolveAppearance(choice) {
    if (choice === "light" || choice === "dark") {
      return choice;
    }
    return window.matchMedia?.("(prefers-color-scheme: light)")?.matches
      ? "light"
      : "dark";
  }

  function accentGradient(key) {
    const accent = ACCENTS[key] || ACCENTS.teal;
    const pair =
      !SHARED_ACCENT_PALETTE && currentAppearance() === "light"
        ? accent.light
        : accent.dark;
    return `linear-gradient(135deg, ${pair[0]} 0%, ${pair[1]} 100%)`;
  }

  function syncAppearanceControl(choice) {
    if (!dom.appearanceSwitch) {
      return;
    }
    for (const button of dom.appearanceSwitch.querySelectorAll(
      "[data-appearance-value]"
    )) {
      const active = button.dataset.appearanceValue === choice;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-checked", active ? "true" : "false");
    }
  }

  function applyAppearance(value, { persist = false } = {}) {
    const choice = normalizeAppearance(value);
    const resolved = resolveAppearance(choice);
    document.documentElement.dataset.appearance = resolved;
    syncAppearanceControl(choice);
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute(
        "content",
        resolved === "light" ? "#eef1f5" : "#080a0f"
      );
    }
    if (dom.appearanceSwitch) {
      dom.appearanceSwitch.title = `界面明暗：${APPEARANCES[choice]}`;
    }
    // The colour swatch follows the shared accent palette.
    applyAccent(state.settings.accent);
    if (persist && state.settings.appearance !== choice) {
      state.settings.appearance = choice;
      markSettingsChanged();
    }
  }

  function applyAccent(name, { persist = false, animate = false } = {}) {
    const key = normalizeAccent(name);
    if (animate) {
      document.documentElement.classList.add("theme-transition");
      window.clearTimeout(applyAccent.transitionTimer);
      applyAccent.transitionTimer = window.setTimeout(() => {
        document.documentElement.classList.remove("theme-transition");
      }, 300);
    }
    document.documentElement.dataset.accent = key;
    if (dom.colorLabel) {
      dom.colorLabel.textContent = ACCENTS[key].label;
    }
    if (dom.colorDot) {
      dom.colorDot.style.background = accentGradient(key);
    }
    if (dom.colorButton) {
      dom.colorButton.dataset.tooltip = `界面颜色：${ACCENTS[key].label}`;
      dom.colorButton.setAttribute(
        "aria-label",
        `界面颜色：${ACCENTS[key].label}`
      );
    }
    if (persist && state.settings.accent !== key) {
      state.settings.accent = key;
      markSettingsChanged();
    }
  }

  function openAccentMenu() {
    if (!dom.colorButton) {
      return;
    }
    openOptionMenu(dom.colorButton, {
      hintText: "选择一种界面颜色，明暗模式会自动适配",
      items: Object.entries(ACCENTS).map(([value, accent]) => ({
        value,
        label: accent.label,
        valueLabel: "",
        swatch: accentGradient(value),
        selected: state.settings.accent === value,
      })),
      onPick(value) {
        applyAccent(value, { persist: true, animate: true });
        dom.colorButton.focus();
      },
    });
  }

  // -----------------------------------------------------------------------
  // UI scale
  // -----------------------------------------------------------------------

  function getSystemScale() {
    const fromServer = Number(state.server?.systemScale);
    if (Number.isFinite(fromServer) && fromServer >= 0.5 && fromServer <= 4) {
      const renderer = getRendererScale();
      // A DPI-unaware fallback may report 96 DPI even on a scaled display.
      if (fromServer <= 1.001 && renderer > 1.05) {
        return renderer;
      }
      return fromServer;
    }
    return getRendererScale();
  }

  function getRendererScale() {
    const dpr = Number(window.devicePixelRatio);
    return Number.isFinite(dpr) && dpr >= 0.5 && dpr <= 5 ? dpr : 1;
  }

  function getTargetUiScale() {
    if (state.settings.uiScale === "system") {
      return getSystemScale();
    }
    const percent = Number(state.settings.uiScale);
    if (Number.isFinite(percent) && percent >= SCALE_MIN && percent <= SCALE_MAX) {
      return percent / 100;
    }
    return getSystemScale();
  }

  function syncUiScaleControl(systemScale, targetScale) {
    if (!dom.uiScaleInput) {
      return;
    }
    const savedValue = normalizeUiScale(state.settings.uiScale);
    const systemPercent = Math.round(systemScale * 100);
    if (document.activeElement !== dom.uiScaleInput) {
      dom.uiScaleInput.value =
        savedValue === "system" ? `跟随系统 ${systemPercent}%` : `${savedValue}%`;
    }
    const targetPercent = Math.round(targetScale * 100);
    const description =
      savedValue === "system"
        ? `跟随系统（${systemPercent}%）`
        : `${targetPercent}%（系统缩放 ${systemPercent}%）`;
    dom.scaleControl.title = `界面缩放：${description}`;
    dom.uiScaleInput.setAttribute("aria-label", `界面缩放：${description}`);
    dom.uiScaleToggle.setAttribute(
      "aria-expanded",
      comboMenuState?.anchor === dom.uiScaleInput ? "true" : "false"
    );
  }

  function openUiScaleMenu() {
    const systemPercent = Math.round(getSystemScale() * 100);
    const current = normalizeUiScale(state.settings.uiScale);
    openOptionMenu(dom.uiScaleInput, {
      hintText: `选择 25% 递增的预设，或输入 ${SCALE_MIN}%–${SCALE_MAX}%`,
      items: [
        {
          value: "system",
          label: "跟随系统",
          valueLabel: `${systemPercent}%`,
          selected: current === "system",
        },
        ...PRESET_SCALE_STEPS.map((percent) => ({
          value: String(percent),
          label: `${percent}%`,
          valueLabel: `${percent}%`,
          selected: current === String(percent),
        })),
      ],
      onPick(value) {
        state.settings.uiScale = normalizeUiScale(value);
        applyUiScale({ persist: true });
        dom.uiScaleInput.focus();
      },
    });
  }

  function commitUiScaleInput() {
    if (!dom.uiScaleInput) {
      return;
    }
    const raw = dom.uiScaleInput.value.trim();
    if (/^跟随系统/.test(raw)) {
      if (state.settings.uiScale !== "system") {
        state.settings.uiScale = "system";
        applyUiScale({ persist: true });
      } else {
        applyUiScale();
      }
      return;
    }
    const percent = parseUiScalePercent(raw);
    if (percent === null) {
      const systemPercent = Math.round(getSystemScale() * 100);
      dom.uiScaleInput.value =
        state.settings.uiScale === "system"
          ? `跟随系统 ${systemPercent}%`
          : `${state.settings.uiScale}%`;
      syncUiScaleControl(getSystemScale(), getTargetUiScale());
      showToast(
        `界面缩放请输入 ${SCALE_MIN}%–${SCALE_MAX}% 之间的数值`,
        "warning"
      );
      return;
    }
    const value = String(percent);
    if (state.settings.uiScale !== value) {
      state.settings.uiScale = value;
      applyUiScale({ persist: true });
    } else {
      applyUiScale();
    }
  }

  function applyUiScale({ persist = false } = {}) {
    if (!dom.uiScaleInput) {
      return;
    }
    const systemScale = getSystemScale();
    const rendererScale = getRendererScale();
    const targetScale = Math.max(
      SCALE_MIN / 100,
      Math.min(SCALE_MAX / 100, getTargetUiScale())
    );
    const factor = Math.max(
      0.5,
      Math.min(SCALE_MAX / 100, targetScale / rendererScale)
    );

    document.documentElement.style.setProperty(
      "--ui-zoom",
      factor.toFixed(4)
    );
    document.documentElement.dataset.uiZoom = String(targetScale);
    document.documentElement.classList.toggle("ui-zoomed", factor > 1.08);

    const sideWidth = window.innerWidth > 1440 ? 766 : 728;
    const availableCenter = window.innerWidth - sideWidth * factor;
    const compact =
      factor > 1.001 &&
      window.innerWidth > 1180 &&
      availableCenter < COMPACT_CENTER_MIN;
    document.documentElement.classList.toggle("ui-compact", compact);

    syncUiScaleControl(systemScale, targetScale);

    if (persist) {
      markSettingsChanged();
    }
  }

  // -----------------------------------------------------------------------
  // Console behaviour after starting scrcpy
  // -----------------------------------------------------------------------

  function syncAfterStartControl() {
    if (!dom.afterStartControl) {
      return;
    }
    const value = normalizeAfterStart(state.settings.afterStart);
    const trayAvailable = state.trayAvailable !== false;
    for (const button of dom.afterStartControl.querySelectorAll(
      "[data-after-start]"
    )) {
      const choice = AFTER_START_CHOICES.find(
        (item) => item.value === button.dataset.afterStart
      );
      if (!choice) {
        continue;
      }
      const blocked = choice.value === "tray" && !trayAvailable;
      const active = choice.value === value;
      button.disabled = blocked;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-checked", active ? "true" : "false");
      button.title = blocked
        ? `${choice.detail}（当前环境没有托盘图标，将改为最小化控制台）`
        : choice.detail;
    }
    dom.afterStartControl.classList.toggle(
      "is-fallback",
      value === "tray" && !trayAvailable
    );
  }

  function initAfterStartControl() {
    if (!dom.afterStartControl) {
      return;
    }
    for (const button of dom.afterStartControl.querySelectorAll(
      "[data-after-start]"
    )) {
      if (
        button.dataset.afterStart === DEFAULT_AFTER_START &&
        !button.querySelector(".segment-default-badge")
      ) {
        const badge = document.createElement("span");
        badge.className = "segment-default-badge";
        badge.textContent = "默认";
        badge.setAttribute("aria-hidden", "true");
        button.append(badge);
        const label = button.querySelector(".segment-label");
        button.setAttribute(
          "aria-label",
          `${label ? label.textContent : ""}（默认）`
        );
      }
    }
    syncAfterStartControl();
  }

  function syncAutoConsoleControl() {
    if (!dom.autoConsoleSwitch) {
      return;
    }
    const enabled = state.settings.autoOpenConsole !== false;
    dom.autoConsoleSwitch.setAttribute(
      "aria-checked",
      enabled ? "true" : "false"
    );
    dom.autoConsoleSwitch.title = enabled
      ? "已开启：投屏结束后自动打开最小化或收进托盘的控制台"
      : "已关闭：投屏结束后控制台保持当前状态";
    if (dom.autoConsoleState) {
      dom.autoConsoleState.textContent = enabled ? "开启" : "关闭";
    }
    if (dom.autoConsoleRow) {
      dom.autoConsoleRow.classList.toggle("is-off", !enabled);
    }
  }

  function syncKeepBackgroundControl() {
    if (!dom.keepBackgroundSwitch) {
      return;
    }
    const enabled = state.settings.keepInBackground !== false;
    dom.keepBackgroundSwitch.setAttribute(
      "aria-checked",
      enabled ? "true" : "false"
    );
    dom.keepBackgroundSwitch.title = enabled
      ? "已开启：点窗口 × 会把控制台收进托盘并停止界面，后端继续运行；顶部按钮用于退出"
      : "已关闭：点窗口 × 会彻底退出，顶部按钮用于收进托盘";
    if (dom.keepBackgroundState) {
      dom.keepBackgroundState.textContent = enabled ? "开启" : "关闭";
    }
    if (dom.keepBackgroundRow) {
      dom.keepBackgroundRow.classList.toggle("is-off", !enabled);
      dom.keepBackgroundRow.title = enabled
        ? "开启时，点窗口 × 收进托盘并停止界面；顶部按钮变为「退出应用」"
        : "关闭时，点窗口 × 彻底退出；顶部按钮用于「最小化到托盘」";
    }
    if (dom.windowActionLabel) {
      dom.windowActionLabel.textContent = enabled
        ? "退出应用"
        : state.trayAvailable === false
          ? "最小化控制台"
          : "最小化到托盘";
    }
    if (dom.windowActionButton) {
      dom.windowActionButton.classList.toggle("is-quit", enabled);
      dom.windowActionButton.title = enabled
        ? "彻底退出 AutoScrcpy（窗口的关闭按钮会收进托盘）"
        : state.trayAvailable === false
          ? "最小化控制台窗口（当前环境没有托盘图标）"
          : "把控制台收进托盘并停止界面（窗口的关闭按钮会彻底退出）";
      const use = dom.windowActionButton.querySelector("use");
      if (use) {
        use.setAttribute("href", enabled ? "#i-power" : "#i-tray");
      }
    }
  }

  function toggleKeepBackground() {
    state.settings.keepInBackground = state.settings.keepInBackground === false;
    syncKeepBackgroundControl();
    markSettingsChanged();
    showToast(
      state.settings.keepInBackground
        ? "关闭窗口时保留后台：点 × 收进托盘并停止界面，顶部按钮可退出"
        : "关闭窗口时彻底退出：顶部按钮可把控制台收进托盘",
      "info",
      4200
    );
  }

  function triggerWindowAction() {
    if (!state.helloReceived) {
      showToast("后端尚未连接", "error");
      return;
    }
    const action =
      state.settings.keepInBackground === false ? "park" : "quit";
    if (!sendMessage({ type: "app_action", action })) {
      showToast("无法发送窗口操作，后端连接已断开", "error");
    }
  }

  function updateExtraArgsState() {
    if (!dom.extraArgsBox) {
      return;
    }
    const parsed = parseExtraArgs();
    const invalid = Boolean(parsed.error);
    dom.extraArgsBox.classList.toggle("is-invalid", invalid);
    if (dom.extraArgsError) {
      dom.extraArgsError.hidden = !invalid;
      dom.extraArgsError.textContent = parsed.error;
    }
  }

  function syncExtraArgsInput() {
    if (!dom.extraArgsInput) {
      return;
    }
    if (document.activeElement !== dom.extraArgsInput) {
      dom.extraArgsInput.value = state.settings.extraArgs || "";
    }
    updateExtraArgsState();
  }


  // -----------------------------------------------------------------------
  // WebSocket
  // -----------------------------------------------------------------------

  function sendMessage(payload) {
    if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
      return false;
    }
    try {
      state.ws.send(JSON.stringify(payload));
      return true;
    } catch {
      return false;
    }
  }

  function setConnectionStatus(mode, text) {
    dom.connectionPill.classList.remove("is-pending", "is-online", "is-offline");
    dom.connectionPill.classList.add(`is-${mode}`);
    dom.connectionText.textContent = text;
  }

  function connectSocket() {
    if (window.location.protocol === "file:") {
      setConnectionStatus("offline", "请通过启动器运行");
      showDisconnectOverlay({
        mode: "failed",
        title: "请从启动器打开",
        message:
          "这个页面需要通过 AutoScrcpy 后端提供。请双击 launch.pyw（或运行 python app.py），不要直接打开 index.html。",
        action: "reload",
      });
      return;
    }

    state.socketAttempts += 1;
    const scheme = window.location.protocol === "https:" ? "wss" : "ws";
    let socket;
    try {
      socket = new WebSocket(`${scheme}://${window.location.host}/ws`);
    } catch (error) {
      showDisconnectOverlay({
        mode: "failed",
        title: "无法创建连接",
        message: String(error),
        action: "reload",
      });
      return;
    }
    state.ws = socket;
    setConnectionStatus(
      "pending",
      state.socketAttempts > 1 ? `正在重新连接（${state.socketAttempts}/4）` : "正在连接后端"
    );

    state.helloTimeout = window.setTimeout(() => {
      if (!state.helloReceived) {
        try {
          socket.close();
        } catch {
          /* ignore */
        }
      }
    }, 7000);

    socket.addEventListener("open", () => {
      state.wsOpen = true;
      setConnectionStatus("pending", "已连接，等待握手");
    });

    socket.addEventListener("message", (event) => {
      if (typeof event.data !== "string") {
        return;
      }
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }
      if (message && typeof message === "object") {
        handleServerMessage(message);
      }
    });

    socket.addEventListener("error", () => {
      /* The close event handles the user-visible state. */
    });

    socket.addEventListener("close", () => {
      window.clearTimeout(state.helloTimeout);
      state.helloTimeout = null;
      state.wsOpen = false;
      if (state.shuttingDown) {
        return;
      }
      if (!state.helloReceived) {
        if (state.socketAttempts < 4) {
          setConnectionStatus("pending", "正在重试连接…");
          window.setTimeout(connectSocket, 320);
        } else {
          setConnectionStatus("offline", "无法连接后端");
          showDisconnectOverlay({
            mode: "failed",
            title: "无法连接后端",
            message:
              "AutoScrcpy 后端可能已经退出。请重新启动 launch.pyw，或确认没有其他程序占用端口。",
            action: "reload",
          });
        }
        return;
      }
      if (state.pageHidden) {
        return;
      }
      handleConnectionLost();
    });
  }

  function handleServerMessage(message) {
    switch (message.type) {
      case "hello":
        handleHello(message);
        break;
      case "devices_loading":
        state.devicesLoading = true;
        renderDeviceStatus();
        break;
      case "devices":
        state.devicesLoading = false;
        state.devicesError = message.error || null;
        state.devices = Array.isArray(message.devices) ? message.devices : [];
        reconcileDeviceSelection();
        renderDevices();
        renderDeviceStatus();
        syncAllControls();
        updateCapabilityBanner();
        updateGroupBadges();
        updateCommandPreview();
        break;
      case "adb_result":
        handleAdbResult(message);
        break;
      case "run_started":
        handleRunStarted(message);
        break;
      case "run_output":
        handleRunOutput(message);
        break;
      case "run_status":
        if (message.status === "stopping") {
          state.stopping = true;
          setRunBadge("stopping", "正在停止");
          updateRunControls();
        }
        break;
      case "run_finished":
        handleRunFinished(message);
        break;
      case "settings_saved":
        if (
          typeof message.updatedAt === "number" &&
          message.updatedAt >= state.settings.updatedAt
        ) {
          setSaveStatus("saved", "已自动保存");
        }
        break;
      case "settings_error":
        setSaveStatus("error", "设置保存失败");
        showToast(message.message || "设置保存失败", "error");
        break;
      case "error":
        showToast(message.message || "后端返回错误", "error");
        if (state.starting) {
          state.starting = false;
          state.pendingRunSnapshot = null;
          setRunBadge("fail", "启动失败");
          updateRunControls();
        }
        break;
      case "shutdown":
        state.shuttingDown = true;
        setConnectionStatus("offline", "后端已退出");
        showDisconnectOverlay({
          mode: "shutdown",
          title: "后端已退出",
          message: message.reason || "AutoScrcpy 后端已经关闭，窗口即将关闭。",
          action: "close",
          autoClose: true,
        });
        break;
      case "pong":
        break;
      default:
        break;
    }
  }

  function handleHello(message) {
    state.helloReceived = true;
    state.socketAttempts = 0;
    window.clearTimeout(state.helloTimeout);
    state.helloTimeout = null;
    state.server = message;
    state.tools = message.tools || {};
    state.trayAvailable = message.trayAvailable !== false;
    state.windowBackend = message.windowBackend || "browser";

    const remote = normalizeSettings(message.settings);
    const local = loadLocalSettings();
    const localNormalized = local ? normalizeSettings(local) : null;
    const useLocal = localNormalized && localNormalized.updatedAt > remote.updatedAt;
    state.settings = useLocal ? localNormalized : remote;

    applyAppearance(state.settings.appearance);
    applyUiScale();
    syncAfterStartControl();
    syncAutoConsoleControl();
    syncKeepBackgroundControl();
    syncExtraArgsInput();
    dom.wirelessAddress.value = state.settings.wirelessAddress || "";
    dom.saveProfileButton.disabled = false;
    renderProfiles();
    applyCollapsedSections();

    setConnectionStatus("online", "后端已连接");
    setSaveStatus("saved", useLocal ? "正在同步本地设置" : "设置已载入");

    dom.scrcpyVersionValue.textContent = state.tools.scrcpyVersion || "未找到";
    dom.scrcpyVersionValue.title = state.tools.scrcpyPath || "PATH 中未找到 scrcpy";
    dom.adbVersionValue.textContent = shortAdbVersion(state.tools.adbVersion);
    dom.adbVersionValue.title = state.tools.adbVersion || "PATH 中未找到 adb";
    dom.portValue.textContent = `127.0.0.1:${message.port}`;
    dom.portValue.title = message.url || "";
    if (dom.windowBackendValue) {
      const labels = {
        webview: "WebView2",
        browser: "浏览器",
        none: "未打开",
      };
      dom.windowBackendValue.textContent =
        labels[state.windowBackend] || state.windowBackend || "—";
      dom.windowBackendValue.title =
        state.windowBackend === "webview"
          ? `${message.webviewInfo || "WebView2"} · 关闭按钮由后端接管`
          : "使用 Edge/Chrome 应用窗口；关闭按钮无法被后端接管";
    }

    restoreRunState(message.run);
    syncAllControls();
    updateCapabilityBanner();
    updateGroupBadges();
    updateCommandPreview();

    if (useLocal) {
      markSettingsChanged({ hint: false });
    }

    if (Array.isArray(state.tools.errors) && state.tools.errors.length > 0) {
      showToast(state.tools.errors[0], "warning", 5200);
    }

    sendMessage({ type: "list_devices" });
  }

  function restoreRunState(run) {
    if (!run || !run.running) {
      return;
    }
    state.starting = false;
    state.running = true;
    state.stopping = false;
    state.pendingRestart = false;
    state.runStartedAt = Number(run.startedAt) || Date.now();
    setRunBadge("running", "运行中");
    startRunTimer();
    updateRunSummary();
    const runNumber = Number(run.runNumber) || 1;
    appendLogLine(
      `已重新连接到正在运行的 scrcpy（运行 #${runNumber}${
        run.pid ? ` · PID ${run.pid}` : ""
      }）`,
      Date.now(),
      "is-dim"
    );
  }

  function handleConnectionLost() {
    setConnectionStatus("offline", "连接已断开");
    state.running = false;
    state.starting = false;
    state.stopping = false;
    state.pendingRestart = false;
    state.pendingRunSnapshot = null;
    dom.saveProfileButton.disabled = true;
    stopRunTimer();
    setRunBadge("fail", "已断开");
    updateRunControls();
    showDisconnectOverlay({
      mode: "lost",
      title: "连接已断开",
      message:
        "与后端的连接中断，后端会随之退出。窗口即将自动关闭；若没有关闭，请点击下方按钮。",
      action: "close",
      autoClose: true,
    });
  }

  function showDisconnectOverlay({ mode, title, message, action, autoClose = false }) {
    state.overlayAction = action || "close";
    if (mode === "failed") {
      dom.disconnectEyebrow.textContent = "CONNECTION FAILED";
    } else if (mode === "shutdown") {
      dom.disconnectEyebrow.textContent = "BACKEND STOPPED";
    } else {
      dom.disconnectEyebrow.textContent = "CONNECTION LOST";
    }
    dom.disconnectTitle.textContent = title;
    dom.disconnectMessage.textContent = message;
    dom.disconnectCloseButton.textContent =
      action === "reload" ? "重新加载" : "关闭窗口";
    dom.disconnectOverlay.hidden = false;
    dom.disconnectCloseButton.focus({ preventScroll: true });
    if (autoClose) {
      window.setTimeout(() => {
        if (!state.pageHidden) {
          closeWindow();
        }
      }, 280);
    }
  }

  function closeWindow() {
    if (state.windowBackend === "webview") {
      // The native host owns the window; the backend closes it on shutdown.
      return;
    }
    try {
      window.close();
    } catch {
      /* Browsers may refuse; the overlay stays as a fallback. */
    }
  }

  // -----------------------------------------------------------------------
  // Devices
  // -----------------------------------------------------------------------

  function shortAdbVersion(version) {
    if (!version) {
      return "未找到";
    }
    const match = version.match(/version\s+([^\s]+)/i);
    return match ? match[1] : version.slice(0, 30);
  }

  function selectedDeviceObject() {
    if (!state.settings.selectedDevice) {
      return null;
    }
    return (
      state.devices.find(
        (device) => device.serial === state.settings.selectedDevice
      ) || null
    );
  }

  function selectedOnlineDevice() {
    const device = selectedDeviceObject();
    return device && device.state === "device" ? device : null;
  }

  function deviceSdk() {
    const device = selectedDeviceObject();
    const sdk = Number(device?.androidSdk);
    return Number.isFinite(sdk) && sdk > 0 ? sdk : null;
  }

  function deviceDisplayName(device) {
    if (!device) {
      return "未选择设备";
    }
    return (
      device.modelFromDevice ||
      device.model ||
      device.device ||
      device.serial ||
      "未知设备"
    );
  }

  function deviceAndroidLabel(device) {
    if (!device) {
      return "";
    }
    if (device.androidVersion) {
      return `Android ${device.androidVersion}`;
    }
    if (device.androidSdk) {
      return `API ${device.androidSdk}`;
    }
    return "";
  }

  function reconcileDeviceSelection() {
    if (state.devicesError) {
      return;
    }
    const exists = state.devices.some(
      (device) => device.serial === state.settings.selectedDevice
    );
    if (exists) {
      return;
    }
    const online = state.devices.filter((device) => device.state === "device");
    const nextSerial = online.length === 1 ? online[0].serial : "";
    if (nextSerial !== state.settings.selectedDevice) {
      state.settings.selectedDevice = nextSerial;
      markSettingsChanged({ hint: false });
    }
  }

  function selectDevice(serial) {
    if (!serial || serial === state.settings.selectedDevice) {
      return;
    }
    state.settings.selectedDevice = serial;
    markSettingsChanged();
    renderDevices();
    syncAllControls();
    updateCapabilityBanner();
    updateGroupBadges();
    updateCommandPreview();
  }

  function renderDeviceStatus() {
    const online = state.devices.filter((device) => device.state === "device").length;
    if (state.devicesLoading) {
      dom.deviceStatusLine.textContent = "正在扫描 adb 设备…";
    } else if (state.devicesError) {
      dom.deviceStatusLine.textContent = "设备扫描失败";
    } else if (state.devices.length === 0) {
      dom.deviceStatusLine.textContent = "没有发现设备，请连接 USB 或添加无线调试地址。";
    } else {
      dom.deviceStatusLine.textContent = `${online} 台在线 · 共 ${state.devices.length} 台设备`;
    }
    dom.refreshDevicesButton.classList.toggle(
      "is-spinning",
      Boolean(state.devicesLoading)
    );
    dom.refreshDevicesButton.disabled = Boolean(state.devicesLoading);
  }

  function makeEmptyDeviceState(title, text, isError = false) {
    const wrapper = document.createElement("div");
    wrapper.className = `empty-state${isError ? " device-error" : ""}`;
    wrapper.innerHTML = `${svgIcon("i-usb")}<strong></strong><p></p>`;
    wrapper.querySelector("strong").textContent = title;
    wrapper.querySelector("p").textContent = text;
    return wrapper;
  }

  function renderDevices() {
    dom.deviceList.replaceChildren();

    if (state.devicesLoading && state.devices.length === 0) {
      for (let i = 0; i < 2; i += 1) {
        const skeleton = document.createElement("div");
        skeleton.className = "device-skeleton";
        skeleton.innerHTML =
          '<span class="skeleton-line skeleton-wide"></span><span class="skeleton-line skeleton-short"></span>';
        dom.deviceList.append(skeleton);
      }
      return;
    }

    if (state.devicesError) {
      dom.deviceList.append(
        makeEmptyDeviceState(
          "无法读取设备",
          state.devicesError,
          true
        )
      );
      return;
    }

    if (state.devices.length === 0) {
      dom.deviceList.append(
        makeEmptyDeviceState(
          "没有发现 adb 设备",
          "用 USB 连接并开启 USB 调试，或在下方的「无线调试连接」中输入地址。"
        )
      );
      return;
    }

    for (const device of state.devices) {
      const fragment = dom.deviceTemplate.content.cloneNode(true);
      const card = fragment.querySelector(".device-card");
      card.dataset.serial = device.serial;
      card.setAttribute(
        "aria-pressed",
        device.serial === state.settings.selectedDevice ? "true" : "false"
      );
      card.classList.toggle(
        "is-selected",
        device.serial === state.settings.selectedDevice
      );
      card.classList.toggle("is-offline", device.state !== "device");
      card.classList.toggle("is-wireless", device.connection === "wireless");

      fragment.querySelector(".device-name").textContent = deviceDisplayName(device);
      const connectionBadge = fragment.querySelector(".connection-badge");
      connectionBadge.textContent = device.connection === "wireless" ? "Wi-Fi" : "USB";
      fragment.querySelector(".device-serial").textContent = device.serial;

      const details = fragment.querySelector(".device-details");
      const detailBits = [
        device.manufacturer,
        deviceAndroidLabel(device),
        device.state === "device" ? "在线" : DEVICE_STATE_LABELS[device.state] || device.state,
      ].filter(Boolean);
      for (const text of detailBits) {
        const span = document.createElement("span");
        span.textContent = text;
        details.append(span);
      }

      const hint = fragment.querySelector(".device-state-hint");
      let hintText = "";
      if (device.state === "unauthorized") {
        hintText = "请在设备上点击「允许 USB 调试」，然后刷新。";
      } else if (device.state === "offline") {
        hintText = "设备离线。检查连接，或重新执行 adb connect。";
      } else if (device.state === "no permissions") {
        hintText = "当前用户没有访问该设备的权限。";
      } else if (device.state !== "device") {
        hintText = "设备当前不可用。";
      }
      if (hintText) {
        hint.textContent = hintText;
        hint.classList.add("is-visible");
      }

      const disconnect = fragment.querySelector(".device-disconnect");
      disconnect.setAttribute("aria-label", `断开无线设备 ${device.serial}`);
      dom.deviceList.append(fragment);
    }
  }

  function handleAdbResult(message) {
    dom.connectDeviceButton.disabled = false;
    dom.connectDeviceButton.textContent = "连接";
    if (message.action === "connect") {
      if (message.address) {
        dom.wirelessAddress.value = message.address;
        state.settings.wirelessAddress = message.address;
        markSettingsChanged({ hint: false });
      }
      if (message.ok) {
        showToast("无线连接成功，正在刷新设备…", "success");
      } else {
        showToast(message.message || "连接失败", "error", 5000);
      }
    } else if (message.action === "disconnect") {
      if (message.ok) {
        showToast("已断开无线设备", "success");
      } else {
        showToast(message.message || "断开失败", "error");
      }
    }
  }

  function connectWirelessDevice() {
    const address = dom.wirelessAddress.value.trim();
    if (!/^[A-Za-z0-9][A-Za-z0-9.\-]*(?::\d{1,5})?$/.test(address)) {
      showToast("地址格式不正确，示例：192.168.5.60:5555", "warning");
      dom.wirelessAddress.focus();
      return;
    }
    if (!state.helloReceived) {
      showToast("后端尚未连接", "error");
      return;
    }
    state.settings.wirelessAddress = address;
    markSettingsChanged({ hint: false });
    dom.connectDeviceButton.disabled = true;
    dom.connectDeviceButton.textContent = "连接中…";
    if (!sendMessage({ type: "adb_connect", address })) {
      dom.connectDeviceButton.disabled = false;
      dom.connectDeviceButton.textContent = "连接";
      showToast("消息发送失败", "error");
      return;
    }
    window.setTimeout(() => {
      if (dom.connectDeviceButton.disabled) {
        dom.connectDeviceButton.disabled = false;
        dom.connectDeviceButton.textContent = "连接";
      }
    }, 25000);
  }

  function disconnectWirelessDevice(serial) {
    if (!serial) {
      return;
    }
    showToast("正在断开无线设备…");
    sendMessage({ type: "adb_disconnect", serial });
  }

  // -----------------------------------------------------------------------
  // Named configurations / last run
  // -----------------------------------------------------------------------

  function generateProfileId() {
    if (window.crypto?.randomUUID) {
      return `cfg_${window.crypto.randomUUID().replace(/-/g, "").slice(0, 18)}`;
    }
    return `cfg_${Date.now().toString(36)}_${Math.random()
      .toString(36)
      .slice(2, 8)}`;
  }

  function snapshotOptions() {
    const options = {};
    for (const option of OPTIONS) {
      options[option.id] = state.settings.options[option.id];
    }
    return options;
  }

  function currentProfileFields() {
    const device = selectedDeviceObject();
    const argv = buildArgv();
    return {
      selectedDevice: state.settings.selectedDevice || "",
      deviceLabel: device ? deviceDisplayName(device) : "",
      command: commandString(argv),
      optionCount: Math.max(0, argv.length - 1),
      extraArgs: state.settings.extraArgs || "",
    };
  }

  function formatRelativeTime(timestamp) {
    if (!timestamp) {
      return "未记录时间";
    }
    const diff = Math.max(0, Date.now() - timestamp);
    if (diff < 60_000) {
      return "刚刚";
    }
    if (diff < 3_600_000) {
      return `${Math.floor(diff / 60_000)} 分钟前`;
    }
    if (diff < 86_400_000) {
      return `${Math.floor(diff / 3_600_000)} 小时前`;
    }
    if (diff < 7 * 86_400_000) {
      return `${Math.floor(diff / 86_400_000)} 天前`;
    }
    return new Date(timestamp).toLocaleDateString("zh-CN");
  }

  function profileDeviceLabel(profile) {
    return profile.deviceLabel || profile.selectedDevice || "当前设备";
  }

  function makeProfileCard(profile, { last = false } = {}) {
    const card = document.createElement("article");
    card.className = `profile-card${last ? " is-last" : ""}`;
    card.dataset.profileId = profile.id;
    card.tabIndex = 0;
    card.setAttribute("role", "group");
    card.setAttribute(
      "aria-label",
      `${profile.name}，右键恢复，双击运行`
    );
    card.innerHTML = `
      <span class="profile-icon">${svgIcon(last ? "i-history" : "i-save")}</span>
      <span class="profile-main">
        <span class="profile-title-row">
          <strong class="profile-name"></strong>
          ${last ? '<span class="profile-badge">自动</span>' : ""}
        </span>
        <p class="profile-meta"></p>
      </span>
      <span class="profile-tools">
        <button class="profile-action profile-restore" type="button" title="恢复配置（不执行）" aria-label="恢复配置">${svgIcon("i-restore")}</button>
        <button class="profile-action profile-run" type="button" title="直接运行此配置" aria-label="直接运行此配置">${svgIcon("i-play")}</button>
        ${
          last
            ? ""
            : `<button class="profile-delete" type="button" title="删除配置" aria-label="删除配置">${svgIcon("i-close")}</button>`
        }
      </span>
    `;
    card.querySelector(".profile-name").textContent = profile.name;
    card.querySelector(".profile-main").dataset.tooltip =
      `${profile.name}\n${last ? "上次运行命令" : "保存时命令"}：\n` +
      `${profile.command || "（没有记录命令）"}\n\n` +
      "右键恢复（不执行） · 双击直接运行";
    const metaParts = [
      `${profile.optionCount || 0} 个参数`,
      profileDeviceLabel(profile),
      formatRelativeTime(profile.updatedAt),
    ];
    card.querySelector(".profile-meta").textContent = metaParts.join(" · ");

    card.querySelector(".profile-restore").addEventListener("click", (event) => {
      event.stopPropagation();
      applyProfile(profile, { execute: false });
    });
    card.querySelector(".profile-run").addEventListener("click", (event) => {
      event.stopPropagation();
      applyProfile(profile, { execute: true });
    });
    card.querySelector(".profile-delete")?.addEventListener("click", (event) => {
      event.stopPropagation();
      deleteProfile(profile);
    });

    card.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (event.target.closest("button")) {
        return;
      }
      applyProfile(profile, { execute: false });
    });
    card.addEventListener("dblclick", (event) => {
      if (event.target.closest("button")) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      applyProfile(profile, { execute: true });
    });
    card.addEventListener("keydown", (event) => {
      if (event.target.closest("button")) {
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault();
        applyProfile(profile, { execute: event.ctrlKey });
      }
    });
    return card;
  }

  function renderProfiles() {
    if (!dom.profileList) {
      return;
    }
    dom.profileList.replaceChildren();
    const lastProfile = state.settings.lastProfile;
    const named = [...state.settings.profiles].sort(
      (a, b) => (b.updatedAt || 0) - (a.updatedAt || 0)
    );
    if (!lastProfile && named.length === 0) {
      const empty = document.createElement("div");
      empty.className = "profile-empty";
      empty.innerHTML =
        "<strong>还没有保存的配置</strong>调整好参数后点「保存当前」，之后右键恢复或双击运行。";
      dom.profileList.append(empty);
      return;
    }
    if (lastProfile) {
      dom.profileList.append(makeProfileCard(lastProfile, { last: true }));
    }
    for (const profile of named) {
      dom.profileList.append(makeProfileCard(profile));
    }
  }

  function nextProfileName() {
    const names = new Set(state.settings.profiles.map((profile) => profile.name));
    let index = 1;
    while (names.has(`配置 ${index}`)) {
      index += 1;
    }
    return `配置 ${index}`;
  }

  function profileNameOptions() {
    return [...state.settings.profiles]
      .filter((profile) => profile?.name && profile.name !== "上一次")
      .sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
  }

  function closeProfileNameMenu() {
    if (!dom.profileNameMenu) {
      return;
    }
    dom.profileNameMenu.hidden = true;
    dom.profileNameInput.setAttribute("aria-expanded", "false");
  }

  function updateProfileNameState() {
    const name = dom.profileNameInput.value.trim();
    const existing = state.settings.profiles.find(
      (profile) => profile.name === name
    );
    dom.profileOverwriteHint.hidden = !existing;
    dom.profileOverwriteHint.textContent = existing
      ? `已存在，将覆盖「${existing.name}」的已保存参数。`
      : "";
    dom.profileDialogSaveButton.textContent = existing
      ? "覆盖保存"
      : "保存配置";
  }

  function openProfileNameMenu() {
    if (dom.profileNameToggle.disabled) {
      return;
    }
    const profiles = profileNameOptions();
    const menu = dom.profileNameMenu;
    menu.replaceChildren();

    const hint = document.createElement("div");
    hint.className = "profile-name-menu-hint";
    hint.textContent = "选择已有配置以覆盖，或直接输入新名称";
    menu.append(hint);

    if (profiles.length === 0) {
      const empty = document.createElement("div");
      empty.className = "profile-name-empty";
      empty.textContent = "还没有已保存的配置";
      menu.append(empty);
    }

    const currentName = dom.profileNameInput.value.trim();
    for (const profile of profiles) {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "profile-name-item";
      item.setAttribute("role", "option");
      item.setAttribute(
        "aria-selected",
        profile.name === currentName ? "true" : "false"
      );
      if (profile.name === currentName) {
        item.classList.add("is-selected");
      }

      const label = document.createElement("span");
      label.className = "profile-name-label";
      label.textContent = profile.name;
      const meta = document.createElement("span");
      meta.className = "profile-name-meta";
      const parts = [];
      if (profile.deviceLabel) {
        parts.push(profile.deviceLabel);
      }
      if (profile.optionCount) {
        parts.push(`${profile.optionCount} 个参数`);
      }
      meta.textContent = parts.join(" · ");
      item.append(label, meta);
      item.addEventListener("mousedown", (event) => {
        event.preventDefault();
      });
      item.addEventListener("click", () => {
        dom.profileNameInput.value = profile.name;
        dom.profileNameError.textContent = "";
        updateProfileNameState();
        closeProfileNameMenu();
        dom.profileNameInput.focus();
      });
      menu.append(item);
    }

    menu.hidden = false;
    dom.profileNameInput.setAttribute("aria-expanded", "true");
    const selected = menu.querySelector(".profile-name-item.is-selected");
    if (selected) {
      window.requestAnimationFrame(() => {
        selected.scrollIntoView({ block: "nearest" });
      });
    }
  }

  function toggleProfileNameMenu() {
    if (dom.profileNameMenu.hidden) {
      openProfileNameMenu();
    } else {
      closeProfileNameMenu();
    }
  }

  function askProfileName(defaultName) {
    if (state.profileDialogResolver) {
      return Promise.resolve(null);
    }
    closeProfileNameMenu();
    dom.profileNameInput.value = defaultName;
    dom.profileNameError.textContent = "";
    updateProfileNameState();
    const profiles = profileNameOptions();
    dom.profileNameToggle.disabled = profiles.length === 0;
    dom.profileNameToggle.title =
      profiles.length > 0
        ? "选择已有配置以覆盖"
        : "还没有已保存的配置";
    dom.profileDialog.returnValue = "cancel";
    dom.profileDialog.showModal();
    window.setTimeout(() => {
      dom.profileNameInput.focus();
      dom.profileNameInput.select();
    }, 20);
    return new Promise((resolve) => {
      state.profileDialogResolver = resolve;
    });
  }

  function commitProfileName() {
    closeProfileNameMenu();
    const name = dom.profileNameInput.value.trim();
    if (!name) {
      dom.profileNameError.textContent = "请为配置填写一个名称。";
      dom.profileNameInput.focus();
      return;
    }
    if (name === "上一次") {
      dom.profileNameError.textContent = "「上一次」是自动配置的保留名称，请换一个。";
      dom.profileNameInput.focus();
      return;
    }
    dom.profileDialog.returnValue = "ok";
    dom.profileDialog.close();
  }

  async function saveCurrentProfile() {
    if (!state.helloReceived) {
      showToast("后端尚未连接，暂时不能保存配置", "warning");
      return;
    }
    const name = await askProfileName(nextProfileName());
    if (!name) {
      return;
    }
    let existing = state.settings.profiles.find(
      (profile) => profile.name === name
    );
    if (existing) {
      const confirmed = await askConfirm(
        "覆盖同名配置？",
        `已经存在名为「${name}」的配置，保存会覆盖它当前保存的参数。`,
        "覆盖保存"
      );
      if (!confirmed) {
        return;
      }
    }
    if (!existing && state.settings.profiles.length >= 100) {
      showToast("最多保存 100 个配置，请先删除旧配置", "warning", 5000);
      return;
    }
    const fields = currentProfileFields();
    const now = Date.now();
    const profile = {
      id: existing?.id || generateProfileId(),
      name,
      createdAt: existing?.createdAt || now,
      updatedAt: now,
      selectedDevice: fields.selectedDevice,
      deviceLabel: fields.deviceLabel,
      command: fields.command,
      optionCount: fields.optionCount,
      options: snapshotOptions(),
      extraArgs: fields.extraArgs,
      argv: [],
    };
    if (existing) {
      state.settings.profiles = state.settings.profiles.map((item) =>
        item.id === existing.id ? profile : item
      );
    } else {
      state.settings.profiles = [profile, ...state.settings.profiles];
    }
    renderProfiles();
    markSettingsChanged();
    showToast(
      existing ? `已覆盖配置「${name}」` : `已保存配置「${name}」`,
      "success"
    );
  }

  async function deleteProfile(profile) {
    if (!profile || profile.id === "last") {
      return;
    }
    const confirmed = await askConfirm(
      "删除这个配置？",
      `「${profile.name}」及其保存的参数会被删除，此操作不会影响当前界面。`,
      "删除"
    );
    if (!confirmed) {
      return;
    }
    state.settings.profiles = state.settings.profiles.filter(
      (item) => item.id !== profile.id
    );
    renderProfiles();
    markSettingsChanged();
    showToast(`已删除配置「${profile.name}」`, "success");
  }

  function applyProfile(profile, { execute = false } = {}) {
    if (!profile) {
      return;
    }
    state.settings.options = normalizeOptions(profile.options);
    state.settings.extraArgs = profile.extraArgs || "";
    let deviceMissing = false;
    let targetDevice = null;
    if (profile.selectedDevice) {
      targetDevice =
        state.devices.find((device) => device.serial === profile.selectedDevice) ||
        null;
      if (targetDevice) {
        state.settings.selectedDevice = profile.selectedDevice;
      } else {
        deviceMissing = true;
      }
    }

    renderDevices();
    syncAllControls();
    syncExtraArgsInput();
    updateCapabilityBanner();
    updateGroupBadges();
    updateCommandPreview();
    markSettingsChanged();

    const name = profile.name;
    if (!execute) {
      showToast(
        deviceMissing
          ? `已恢复「${name}」，但保存的设备不在线；参数已生效`
          : `已恢复配置「${name}」（未执行）`,
        deviceMissing ? "warning" : "success",
        4200
      );
      return;
    }

    if (deviceMissing) {
      showToast(
        `已恢复「${name}」，但保存的设备不在线，未执行。请连接设备后手动运行。`,
        "warning",
        5600
      );
      return;
    }
    if (targetDevice && targetDevice.state !== "device") {
      showToast(
        `已恢复「${name}」，但保存的设备当前不可用，未执行。`,
        "warning",
        5000
      );
      return;
    }
    if (state.running || state.starting) {
      showToast(
        `已恢复「${name}」；scrcpy 正在运行，停止后可手动运行。`,
        "warning",
        4800
      );
      return;
    }
    runScrcpy();
  }

  function rememberLastRun(snapshot) {
    if (!snapshot) {
      return;
    }
    const now = Date.now();
    const previous = state.settings.lastProfile;
    state.settings.lastProfile = {
      id: "last",
      name: "上一次",
      createdAt: previous?.createdAt || now,
      updatedAt: now,
      selectedDevice: snapshot.selectedDevice || "",
      deviceLabel: snapshot.deviceLabel || "",
      command: snapshot.command || "",
      optionCount: snapshot.optionCount || 0,
      options: snapshot.options,
      extraArgs: snapshot.extraArgs || "",
      argv: Array.isArray(snapshot.argv) ? snapshot.argv : [],
    };
    renderProfiles();
    markSettingsChanged({ hint: false });
  }

  function handleProfileDialogClose() {
    closeProfileNameMenu();
    const resolver = state.profileDialogResolver;
    state.profileDialogResolver = null;
    if (!resolver) {
      return;
    }
    const name = dom.profileNameInput.value.trim();
    resolver(
      dom.profileDialog.returnValue === "ok" && name ? name : null
    );
  }

  // -----------------------------------------------------------------------
  // Capabilities / banners
  // -----------------------------------------------------------------------

  function supportedArg(flag) {
    const supported = state.tools?.supportedArgs;
    if (!Array.isArray(supported) || supported.length === 0) {
      return true;
    }
    return supported.includes(flag);
  }

  function minSdkLabel(sdk) {
    const version = ANDROID_NAMES[sdk];
    return version ? `Android ${version}` : `API ${sdk}`;
  }

  function minSdkShortLabel(sdk) {
    const version = ANDROID_NAMES[sdk];
    return version ? `${version}+` : `API ${sdk}+`;
  }

  function choiceAllowed(choice) {
    const sdk = deviceSdk();
    if (choice.minSdk && sdk !== null && sdk < choice.minSdk) {
      return false;
    }
    return true;
  }

  function optionValueIsActive(option, value = state.settings.options[option.id]) {
    if (option.type === "toggle") {
      return Boolean(value);
    }
    if (option.type === "select") {
      return (
        value != null &&
        String(value) !== "" &&
        String(value) !== String(option.default)
      );
    }
    if (option.type === "combo") {
      const normalized = normalizeComboValue(option, value);
      return (
        normalized !== "" &&
        normalized !== normalizeComboValue(option, option.default)
      );
    }
    return String(value ?? "").trim() !== "";
  }

  function requiredSdkForOptionValue(option, value) {
    if (!optionValueIsActive(option, value)) {
      return 0;
    }
    let required = Number(option.minSdk) || 0;
    if (option.type === "select") {
      const choice = option.choices.find((item) => item.value === value);
      required = Math.max(required, Number(choice?.minSdk) || 0);
    }
    return required;
  }

  function getVersionWarning(option) {
    const sdk = deviceSdk();
    if (sdk === null) {
      return null;
    }
    const required = requiredSdkForOptionValue(
      option,
      state.settings.options[option.id]
    );
    if (!required || sdk >= required) {
      return null;
    }
    const device = selectedDeviceObject();
    const current = deviceAndroidLabel(device) || `API ${sdk}`;
    return {
      requiredSdk: required,
      label: minSdkLabel(required),
      message:
        `当前设备是 ${current}，这个设置需要 ${minSdkLabel(required)}+。` +
        "你的开关状态会保留，但本次运行会自动忽略该参数。",
    };
  }

  function getActiveVersionWarnings() {
    return OPTIONS.map((option) => ({
      option,
      warning: getVersionWarning(option),
    })).filter((item) => item.warning);
  }

  function virtualDisplayOption() {
    return OPTION_MAP.get("newDisplay");
  }

  function virtualDisplayActive() {
    const option = virtualDisplayOption();
    if (!option) {
      return false;
    }
    return (
      normalizeComboValue(option, state.settings.options.newDisplay) !== ""
    );
  }

  function displayIdActive() {
    const option = OPTION_MAP.get("displayId");
    if (!option) {
      return false;
    }
    const value = String(state.settings.options.displayId ?? "").trim();
    return value !== "" && value !== "0" && value !== String(option.default ?? "");
  }

  function getDisabledReason(option) {
    if (!state.helloReceived) {
      return "正在加载设置…";
    }
    const sdk = deviceSdk();
    if (option.id === "hwdec" && option.flag && !supportedArg(option.flag)) {
      return "硬件解码需要 scrcpy 5.0+（当前版本没有 --hwdec）";
    }
    if (option.flag && !supportedArg(option.flag)) {
      return "当前 scrcpy 版本不支持此参数";
    }
    if (option.id === "newDisplay" && displayIdActive()) {
      return "已填写「镜像显示 ID」，两者互斥";
    }
    if (option.id === "displayId" && virtualDisplayActive()) {
      return "已开启「虚拟显示尺寸」，两者互斥";
    }
    if (option.id === "hwdec" && state.settings.options.noWindow) {
      return "「无窗口运行」没有视频播放，硬件解码不可用";
    }
    if (option.requiresVirtualDisplay) {
      if (sdk !== null && sdk < 29) {
        return "虚拟显示需要 Android 10+";
      }
      if (!virtualDisplayActive()) {
        return "需要先设置「虚拟显示尺寸」";
      }
    }
    if (
      option.id === "displayOrientation" &&
      String(state.settings.options.orientation ?? "0") !== "0"
    ) {
      return "已被「整体方向」覆盖（--orientation 会同时设置预览与录制）";
    }
    if (option.minSdk && sdk !== null && sdk < option.minSdk) {
      return `需要 ${minSdkLabel(option.minSdk)}+`;
    }
    if (option.requiresRecord && !String(state.settings.options.record || "").trim()) {
      return "请先填写录制文件";
    }
    if (option.requires) {
      const otherValue = state.settings.options[option.requires.option];
      if (otherValue !== option.requires.equals) {
        if (option.requires.option === "noAudio") {
          return "需要开启声音转发";
        }
        if (option.requires.option === "videoSource") {
          return "需要先切换到摄像头模式";
        }
        if (option.requires.option === "audioSource") {
          return "需要声音来源选择「应用播放」";
        }
        return "当前选项不适用";
      }
    }
    return "";
  }

  function isOptionActive(option) {
    return !getDisabledReason(option) && !getVersionWarning(option);
  }

  function updateCapabilityBanner() {
    const banner = dom.capabilityBanner;
    banner.classList.remove("is-warning", "is-danger", "is-ok");
    const device = selectedDeviceObject();
    const sdk = deviceSdk();

    if (!state.helloReceived) {
      dom.capabilityTitle.textContent = "正在等待后端";
      dom.capabilityText.textContent = "连接后会读取 scrcpy 参数表和 adb 设备列表。";
      dom.capabilityBadge.textContent = "连接中";
      return;
    }
    if (!state.tools?.scrcpyPath) {
      banner.classList.add("is-danger");
      dom.capabilityTitle.textContent = "找不到 scrcpy";
      dom.capabilityText.textContent = "请确认 scrcpy 已加入 PATH，然后重启程序。";
      dom.capabilityBadge.textContent = "不可运行";
      return;
    }
    if (state.devicesError) {
      banner.classList.add("is-danger");
      dom.capabilityTitle.textContent = "设备列表读取失败";
      dom.capabilityText.textContent = state.devicesError;
      dom.capabilityBadge.textContent = "检查 adb";
      return;
    }
    if (!device) {
      banner.classList.add("is-warning");
      dom.capabilityTitle.textContent = "尚未选择设备";
      dom.capabilityText.textContent =
        state.devices.length > 1
          ? "左侧有多台设备，请选择一台在线设备后再运行。"
          : "连接设备后，这里会根据 Android 版本说明可用能力。";
      dom.capabilityBadge.textContent = "等待设备";
      return;
    }
    if (device.state !== "device") {
      banner.classList.add("is-danger");
      dom.capabilityTitle.textContent = `${deviceDisplayName(device)} · ${
        DEVICE_STATE_LABELS[device.state] || device.state
      }`;
      dom.capabilityText.textContent =
        device.state === "unauthorized"
          ? "请在设备上允许 USB 调试，然后点击右上角刷新。"
          : "设备当前不可用，请检查连接后刷新。";
      dom.capabilityBadge.textContent = "不可运行";
      return;
    }

    const name = deviceDisplayName(device);
    const android = deviceAndroidLabel(device);
    let baseText;
    let badgeText;
    if (sdk !== null && sdk < 30) {
      banner.classList.add("is-warning");
      baseText =
        "屏幕镜像可用；此版本不支持音频转发，摄像头模式需要 Android 12+。";
      badgeText = "基础能力";
    } else if (sdk !== null && sdk < 31) {
      banner.classList.add("is-warning");
      baseText =
        "屏幕镜像与声音可用；摄像头采集需要 Android 12+，相关开关会自动禁用。";
      badgeText = "部分能力";
    } else {
      banner.classList.add("is-ok");
      baseText = "设备已就绪，屏幕、声音与摄像头参数均可使用。";
      badgeText = "全部能力";
    }

    const warnings = getActiveVersionWarnings();
    if (warnings.length > 0) {
      banner.classList.remove("is-ok");
      banner.classList.add("is-warning");
      const labels = [
        ...new Set(
          [...warnings]
            .sort((a, b) => a.warning.requiredSdk - b.warning.requiredSdk)
            .map((item) => item.warning.label)
        ),
      ].join(" / ");
      baseText += ` 有 ${warnings.length} 个已开启参数需要 ${labels}，设置会保留，但运行时自动跳过。`;
      badgeText = `${warnings.length} 项警告`;
    }

    dom.capabilityTitle.textContent = `${name} · ${android || `API ${sdk}`}`;
    dom.capabilityText.textContent = baseText;
    dom.capabilityBadge.textContent = badgeText;
  }

  function updateGroupBadges() {
    const sdk = deviceSdk();
    const cameraGroup = document.querySelector(
      '.option-group[data-group="camera"]'
    );
    const audioGroup = document.querySelector('.option-group[data-group="audio"]');
    if (cameraGroup) {
      const badge = cameraGroup.querySelector(".group-badge");
      const note = cameraGroup.querySelector(".group-note");
      let text = "";
      if (sdk !== null && sdk < 31) {
        text = "需要 Android 12+";
      } else if (!supportedArg("--video-source")) {
        text = "scrcpy 不支持";
      }
      badge.textContent = text;
      badge.classList.toggle("is-visible", Boolean(text));
      note.textContent = text
        ? "当前设备不支持摄像头采集；已保存的摄像头设置会保留，但不会执行"
        : GROUP_MAP.get("camera").note;
    }
    if (audioGroup) {
      const badge = audioGroup.querySelector(".group-badge");
      const note = audioGroup.querySelector(".group-note");
      const text =
        sdk !== null && sdk < 30 ? "此设备不支持音频" : "";
      badge.textContent = text;
      badge.classList.toggle("is-visible", Boolean(text));
      note.textContent = text
        ? "Android 11 以下没有音频转发能力；相关设置会保留并标记为跳过"
        : GROUP_MAP.get("audio").note;
    }
  }

  // -----------------------------------------------------------------------
  // Option UI
  // -----------------------------------------------------------------------

  function bindComboInput(option, input) {
    input.addEventListener("input", () => {
      state.settings.options[option.id] = input.value;
      afterOptionChanged(option, { debounce: true });
    });
    const commit = () => {
      const normalized = normalizeComboValue(option, input.value);
      state.settings.options[option.id] = normalized;
      input.value = normalized;
      afterOptionChanged(option, { debounce: false });
    };
    input.addEventListener("change", commit);
    input.addEventListener("blur", commit);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        input.blur();
      }
    });
  }

  function decorateSegmentButton(button, label, isDefault) {
    const clean = label.replace(/（默认）\s*$/, "").trim();
    const text = document.createElement("span");
    text.className = "segment-label";
    text.textContent = clean;
    button.append(text);
    if (isDefault) {
      const badge = document.createElement("span");
      badge.className = "segment-default-badge";
      badge.textContent = "默认";
      badge.setAttribute("aria-hidden", "true");
      button.append(badge);
      button.setAttribute("aria-label", `${clean}（默认）`);
    } else {
      button.setAttribute("aria-label", clean);
    }
  }

  function buildOptionRow(option) {
    const row = document.createElement("div");
    row.className = "option-row";
    row.dataset.option = option.id;
    row.innerHTML = `
      <div class="option-copy">
        <div class="option-title-row">
          <span class="option-title"></span>
          <code class="arg-chip"></code>
          <button class="version-warning" type="button" aria-label="Android 版本警告" hidden>${svgIcon("i-alert")}</button>
        </div>
        <p class="option-short"></p>
        <p class="option-lock"></p>
      </div>
      <div class="option-control"></div>
    `;
    const title = row.querySelector(".option-title");
    const shortText = row.querySelector(".option-short");
    title.textContent = option.title;
    shortText.textContent = option.short;
    title.dataset.tooltip = option.detail;
    shortText.dataset.tooltip = option.detail;

    const argChip = row.querySelector(".arg-chip");
    argChip.textContent =
      option.type === "toggle" ? option.arg : `${option.flag}=…`;
    argChip.dataset.tooltip = option.detail;

    const control = row.querySelector(".option-control");
    if (option.type === "toggle") {
      const wrap = document.createElement("div");
      wrap.className = "switch-wrap";
      const button = document.createElement("button");
      button.type = "button";
      button.className = "switch";
      button.setAttribute("role", "switch");
      button.setAttribute("aria-label", option.title);
      button.addEventListener("click", () => {
        if (button.disabled) {
          return;
        }
        state.settings.options[option.id] = !state.settings.options[option.id];
        afterOptionChanged(option);
      });
      const text = document.createElement("span");
      text.className = "switch-state";
      wrap.append(button, text);
      control.append(wrap);
    } else if (option.type === "select" && option.choices.length <= 4) {
      const wrap = document.createElement("div");
      wrap.className = "segmented";
      for (const choice of option.choices) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "segmented-button";
        button.dataset.value = choice.value;
        decorateSegmentButton(
          button,
          choice.label,
          choice.value === option.default
        );
        button.title = choice.label;
        button.setAttribute("aria-pressed", "false");
        button.addEventListener("click", () => {
          if (button.disabled) {
            return;
          }
          state.settings.options[option.id] = choice.value;
          afterOptionChanged(option);
        });
        wrap.append(button);
      }
      control.append(wrap);
    } else if (option.type === "select") {
      const wrap = document.createElement("div");
      wrap.className = "custom-select-wrap";
      const button = document.createElement("button");
      button.type = "button";
      button.className = "custom-select";
      button.setAttribute("aria-label", option.title);
      button.setAttribute("aria-haspopup", "listbox");
      button.setAttribute("aria-expanded", "false");
      const label = document.createElement("span");
      label.className = "custom-select-label";
      const chevron = document.createElement("span");
      chevron.className = "custom-select-chevron";
      chevron.innerHTML = svgIcon("i-chevron");
      button.append(label, chevron);
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        openSelectMenu(button, option);
      });
      button.addEventListener("keydown", (event) => {
        if (event.key === "ArrowDown") {
          event.preventDefault();
          openSelectMenu(button, option);
        } else if (event.key === "Escape") {
          hideComboMenu();
        }
      });
      wrap.append(button);
      control.append(wrap);
    } else if (option.type === "combo" && option.quick) {
      const wrap = document.createElement("div");
      wrap.className = "quick-combo";
      const buttonGroup = document.createElement("div");
      buttonGroup.className = "quick-buttons";
      for (const preset of option.quickPresets || []) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "quick-button";
        button.dataset.value = preset.value;
        decorateSegmentButton(
          button,
          preset.label,
          preset.value === option.default
        );
        button.title = preset.label;
        button.setAttribute("aria-pressed", "false");
        button.addEventListener("click", () => {
          if (button.disabled) {
            return;
          }
          state.settings.options[option.id] = preset.value;
          afterOptionChanged(option, { debounce: false });
        });
        buttonGroup.append(button);
      }
      wrap.append(buttonGroup);
      control.append(wrap);
    } else if (option.type === "combo") {
      const wrap = document.createElement("div");
      wrap.className = "combo-wrap";
      const input = document.createElement("input");
      input.type = "text";
      input.className = "combo-input";
      input.setAttribute("aria-label", option.title);
      input.autocomplete = "off";
      input.spellcheck = false;
      input.inputMode =
        option.comboKind === "size" ? "numeric" : "text";
      if (option.placeholder) {
        input.placeholder = option.placeholder;
      }
      input.title = "可从右侧选择预设，也可以直接输入";
      bindComboInput(option, input);

      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "combo-toggle";
      toggle.setAttribute("aria-label", `选择${option.title}预设`);
      toggle.setAttribute("aria-haspopup", "listbox");
      toggle.innerHTML = svgIcon("i-chevron");
      toggle.addEventListener("click", (event) => {
        event.stopPropagation();
        openComboMenu(input, option);
      });
      input.addEventListener("keydown", (event) => {
        if (event.key === "ArrowDown") {
          event.preventDefault();
          openComboMenu(input, option);
        } else if (event.key === "Escape") {
          hideComboMenu();
        }
      });
      wrap.append(input, toggle);
      control.append(wrap);
    } else {
      const holder = document.createElement("div");
      holder.className = option.unit ? "unit-input" : "";
      const input = document.createElement("input");
      input.type = option.type === "number" ? "number" : "text";
      input.className =
        option.type === "number" ? "number-input" : "text-input";
      input.setAttribute("aria-label", option.title);
      input.autocomplete = "off";
      input.spellcheck = false;
      if (option.placeholder) {
        input.placeholder = option.placeholder;
      }
      if (option.type === "number") {
        input.inputMode = "decimal";
        if (option.min !== undefined) {
          input.min = String(option.min);
        }
        if (option.max !== undefined) {
          input.max = String(option.max);
        }
        if (option.step !== undefined) {
          input.step = String(option.step);
        }
      }
      input.addEventListener("input", () => {
        state.settings.options[option.id] = input.value;
        afterOptionChanged(option);
      });
      holder.append(input);
      if (option.unit) {
        const unit = document.createElement("span");
        unit.className = "unit";
        unit.textContent = option.unit;
        holder.append(unit);
      }
      control.append(holder);
    }
    return row;
  }

  function buildOptionGroups() {
    hideComboMenu();
    dom.optionsRoot.replaceChildren();
    GROUPS.forEach((group) => {
      const section = document.createElement("section");
      section.className = "option-group";
      section.dataset.group = group.id;
      const header = document.createElement("button");
      header.type = "button";
      header.className = "option-group-header";
      header.innerHTML = `
        <span class="group-icon">${svgIcon(group.icon)}</span>
        <span class="group-heading-copy">
          <span class="group-title-line">
            <span class="group-title"></span>
            <span class="group-count"></span>
          </span>
          <span class="group-note"></span>
        </span>
        <span class="group-badge"></span>
        ${svgIcon("i-chevron", "icon chevron")}
      `;
      header.querySelector(".group-title").textContent = group.title;
      header.querySelector(".group-count").textContent = String(
        group.options.length
      );
      header.querySelector(".group-note").textContent = group.note;
      header.setAttribute("aria-expanded", "true");
      header.addEventListener("click", () => {
        if (state.search) {
          return;
        }
        toggleGroup(group.id);
      });
      const body = document.createElement("div");
      body.className = "option-group-body";
      for (const option of group.options) {
        body.append(buildOptionRow(option));
      }
      section.append(header, body);
      dom.optionsRoot.append(section);
    });
    applyCollapsedSections();
  }

  function applyCollapsedSections() {
    const collapsed = new Set(state.settings.collapsedSections);
    for (const section of dom.optionsRoot.querySelectorAll(".option-group")) {
      const isCollapsed = collapsed.has(section.dataset.group);
      section.classList.toggle("is-collapsed", isCollapsed);
      const header = section.querySelector(".option-group-header");
      header.setAttribute("aria-expanded", isCollapsed ? "false" : "true");
    }
  }

  function toggleGroup(groupId) {
    const set = new Set(state.settings.collapsedSections);
    if (set.has(groupId)) {
      set.delete(groupId);
    } else {
      set.add(groupId);
    }
    state.settings.collapsedSections = [...set];
    applyCollapsedSections();
    markSettingsChanged();
  }

  function afterOptionChanged(option, settings = {}) {
    state.settings.options[option.id] = normalizeOptionValue(
      option,
      state.settings.options[option.id]
    );
    syncAllControls();
    updateCommandPreview();
    updateCapabilityBanner();
    updateGroupBadges();
    markSettingsChanged({
      debounce:
        settings.debounce ??
        (option.type === "text" ||
          option.type === "number" ||
          option.type === "combo"),
    });
  }

  function syncAllControls() {
    for (const option of OPTIONS) {
      const row = dom.optionsRoot.querySelector(
        `.option-row[data-option="${option.id}"]`
      );
      if (!row) {
        continue;
      }
      const reason = getDisabledReason(option);
      const disabled = Boolean(reason);
      const versionWarning = getVersionWarning(option);
      row.classList.toggle("is-disabled", disabled);
      row.classList.toggle("has-version-warning", Boolean(versionWarning));
      row.querySelector(".option-lock").textContent =
        reason ||
        (versionWarning
          ? `需要 ${versionWarning.label}+；本次运行会忽略此参数`
          : "");

      const warningButton = row.querySelector(".version-warning");
      warningButton.hidden = !versionWarning;
      if (versionWarning) {
        warningButton.dataset.tooltip = versionWarning.message;
        warningButton.setAttribute(
          "aria-label",
          `需要 ${versionWarning.label}+，点击或悬停查看说明`
        );
      } else {
        warningButton.removeAttribute("data-tooltip");
      }

      const tooltipParts = [option.detail];
      if (reason) {
        tooltipParts.push(`当前不可用：${reason}`);
      }
      if (versionWarning) {
        tooltipParts.push(versionWarning.message);
      }
      const tooltip = tooltipParts.join("\n\n");
      row.querySelector(".option-title").dataset.tooltip = tooltip;
      row.querySelector(".option-short").dataset.tooltip = tooltip;
      row.querySelector(".arg-chip").dataset.tooltip = tooltip;

      if (option.type === "toggle") {
        const button = row.querySelector(".switch");
        const text = row.querySelector(".switch-state");
        const checked = Boolean(state.settings.options[option.id]);
        button.disabled = disabled;
        button.setAttribute("aria-checked", checked ? "true" : "false");
        text.textContent = checked ? "开启" : "关闭";
      } else if (
        option.type === "select" &&
        option.choices.length <= 4
      ) {
        const value = String(state.settings.options[option.id] ?? "");
        for (const button of row.querySelectorAll(".segmented-button")) {
          const choice = option.choices.find(
            (item) => item.value === button.dataset.value
          );
          const blocked = !choice || !choiceAllowed(choice);
          button.disabled = disabled || blocked;
          button.classList.toggle(
            "is-active",
            Boolean(choice) && choice.value === value
          );
          button.setAttribute(
            "aria-pressed",
            choice && choice.value === value ? "true" : "false"
          );
          if (choice) {
            button.title = blocked
              ? `${choice.label}（需 ${minSdkShortLabel(choice.minSdk)}）`
              : choice.label;
          }
        }
      } else if (option.type === "select") {
        const button = row.querySelector(".custom-select");
        const value = String(state.settings.options[option.id] ?? "");
        const choice = option.choices.find(
          (candidate) => candidate.value === value
        );
        button.disabled = disabled;
        button.setAttribute(
          "aria-expanded",
          comboMenuState?.anchor === button ? "true" : "false"
        );
        row.querySelector(".custom-select-label").textContent = choice
          ? choice.label
          : "";
      } else if (option.type === "combo" && option.quick) {
        const normalized = normalizeComboValue(
          option,
          state.settings.options[option.id]
        );
        for (const button of row.querySelectorAll(".quick-button")) {
          const active = button.dataset.value === normalized;
          button.disabled = disabled;
          button.classList.toggle("is-active", active);
          button.setAttribute("aria-pressed", active ? "true" : "false");
        }
      } else if (option.type === "combo") {
        const input = row.querySelector(".combo-input");
        input.disabled = disabled;
        const toggle = row.querySelector(".combo-toggle");
        toggle.disabled = disabled;
        if (document.activeElement !== input) {
          input.value = normalizeComboValue(
            option,
            state.settings.options[option.id]
          );
        }
      } else {
        const input = row.querySelector("input");
        input.disabled = disabled;
        if (document.activeElement !== input) {
          input.value = String(state.settings.options[option.id] ?? "");
        }
      }
    }
  }

  // -----------------------------------------------------------------------
  // Command construction
  // -----------------------------------------------------------------------

  function tokenizeExtraArgs(text) {
    const tokens = [];
    let current = "";
    let quote = "";
    let inToken = false;
    const source = String(text ?? "");
    for (let index = 0; index < source.length; index += 1) {
      const char = source[index];
      if (quote) {
        if (char === quote) {
          quote = "";
          continue;
        }
        if (
          char === "\\" &&
          quote === '"' &&
          index + 1 < source.length &&
          (source[index + 1] === '"' || source[index + 1] === "\\")
        ) {
          index += 1;
          current += source[index];
          continue;
        }
        current += char;
        continue;
      }
      if (char === '"' || char === "'") {
        quote = char;
        inToken = true;
        continue;
      }
      if (/\s/.test(char)) {
        if (inToken) {
          tokens.push(current);
          current = "";
          inToken = false;
        }
        continue;
      }
      current += char;
      inToken = true;
    }
    if (quote) {
      return { tokens: [], error: "引号没有闭合，请检查额外参数" };
    }
    if (inToken) {
      tokens.push(current);
    }
    return { tokens, error: "" };
  }

  function parseExtraArgs() {
    return tokenizeExtraArgs(state.settings.extraArgs || "");
  }

  function extraArgTokens() {
    const parsed = parseExtraArgs();
    if (parsed.error) {
      return [];
    }
    return parsed.tokens
      .filter((token) => token.length > 0)
      .slice(0, 120)
      .map((token) => token.slice(0, 4000));
  }

  function emitOptionArgs(option, value) {
    if (option.type === "toggle") {
      return value ? [option.arg] : [];
    }
    if (option.id === "newDisplay") {
      const normalized = normalizeComboValue(option, value);
      if (!normalized) {
        return [];
      }
      if (normalized === "main") {
        return ["--new-display"];
      }
      return [`--new-display=${normalized}`];
    }
    if (option.type === "select") {
      const choice = option.choices.find((item) => item.value === value);
      if (!choice || choice.value === "") {
        return [];
      }
      if (choice.arg !== undefined) {
        return choice.arg ? [choice.arg] : [];
      }
      return [`${option.flag}=${choice.value}`];
    }
    if (option.type === "combo") {
      const normalized = normalizeComboValue(option, value);
      if (!normalized) {
        return [];
      }
      const defaultValue = normalizeComboValue(option, option.default);
      if (option.default !== "" && normalized === defaultValue) {
        return [];
      }
      return [`${option.flag}=${normalized}`];
    }
    const text = String(value ?? "").trim();
    if (!text) {
      return [];
    }
    if (Array.isArray(option.omitValues) && option.omitValues.includes(text)) {
      return [];
    }
    return [`${option.flag}=${text}`];
  }

  function buildArgv() {
    const argv = ["scrcpy"];
    const device = selectedDeviceObject();
    if (device?.serial) {
      argv.push("-s", device.serial);
    }
    for (const option of OPTIONS) {
      if (!isOptionActive(option)) {
        continue;
      }
      argv.push(
        ...emitOptionArgs(option, state.settings.options[option.id])
      );
    }
    argv.push(...extraArgTokens());
    return argv;
  }

  function quoteArg(arg) {
    if (arg === "") {
      return '""';
    }
    if (/^[A-Za-z0-9_@%+=:,./\\-]+$/.test(arg) && !arg.endsWith("\\")) {
      return arg;
    }
    return `"${arg.replace(/"/g, '\\"')}"`;
  }

  function commandString(argv) {
    return argv.map(quoteArg).join(" ");
  }

  function renderCommandLine(argv) {
    const pre = dom.commandLine;
    pre.replaceChildren();
    let previousWasSerialFlag = false;
    argv.forEach((arg, index) => {
      if (index > 0) {
        pre.append(document.createTextNode(" "));
      }
      const wrapper = document.createElement("span");
      wrapper.className = "token-arg";
      pre.append(wrapper);

      if (index === 0) {
        appendCommandToken(wrapper, "token-command", arg);
        previousWasSerialFlag = false;
        return;
      }
      const quoted = quoteArg(arg) !== arg;
      if (quoted) {
        appendCommandToken(wrapper, "token-quoted", quoteArg(arg));
        previousWasSerialFlag = false;
        return;
      }
      if (previousWasSerialFlag) {
        appendCommandToken(wrapper, "token-serial", arg);
        previousWasSerialFlag = false;
        return;
      }
      if (arg === "-s" || arg === "--serial") {
        appendCommandToken(wrapper, "token-flag", arg);
        previousWasSerialFlag = true;
        return;
      }
      if (arg.startsWith("--serial=")) {
        appendCommandToken(wrapper, "token-flag", "--serial");
        appendCommandToken(wrapper, "token-equals", "=");
        appendCommandToken(
          wrapper,
          "token-serial",
          arg.slice("--serial=".length)
        );
        return;
      }
      if (arg.startsWith("-")) {
        const equals = arg.indexOf("=");
        if (equals > 0) {
          appendCommandToken(wrapper, "token-flag", arg.slice(0, equals));
          appendCommandToken(wrapper, "token-equals", "=");
          appendCommandToken(wrapper, "token-value", arg.slice(equals + 1));
        } else {
          appendCommandToken(wrapper, "token-flag", arg);
        }
        return;
      }
      appendCommandToken(wrapper, "token-plain", arg);
    });
  }

  function appendCommandToken(parent, className, text) {
    const span = document.createElement("span");
    span.className = className;
    span.textContent = text;
    parent.append(span);
  }

  function getValidation() {
    if (!state.wsOpen || !state.helloReceived) {
      return {
        canRun: false,
        hint: "正在等待后端连接…",
        warning: "未连接后端",
      };
    }
    if (!state.tools?.scrcpyPath) {
      return {
        canRun: false,
        hint: "请确认 scrcpy 在 PATH 中，然后重启程序。",
        warning: "找不到 scrcpy",
      };
    }
    const extraArgs = parseExtraArgs();
    if (extraArgs.error) {
      return {
        canRun: false,
        hint: extraArgs.error,
        warning: "额外参数有误",
      };
    }
    if (state.starting) {
      return {
        canRun: false,
        hint: "正在请求后端启动 scrcpy…",
        warning: "正在启动",
      };
    }
    if (state.running) {
      return {
        canRun: false,
        hint: "运行中 · 新的命令需重启生效",
        warning: "运行中",
      };
    }
    const device = selectedDeviceObject();
    if (!device) {
      return {
        canRun: false,
        hint:
          state.devices.length > 1
            ? "左侧有多台设备，请先选择目标设备。"
            : "请先连接并选择一台在线设备。",
        warning: "请选择设备",
      };
    }
    if (device.state !== "device") {
      return {
        canRun: false,
        hint: "当前设备不可用，请处理授权或连接问题后刷新。",
        warning: "设备不可用",
      };
    }
    let warning = `目标：${deviceDisplayName(device)}`;
    if (state.settings.options.noWindow) {
      const record = String(state.settings.options.record || "").trim();
      if (!record) {
        warning = "无窗口且未录制：scrcpy 会禁用视频，进程可能一直空跑";
      }
    }
    if (
      String(state.settings.options.record || "").trim() &&
      !String(state.settings.options.recordFormat || "").trim()
    ) {
      const record = String(state.settings.options.record).trim();
      if (!/\.[A-Za-z0-9]{1,5}$/.test(record)) {
        warning = "建议为录制文件添加扩展名，或指定录制格式";
      }
    }
    return {
      canRun: true,
      hint: "命令将直接在本机执行，不经过 shell。",
      warning,
    };
  }

  function updateCommandPreview() {
    const argv = buildArgv();
    state.currentArgv = argv;
    state.lastCommand = commandString(argv);
    renderCommandLine(argv);
    dom.optionCount.textContent = `${Math.max(0, argv.length - 1)} 个参数`;

    const validation = getValidation();
    let warning = validation.warning;
    const versionWarnings = getActiveVersionWarnings();
    if (state.running) {
      warning = "运行中 · 新的命令需重启生效";
    } else if (validation.canRun && versionWarnings.length > 0) {
      warning = `${versionWarnings.length} 个已开启参数与当前 Android 版本不兼容，已自动忽略`;
    } else if (
      validation.canRun &&
      (warning.startsWith("目标：") || warning.startsWith("建议"))
    ) {
      // Keep the useful target or record-extension warning.
    }
    dom.commandWarning.textContent = warning;
    dom.commandWarning.classList.toggle(
      "is-warning",
      warning !== `目标：${deviceDisplayName(selectedDeviceObject())}`
    );

    dom.runButton.disabled = !validation.canRun;
    dom.runHint.textContent = validation.hint;
    dom.runButton.querySelector("span").textContent = state.starting
      ? "正在启动…"
      : "运行 scrcpy";
    updateRunControls();
  }

  // -----------------------------------------------------------------------
  // Running
  // -----------------------------------------------------------------------

  function setRunBadge(mode, text) {
    state.runBadgeMode = mode;
    state.runBadgeText = text;
    dom.runStateBadge.className = `run-state-badge is-${mode}`;
    dom.runStateBadge.textContent = text;
  }

  function updateRunControls() {
    dom.stopButton.hidden = !state.running;
    dom.stopButton.disabled = state.stopping;
    dom.restartButton.hidden = !state.running;
    dom.restartButton.disabled = state.stopping;
    const runLabel = dom.runButton.querySelector("span");
    if (state.starting) {
      runLabel.textContent = "正在启动…";
      dom.runButton.disabled = true;
    } else if (state.running) {
      runLabel.textContent = "运行 scrcpy";
      dom.runButton.disabled = true;
    } else {
      runLabel.textContent = "运行 scrcpy";
      dom.runButton.disabled = !getValidation().canRun;
    }
    if (state.running) {
      dom.runHint.textContent = "运行中 · 新的命令需重启生效";
    }
  }

  function runScrcpy() {
    if (state.running || state.starting) {
      return;
    }
    const validation = getValidation();
    if (!validation.canRun) {
      showToast(validation.hint, "warning");
      return;
    }
    state.starting = true;
    setRunBadge("running", "启动中");
    updateCommandPreview();
    const argv = state.currentArgv;
    const command = commandString(argv);
    const device = selectedDeviceObject();
    state.pendingRunSnapshot = {
      options: snapshotOptions(),
      argv: [...argv],
      command,
      selectedDevice: state.settings.selectedDevice || "",
      deviceLabel: device ? deviceDisplayName(device) : "",
      optionCount: Math.max(0, argv.length - 1),
      extraArgs: state.settings.extraArgs || "",
    };
    if (
      !sendMessage({
        type: "run",
        argv,
        command,
        afterStart: normalizeAfterStart(state.settings.afterStart),
      })
    ) {
      state.starting = false;
      state.pendingRunSnapshot = null;
      setRunBadge("idle", "尚未运行");
      updateCommandPreview();
      showToast("无法发送运行命令，后端连接已断开", "error");
    }
  }

  function stopScrcpy() {
    if (!state.running || state.stopping) {
      return;
    }
    state.pendingRestart = false;
    state.stopping = true;
    setRunBadge("stopping", "正在停止");
    updateRunControls();
    if (!sendMessage({ type: "stop" })) {
      state.stopping = false;
      updateRunControls();
      showToast("无法停止：后端连接已断开", "error");
    }
  }

  function restartScrcpy() {
    if (!state.running || state.stopping || state.starting) {
      return;
    }
    state.pendingRestart = true;
    state.stopping = true;
    setRunBadge("stopping", "正在重启");
    updateRunControls();
    if (!sendMessage({ type: "stop" })) {
      state.pendingRestart = false;
      state.stopping = false;
      setRunBadge("running", "运行中");
      updateRunControls();
      showToast("无法重启：后端连接已断开", "error");
    }
  }

  function handleRunStarted(message) {
    state.starting = false;
    state.running = true;
    state.stopping = false;
    state.pendingRestart = false;
    state.runStartedAt = Number(message.startedAt) || Date.now();
    setRunBadge("running", "运行中");
    addRunDivider(
      `RUN #${message.runNumber || 1} · ${formatClock(Date.now())}`
    );
    if (message.command) {
      appendLogLine(`$ ${message.command}`, Date.now(), "is-dim");
    }
    if (state.pendingRunSnapshot) {
      rememberLastRun(state.pendingRunSnapshot);
      state.pendingRunSnapshot = null;
      appendLogLine("已自动更新「上一次」配置", Date.now(), "is-dim");
    }
    startRunTimer();
    updateRunSummary();
    updateCommandPreview();
  }

  function handleRunOutput(message) {
    if (!Array.isArray(message.lines)) {
      return;
    }
    for (const line of message.lines) {
      if (!line || typeof line.text !== "string") {
        continue;
      }
      appendLogLine(
        line.text,
        Number(line.ts) || Date.now(),
        classifyLog(line.text)
      );
    }
  }

  function handleRunFinished(message) {
    const wasRunning = state.running;
    const restarting = state.pendingRestart;
    state.pendingRestart = false;
    state.starting = false;
    state.running = false;
    state.stopping = false;
    if (!wasRunning) {
      state.pendingRunSnapshot = null;
    }
    stopRunTimer();
    const duration = Number(message.duration) || 0;
    const code = Number(message.code);
    const stopped = Boolean(message.stopped);
    const success = code === 0 && !stopped;
    const launchFailed = code === -1 || code === 1;
    if (success) {
      setRunBadge("success", "已完成");
    } else if (stopped) {
      setRunBadge("stopping", "已停止");
    } else if (launchFailed) {
      setRunBadge("fail", "启动失败");
    } else {
      setRunBadge("fail", `退出码 ${Number.isFinite(code) ? code : "?"}`);
    }
    if (wasRunning || message.message) {
      appendLogLine(
        `— ${message.message || "进程已结束"}${
          Number.isFinite(code) ? `（退出码 ${code}）` : ""
        } · ${formatDuration(duration)}`,
        Date.now(),
        success ? "is-success" : stopped ? "is-dim" : "is-error"
      );
    }
    dom.runSummary.textContent = stopped
      ? `已停止 · ${formatDuration(duration)}`
      : launchFailed
        ? `启动失败 · ${formatDuration(duration)}`
        : `退出码 ${Number.isFinite(code) ? code : "?"} · ${formatDuration(
            duration
          )}`;
    updateCommandPreview();
    if (restarting) {
      appendLogLine("— 正在重启 scrcpy…", Date.now(), "is-dim");
      setRunBadge("running", "正在重启");
      dom.runSummary.textContent = "正在重启…";
      dom.runButton.disabled = true;
      window.setTimeout(() => {
        if (state.running || state.starting) {
          return;
        }
        if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
          setRunBadge("fail", "已断开");
          updateCommandPreview();
          return;
        }
        const validation = getValidation();
        if (!validation.canRun) {
          setRunBadge("idle", "尚未运行");
          updateCommandPreview();
          showToast(validation.hint, "warning");
          return;
        }
        runScrcpy();
      }, 80);
      return;
    }
    if (success) {
      showToast("scrcpy 已正常退出", "success");
    } else if (stopped) {
      showToast("scrcpy 已停止");
    } else {
      showToast(message.message || "scrcpy 异常退出", "error", 5000);
    }
  }

  function startRunTimer() {
    stopRunTimer();
    state.runTimer = window.setInterval(() => {
      if (!state.running) {
        return;
      }
      updateRunSummary();
    }, 1000);
  }

  function stopRunTimer() {
    if (state.runTimer) {
      window.clearInterval(state.runTimer);
      state.runTimer = null;
    }
  }

  function updateRunSummary() {
    if (state.running) {
      const elapsed = Math.max(0, (Date.now() - state.runStartedAt) / 1000);
      dom.runSummary.textContent = `运行中 · ${formatDuration(elapsed)}`;
    }
  }

  function formatDuration(seconds) {
    const value = Math.max(0, Number(seconds) || 0);
    if (value < 60) {
      return `${value.toFixed(1)} 秒`;
    }
    const minutes = Math.floor(value / 60);
    const rest = Math.round(value % 60);
    return `${minutes} 分 ${rest} 秒`;
  }

  function formatClock(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleTimeString("zh-CN", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  }

  function classifyLog(text) {
    const lower = text.toLowerCase();
    if (
      lower.includes("error") ||
      lower.includes("fatal") ||
      lower.includes("failed") ||
      lower.includes("exception")
    ) {
      return "is-error";
    }
    if (lower.includes("warn")) {
      return "is-warning";
    }
    return "";
  }

  function addRunDivider(label) {
    dom.terminalEmpty.hidden = true;
    const divider = document.createElement("div");
    divider.className = "log-divider";
    divider.textContent = label;
    dom.logLines.append(divider);
    trimLogLines();
    scrollLogsToBottom(true);
  }

  function appendLogLine(text, timestamp, className = "") {
    if (typeof text !== "string" || !text) {
      return;
    }
    dom.terminalEmpty.hidden = true;
    const line = document.createElement("div");
    line.className = `log-line ${className}`.trim();
    const time = document.createElement("span");
    time.className = "log-time";
    time.textContent = formatClock(timestamp || Date.now());
    const content = document.createElement("span");
    content.className = "log-text";
    content.textContent = text;
    line.append(time, content);
    dom.logLines.append(line);
    state.logLines.push(text);
    if (state.logLines.length > MAX_LOG_LINES) {
      state.logLines.splice(0, state.logLines.length - MAX_LOG_LINES);
    }
    trimLogLines();
    scrollLogsToBottom(state.stickToBottom);
  }

  function trimLogLines() {
    while (dom.logLines.childElementCount > MAX_LOG_LINES) {
      dom.logLines.firstElementChild?.remove();
    }
  }

  function scrollLogsToBottom(force = false) {
    if (force) {
      state.stickToBottom = true;
      dom.scrollToBottomButton.hidden = true;
    }
    if (!state.stickToBottom) {
      return;
    }
    window.requestAnimationFrame(() => {
      dom.logView.scrollTop = dom.logView.scrollHeight;
    });
  }

  function clearLogs() {
    state.logLines = [];
    dom.logLines.replaceChildren();
    dom.terminalEmpty.hidden = false;
    if (!state.running) {
      dom.runSummary.textContent = "尚未运行";
      setRunBadge("idle", "尚未运行");
    }
    state.stickToBottom = true;
    dom.scrollToBottomButton.hidden = true;
  }

  // -----------------------------------------------------------------------
  // Copy / toast / tooltip / dialog
  // -----------------------------------------------------------------------

  async function copyText(text) {
    if (!text) {
      return false;
    }
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      try {
        const area = document.createElement("textarea");
        area.value = text;
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.append(area);
        area.focus();
        area.select();
        const copied = document.execCommand("copy");
        area.remove();
        return copied;
      } catch {
        return false;
      }
    }
  }

  function showToast(message, kind = "info", duration = 3400) {
    const toast = document.createElement("div");
    toast.className = `toast${kind === "error" ? " is-error" : ""}${
      kind === "warning" ? " is-warning" : ""
    }`;
    let icon = "i-info";
    if (kind === "success") {
      icon = "i-check";
    } else if (kind === "error" || kind === "warning") {
      icon = "i-alert";
    }
    toast.innerHTML = `${svgIcon(icon)}<span></span>`;
    toast.querySelector("span").textContent = message;
    dom.toastRoot.append(toast);
    window.setTimeout(() => {
      toast.classList.add("is-leaving");
      window.setTimeout(() => toast.remove(), 220);
    }, duration);
  }

  function showTooltip(target) {
    const text = target.dataset.tooltip;
    if (!text) {
      return;
    }
    dom.floatingTooltip.textContent = text;
    dom.floatingTooltip.hidden = false;
    const targetRect = target.getBoundingClientRect();
    const tooltipRect = dom.floatingTooltip.getBoundingClientRect();
    const zoom =
      Number.parseFloat(
        getComputedStyle(document.documentElement).getPropertyValue("--ui-zoom")
      ) || 1;
    let left = targetRect.left + targetRect.width / 2 - tooltipRect.width / 2;
    left = Math.max(8, Math.min(window.innerWidth - tooltipRect.width - 8, left));
    let top = targetRect.top - tooltipRect.height - 8;
    if (top < 8) {
      top = targetRect.bottom + 8;
    }
    // getBoundingClientRect() is in visual coordinates, while fixed offsets
    // are laid out in the zoomed CSS coordinate space.
    dom.floatingTooltip.style.left = `${Math.round(left / zoom)}px`;
    dom.floatingTooltip.style.top = `${Math.round(top / zoom)}px`;
  }

  function hideTooltip() {
    dom.floatingTooltip.hidden = true;
  }

  let comboMenuState = null;

  function hideComboMenu() {
    if (!dom.comboMenu) {
      return;
    }
    if (comboMenuState?.anchor) {
      comboMenuState.anchor.setAttribute("aria-expanded", "false");
      if (
        dom.uiScaleToggle &&
        comboMenuState.anchor === dom.uiScaleInput
      ) {
        dom.uiScaleToggle.setAttribute("aria-expanded", "false");
      }
    }
    dom.comboMenu.hidden = true;
    comboMenuState = null;
  }

  function openOptionMenu(anchor, { hintText, items, onPick }) {
    if (!anchor || anchor.disabled) {
      return;
    }
    if (
      comboMenuState &&
      comboMenuState.anchor === anchor &&
      !dom.comboMenu.hidden
    ) {
      hideComboMenu();
      return;
    }
    hideComboMenu();
    hideTooltip();

    const menu = dom.comboMenu;
    menu.replaceChildren();

    const hint = document.createElement("div");
    hint.className = "combo-menu-hint";
    hint.textContent = hintText;
    menu.append(hint);

    for (const entry of items) {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "combo-menu-item";
      item.dataset.value = entry.value;
      item.setAttribute("role", "option");
      item.setAttribute("aria-selected", entry.selected ? "true" : "false");
      if (entry.selected) {
        item.classList.add("is-selected");
      }
      if (entry.disabled) {
        item.disabled = true;
        item.title = entry.title || "";
      }
      const label = document.createElement("span");
      label.className = "combo-menu-label";
      if (entry.swatch) {
        const dot = document.createElement("span");
        dot.className = "combo-menu-swatch";
        dot.style.background = entry.swatch;
        dot.setAttribute("aria-hidden", "true");
        label.append(dot);
      }
      const labelText = document.createElement("span");
      labelText.textContent = entry.label;
      label.append(labelText);
      const value = document.createElement("span");
      value.className = "combo-menu-value";
      const valueLabel = entry.valueLabel ?? entry.value;
      if (valueLabel) {
        value.textContent = valueLabel;
      } else {
        value.hidden = true;
      }
      item.append(label, value);
      item.addEventListener("mousedown", (event) => {
        event.preventDefault();
      });
      item.addEventListener("click", () => {
        onPick(entry.value);
        hideComboMenu();
        anchor.focus();
      });
      menu.append(item);
    }

    menu.hidden = false;
    const zoom =
      Number.parseFloat(
        getComputedStyle(document.documentElement).getPropertyValue("--ui-zoom")
      ) || 1;
    const rect = anchor.getBoundingClientRect();
    menu.style.width = `${Math.max(230, rect.width) / zoom}px`;
    const menuRect = menu.getBoundingClientRect();
    let left = rect.left;
    left = Math.max(
      8,
      Math.min(window.innerWidth - menuRect.width - 8, left)
    );
    let top = rect.bottom + 5;
    if (top + menuRect.height > window.innerHeight - 8) {
      top = rect.top - menuRect.height - 5;
    }
    top = Math.max(8, top);
    menu.style.left = `${Math.round(left / zoom)}px`;
    menu.style.top = `${Math.round(top / zoom)}px`;
    menu.scrollTop = 0;
    anchor.setAttribute("aria-expanded", "true");
    if (dom.uiScaleToggle && anchor === dom.uiScaleInput) {
      dom.uiScaleToggle.setAttribute("aria-expanded", "true");
    }
    comboMenuState = { anchor };
    hideTooltip();
  }

  function openComboMenu(anchor, option) {
    const normalized = normalizeComboValue(
      option,
      state.settings.options[option.id]
    );
    openOptionMenu(anchor, {
      hintText: "选择预设，或直接在输入框输入",
      items: option.presets.map((preset) => ({
        value: preset.value,
        label: preset.label,
        valueLabel: preset.value,
        selected:
          normalizeComboValue(option, preset.value) === normalized,
      })),
      onPick(value) {
        anchor.value = value;
        anchor.dispatchEvent(new Event("input", { bubbles: true }));
        anchor.dispatchEvent(new Event("change", { bubbles: true }));
        anchor.focus();
      },
    });
  }

  function openSelectMenu(anchor, option) {
    const value = String(state.settings.options[option.id] ?? "");
    openOptionMenu(anchor, {
      hintText: "选择一个选项",
      items: option.choices.map((choice) => {
        const allowed = choiceAllowed(choice);
        const requirement = allowed
          ? ""
          : `（需 ${minSdkShortLabel(choice.minSdk)}）`;
        return {
          value: choice.value,
          label: `${choice.label}${requirement}`,
          valueLabel: choice.value,
          selected: choice.value === value,
          disabled: !allowed,
          title: allowed ? "" : `${choice.label}${requirement}`,
        };
      }),
      onPick(nextValue) {
        state.settings.options[option.id] = nextValue;
        afterOptionChanged(option, { debounce: false });
        anchor.focus();
      },
    });
  }

  function askConfirm(title, message, okText = "确认") {
    dom.confirmTitle.textContent = title;
    dom.confirmMessage.textContent = message;
    dom.confirmOkButton.textContent = okText;
    dom.confirmDialog.returnValue = "cancel";
    return new Promise((resolve) => {
      const onClose = () => {
        dom.confirmDialog.removeEventListener("close", onClose);
        resolve(dom.confirmDialog.returnValue === "ok");
      };
      dom.confirmDialog.addEventListener("close", onClose);
      dom.confirmDialog.showModal();
    });
  }

  function resetOptions() {
    askConfirm(
      "恢复默认参数？",
      "所有开关会回到初始状态，设备选择和主题不会改变。",
      "恢复默认"
    ).then((confirmed) => {
      if (!confirmed) {
        return;
      }
      state.settings.options = { ...DEFAULT_OPTIONS };
      applyCollapsedSections();
      syncAllControls();
      updateCommandPreview();
      updateCapabilityBanner();
      updateGroupBadges();
      markSettingsChanged();
      showToast("已恢复默认参数", "success");
    });
  }

  // -----------------------------------------------------------------------
  // Search
  // -----------------------------------------------------------------------

  function renderSearch() {
    const query = state.search.trim().toLowerCase();
    dom.optionsRoot.classList.toggle("is-searching", Boolean(query));
    let totalMatches = 0;
    for (const section of dom.optionsRoot.querySelectorAll(".option-group")) {
      const group = GROUP_MAP.get(section.dataset.group);
      let matches = 0;
      for (const row of section.querySelectorAll(".option-row")) {
        const option = OPTION_MAP.get(row.dataset.option);
        if (!option) {
          continue;
        }
        const haystack = [
          option.title,
          option.arg || "",
          option.flag || "",
          option.short,
          option.detail,
          ...(option.choices || []).map((choice) => choice.label),
          ...(option.presets || []).map((preset) => preset.label),
        ]
          .join(" ")
          .toLowerCase();
        const visible = !query || haystack.includes(query);
        row.hidden = !visible;
        if (visible) {
          matches += 1;
        }
      }
      section.hidden = Boolean(query) && matches === 0;
      section.querySelector(".group-count").textContent = query
        ? `${matches}/${group.options.length}`
        : String(group.options.length);
      totalMatches += matches;
    }
    dom.noResults.hidden = totalMatches > 0;
    dom.optionsRoot.hidden = totalMatches === 0;
  }

  // -----------------------------------------------------------------------
  // Events / init
  // -----------------------------------------------------------------------

  function cacheDom() {
    const ids = [
      "connectionPill",
      "connectionText",
      "saveIndicator",
      "saveText",
      "scaleControl",
      "uiScaleInput",
      "uiScaleToggle",
      "appearanceSwitch",
      "colorControl",
      "colorDot",
      "colorButton",
      "colorLabel",
      "windowActionButton",
      "windowActionLabel",
      "refreshDevicesButton",
      "deviceStatusLine",
      "deviceList",
      "wirelessToggle",
      "wirelessBody",
      "wirelessAddress",
      "connectDeviceButton",
      "saveProfileButton",
      "profileList",
      "profileDialog",
      "profileNameInput",
      "profileNameToggle",
      "profileNameMenu",
      "profileOverwriteHint",
      "profileNameError",
      "profileDialogCancelButton",
      "profileDialogSaveButton",
      "scrcpyVersionValue",
      "adbVersionValue",
      "portValue",
      "windowBackendValue",
      "optionSearch",
      "resetOptionsButton",
      "capabilityBanner",
      "capabilityTitle",
      "capabilityText",
      "capabilityBadge",
      "optionsRoot",
      "noResults",
      "commandLine",
      "copyCommandButton",
      "optionCount",
      "commandWarning",
      "runButton",
      "restartButton",
      "stopButton",
      "afterStartControl",
      "autoConsoleRow",
      "autoConsoleSwitch",
      "autoConsoleState",
      "keepBackgroundRow",
      "keepBackgroundSwitch",
      "keepBackgroundState",
      "extraArgsBox",
      "extraArgsInput",
      "extraArgsError",
      "runHint",
      "runStateBadge",
      "copyLogButton",
      "clearLogButton",
      "logView",
      "terminalEmpty",
      "logLines",
      "runSummary",
      "scrollToBottomButton",
      "disconnectOverlay",
      "disconnectEyebrow",
      "disconnectTitle",
      "disconnectMessage",
      "disconnectCloseButton",
      "confirmDialog",
      "confirmTitle",
      "confirmMessage",
      "confirmOkButton",
      "confirmCancelButton",
      "toastRoot",
      "floatingTooltip",
      "comboMenu",
      "deviceTemplate",
    ];
    for (const id of ids) {
      dom[id] = byId(id);
    }
  }

  function bindEvents() {
    dom.appearanceSwitch.addEventListener("click", (event) => {
      const button = event.target.closest("[data-appearance-value]");
      if (!button) {
        return;
      }
      applyAppearance(button.dataset.appearanceValue, { persist: true });
    });

    const colorScheme = window.matchMedia?.("(prefers-color-scheme: light)");
    colorScheme?.addEventListener?.("change", () => {
      if (normalizeAppearance(state.settings.appearance) !== "system") {
        return;
      }
      applyAppearance("system");
      // Let the backend update the native window title bar as well.
      flushSettings();
    });

    dom.colorButton.addEventListener("click", (event) => {
      event.stopPropagation();
      openAccentMenu();
    });
    dom.colorButton.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        openAccentMenu();
      } else if (event.key === "Escape") {
        hideComboMenu();
      }
    });

    dom.windowActionButton.addEventListener("click", triggerWindowAction);

    dom.keepBackgroundSwitch.addEventListener("click", toggleKeepBackground);

    dom.uiScaleInput.addEventListener("input", () => {
      const percent = parseUiScalePercent(dom.uiScaleInput.value);
      if (percent === null) {
        return;
      }
      const value = String(percent);
      if (state.settings.uiScale !== value) {
        state.settings.uiScale = value;
        applyUiScale({ persist: true });
      }
    });
    dom.uiScaleInput.addEventListener("change", commitUiScaleInput);
    dom.uiScaleInput.addEventListener("blur", commitUiScaleInput);
    dom.uiScaleInput.addEventListener("focus", () => {
      dom.uiScaleInput.select();
    });
    dom.uiScaleInput.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        openUiScaleMenu();
      } else if (event.key === "Enter") {
        event.preventDefault();
        dom.uiScaleInput.blur();
      } else if (event.key === "Escape") {
        hideComboMenu();
      }
    });
    dom.uiScaleToggle.addEventListener("click", (event) => {
      event.stopPropagation();
      openUiScaleMenu();
    });

    dom.afterStartControl.addEventListener("click", (event) => {
      const button = event.target.closest("[data-after-start]");
      if (!button || button.disabled) {
        return;
      }
      const next = normalizeAfterStart(button.dataset.afterStart);
      if (state.settings.afterStart === next) {
        return;
      }
      state.settings.afterStart = next;
      syncAfterStartControl();
      markSettingsChanged();
    });

    dom.autoConsoleSwitch.addEventListener("click", () => {
      state.settings.autoOpenConsole =
        state.settings.autoOpenConsole === false;
      syncAutoConsoleControl();
      markSettingsChanged();
    });

    dom.extraArgsInput.addEventListener("input", () => {
      state.settings.extraArgs = dom.extraArgsInput.value.slice(0, 4000);
      updateExtraArgsState();
      updateCommandPreview();
      markSettingsChanged({ debounce: true });
    });
    dom.extraArgsInput.addEventListener("change", () => {
      state.settings.extraArgs = dom.extraArgsInput.value.slice(0, 4000);
      updateExtraArgsState();
      updateCommandPreview();
      flushSettings();
    });

    dom.refreshDevicesButton.addEventListener("click", () => {
      if (state.helloReceived) {
        sendMessage({ type: "list_devices" });
      }
    });

    dom.wirelessToggle.addEventListener("click", () => {
      const box = dom.wirelessToggle.closest(".wireless-box");
      const collapsed = box.classList.toggle("is-collapsed");
      dom.wirelessToggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
    });

    dom.connectDeviceButton.addEventListener("click", connectWirelessDevice);
    dom.wirelessAddress.addEventListener("input", () => {
      state.settings.wirelessAddress = dom.wirelessAddress.value.slice(0, 300);
      markSettingsChanged({ debounce: true });
    });
    dom.wirelessAddress.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        connectWirelessDevice();
      }
    });

    dom.saveProfileButton.addEventListener("click", saveCurrentProfile);
    dom.profileDialogCancelButton.addEventListener("click", () => {
      dom.profileDialog.returnValue = "cancel";
      dom.profileDialog.close();
    });
    dom.profileDialogSaveButton.addEventListener("click", commitProfileName);
    dom.profileNameToggle.addEventListener("click", toggleProfileNameMenu);
    dom.profileNameInput.addEventListener("input", () => {
      dom.profileNameError.textContent = "";
      updateProfileNameState();
      if (!dom.profileNameMenu.hidden) {
        closeProfileNameMenu();
      }
    });
    dom.profileNameInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        commitProfileName();
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        openProfileNameMenu();
      } else if (event.key === "Escape" && !dom.profileNameMenu.hidden) {
        event.preventDefault();
        event.stopPropagation();
        closeProfileNameMenu();
      }
    });
    dom.profileDialog.addEventListener("pointerdown", (event) => {
      if (!event.target.closest(".profile-name-combo")) {
        closeProfileNameMenu();
      }
    });
    dom.profileDialog.addEventListener("close", handleProfileDialogClose);

    dom.deviceList.addEventListener("click", (event) => {
      const card = event.target.closest(".device-card");
      if (!card) {
        return;
      }
      if (event.target.closest(".device-disconnect")) {
        event.stopPropagation();
        disconnectWirelessDevice(card.dataset.serial);
        return;
      }
      selectDevice(card.dataset.serial);
    });

    dom.deviceList.addEventListener("keydown", (event) => {
      const card = event.target.closest(".device-card");
      if (!card || event.target.closest("button")) {
        return;
      }
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectDevice(card.dataset.serial);
      }
    });

    dom.optionSearch.addEventListener("input", () => {
      state.search = dom.optionSearch.value;
      renderSearch();
    });
    dom.optionSearch.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        dom.optionSearch.value = "";
        state.search = "";
        renderSearch();
        dom.optionSearch.blur();
      }
    });

    dom.resetOptionsButton.addEventListener("click", resetOptions);

    dom.copyCommandButton.addEventListener("click", async () => {
      const copied = await copyText(state.lastCommand);
      showToast(copied ? "完整命令已复制" : "复制失败", copied ? "success" : "error");
    });
    dom.copyLogButton.addEventListener("click", async () => {
      const copied = await copyText(state.logLines.join("\n"));
      showToast(copied ? "日志已复制" : "没有可复制的日志", copied ? "success" : "warning");
    });
    dom.clearLogButton.addEventListener("click", clearLogs);

    dom.runButton.addEventListener("click", runScrcpy);
    dom.restartButton.addEventListener("click", restartScrcpy);
    dom.stopButton.addEventListener("click", stopScrcpy);

    dom.logView.addEventListener("scroll", () => {
      const distance =
        dom.logView.scrollHeight - dom.logView.scrollTop - dom.logView.clientHeight;
      state.stickToBottom = distance < 28;
      dom.scrollToBottomButton.hidden = state.stickToBottom;
    });
    dom.scrollToBottomButton.addEventListener("click", () => {
      scrollLogsToBottom(true);
    });

    dom.disconnectCloseButton.addEventListener("click", () => {
      if (state.overlayAction === "reload") {
        window.location.reload();
      } else {
        closeWindow();
      }
    });

    document.addEventListener("keydown", (event) => {
      if (document.querySelector("dialog[open]")) {
        return;
      }
      const editable =
        event.target instanceof HTMLElement &&
        (event.target.matches("input, textarea, select") ||
          event.target.isContentEditable);
      if (event.ctrlKey && event.key === "Enter") {
        event.preventDefault();
        if (state.running) {
          stopScrcpy();
        } else {
          runScrcpy();
        }
        return;
      }
      if (!editable && event.key === "/") {
        event.preventDefault();
        dom.optionSearch.focus();
        dom.optionSearch.select();
        return;
      }
      if (event.key === "Escape" && document.activeElement === dom.optionSearch) {
        dom.optionSearch.value = "";
        state.search = "";
        renderSearch();
        dom.optionSearch.blur();
      }
    });

    document.addEventListener("mouseover", (event) => {
      const target = event.target.closest?.("[data-tooltip]");
      if (!target) {
        return;
      }
      if (event.relatedTarget && target.contains(event.relatedTarget)) {
        return;
      }
      showTooltip(target);
    });
    document.addEventListener("mouseout", (event) => {
      const target = event.target.closest?.("[data-tooltip]");
      if (!target) {
        return;
      }
      if (event.relatedTarget && target.contains(event.relatedTarget)) {
        return;
      }
      hideTooltip();
    });
    document.addEventListener("focusin", (event) => {
      const target = event.target.closest?.("[data-tooltip]");
      if (target) {
        showTooltip(target);
      }
    });
    document.addEventListener("focusout", hideTooltip);
    window.addEventListener(
      "scroll",
      (event) => {
        hideTooltip();
        if (dom.comboMenu && dom.comboMenu.contains(event.target)) {
          return;
        }
        hideComboMenu();
      },
      true
    );
    document.addEventListener(
      "pointerdown",
      (event) => {
        if (!comboMenuState) {
          return;
        }
        if (dom.comboMenu.contains(event.target)) {
          return;
        }
        const wrap = comboMenuState.anchor.closest(
          ".combo-wrap, .custom-select-wrap"
        );
        if (wrap && wrap.contains(event.target)) {
          return;
        }
        hideComboMenu();
      },
      true
    );
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        hideComboMenu();
      }
    });
    let scaleResizeTimer = null;
    window.addEventListener("resize", () => {
      hideTooltip();
      hideComboMenu();
      if (scaleResizeTimer) {
        window.clearTimeout(scaleResizeTimer);
      }
      scaleResizeTimer = window.setTimeout(() => {
        scaleResizeTimer = null;
        applyUiScale();
      }, 120);
    });

    window.addEventListener("pagehide", () => {
      state.pageHidden = true;
      if (state.wsOpen && state.helloReceived) {
        try {
          state.ws.send(
            JSON.stringify({ type: "save_settings", settings: state.settings })
          );
        } catch {
          /* ignore */
        }
      }
    });
    window.addEventListener("pageshow", (event) => {
      state.pageHidden = false;
      if (event.persisted && !state.wsOpen) {
        handleConnectionLost();
      }
    });
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") {
        persistLocalSettings();
        if (state.saveTimer) {
          flushSettings();
        }
      }
    });
  }

  function init() {
    cacheDom();
    applyAppearance(state.settings.appearance);
    buildOptionGroups();
    bindEvents();
    dom.wirelessAddress.value = state.settings.wirelessAddress || "";
    dom.saveProfileButton.disabled = true;
    initAfterStartControl();
    syncAutoConsoleControl();
    syncKeepBackgroundControl();
    syncExtraArgsInput();
    applyUiScale();
    renderProfiles();
    syncAllControls();
    updateCommandPreview();
    updateCapabilityBanner();
    setConnectionStatus("pending", "正在连接后端");
    setSaveStatus("saved", "等待设置载入");
    renderDeviceStatus();
    connectSocket();
  }

  init();
})();
