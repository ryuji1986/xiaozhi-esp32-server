# xiaozhi-server 架构概览

> **小智 AI 语音交互服务器** - 生产级实时语音对话系统

本文档深入解析 xiaozhi-server 模块的代码架构、数据流动和核心设计原理。

---

## 📚 目录

- [一、系统架构全景](#一系统架构全景)
- [二、目录结构说明](#二目录结构说明)
- [三、启动流程](#三启动流程)
- [四、核心组件详解](#四核心组件详解)
- [五、数据流动路径](#五数据流动路径)
- [六、WebSocket 协议](#六websocket-协议)
- [七、关键技术点](#七关键技术点)
- [八、性能优化策略](#八性能优化策略)
- [九、扩展开发指南](#九扩展开发指南)

---

## 一、系统架构全景

### 1.1 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                     xiaozhi-server 架构                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │  app.py      │    │  config/     │    │  core/       │  │
│  │  (入口)      │───▶│  (配置管理)   │───▶│  (核心逻辑)   │  │
│  └──────────────┘    └──────────────┘    └──────┬───────┘  │
│                                                  │           │
│                    ┌─────────────────────────────┼───────┐  │
│                    │                             │       │  │
│          ┌─────────▼────────┐         ┌─────────▼──────┐│  │
│          │ WebSocket Server │         │  HTTP Server   ││  │
│          │ (port: 8000)     │         │  (port: 8003)  ││  │
│          └─────────┬────────┘         └────────────────┘│  │
│                    │                                     │  │
│          ┌─────────▼────────────────────────────────┐   │  │
│          │      ConnectionHandler (每连接一个实例)    │   │  │
│          │  - 会话管理                               │   │  │
│          │  - 音频流处理                             │   │  │
│          │  - 状态机控制                             │   │  │
│          └─────────┬────────────────────────────────┘   │  │
│                    │                                     │  │
│          ┌─────────▼────────────────────────────────┐   │  │
│          │           Handle 层 (业务逻辑)            │   │  │
│          │  ┌──────────┐ ┌──────────┐ ┌──────────┐ │   │  │
│          │  │hello     │ │receive   │ │sendAudio │ │   │  │
│          │  │Handle    │ │Audio     │ │Handle    │ │   │  │
│          │  └──────────┘ └──────────┘ └──────────┘ │   │  │
│          │  ┌──────────┐ ┌──────────┐ ┌──────────┐ │   │  │
│          │  │text      │ │intent    │ │abort     │ │   │  │
│          │  │Handle    │ │Handler   │ │Handle    │ │   │  │
│          │  └──────────┘ └──────────┘ └──────────┘ │   │  │
│          └─────────┬────────────────────────────────┘   │  │
│                    │                                     │  │
│          ┌─────────▼────────────────────────────────┐   │  │
│          │        Providers 层 (AI能力抽象)          │   │  │
│          │  ┌────┐ ┌───┐ ┌───┐ ┌────┐ ┌───┐ ┌───┐ │   │  │
│          │  │VAD │ │ASR│ │LLM│ │TTS │ │MEM│ │INT│ │   │  │
│          │  └────┘ └───┘ └───┘ └────┘ └───┘ └───┘ │   │  │
│          └──────────────────────────────────────────┘   │  │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

### 1.2 设计原则

- **模块化设计**：各组件松耦合，通过统一接口交互
- **异步优先**：全程 asyncio，支持高并发
- **配置驱动**：yaml 配置文件控制所有行为
- **流式处理**：LLM/TTS 边生成边发送，降低延迟
- **生产者-消费者**：队列解耦，提高吞吐量

---

## 二、目录结构说明

```
xiaozhi-server/
├── app.py                          # 应用入口
├── config.yaml                     # 主配置文件
├── config_from_api.yaml            # API 配置模板
├── requirements.txt                # Python 依赖
│
├── config/                         # 配置管理模块
│   ├── config_loader.py            # 配置加载器
│   ├── logger.py                   # 日志系统
│   ├── manage_api_client.py        # 智控台 API 客户端
│   └── settings.py                 # 设置管理
│
├── core/                           # 核心业务逻辑
│   ├── websocket_server.py         # WebSocket 服务器
│   ├── http_server.py              # HTTP 服务器（OTA + 视觉）
│   ├── connection.py               # 连接处理器（核心）
│   ├── auth.py                     # JWT 认证
│   │
│   ├── handle/                     # 业务逻辑处理器
│   │   ├── helloHandle.py          # 握手处理
│   │   ├── receiveAudioHandle.py   # 音频接收处理
│   │   ├── sendAudioHandle.py      # 音频发送处理
│   │   ├── textHandle.py           # 文本消息处理
│   │   ├── intentHandler.py        # 意图识别处理
│   │   └── abortHandle.py          # 打断处理
│   │
│   ├── providers/                  # AI 能力提供商（插件化）
│   │   ├── vad/                    # 语音活动检测
│   │   │   └── silero.py
│   │   ├── asr/                    # 语音识别
│   │   │   ├── fun_local.py        # FunASR 本地
│   │   │   ├── doubao.py           # 火山引擎
│   │   │   ├── aliyun.py           # 阿里云
│   │   │   └── ...
│   │   ├── llm/                    # 大语言模型
│   │   │   ├── chatglm.py          # 智谱 AI
│   │   │   ├── doubao.py           # 豆包
│   │   │   ├── qwen.py             # 通义千问
│   │   │   └── ...
│   │   ├── tts/                    # 文本转语音
│   │   │   ├── edge.py             # Edge TTS
│   │   │   ├── doubao.py           # 火山引擎
│   │   │   ├── fishspeech.py       # FishSpeech
│   │   │   └── ...
│   │   ├── memory/                 # 记忆管理
│   │   │   ├── mem0ai.py
│   │   │   ├── powermem.py
│   │   │   └── local_short.py
│   │   ├── intent/                 # 意图识别
│   │   │   ├── intent_llm.py
│   │   │   └── function_call.py
│   │   └── tools/                  # 工具调用（MCP）
│   │
│   ├── utils/                      # 工具类
│   │   ├── gc_manager.py           # GC 管理器
│   │   ├── cache/                  # 缓存管理
│   │   ├── dialogue.py             # 对话管理
│   │   └── ...
│   │
│   └── api/                        # HTTP API 接口
│       ├── ota_handler.py          # OTA 升级接口
│       └── vision_handler.py       # 视觉分析接口
│
├── plugins_func/                   # 功能插件
│   └── functions/
│       ├── get_weather.py          # 天气查询
│       ├── play_music.py           # 音乐播放
│       └── ...
│
├── models/                         # 本地模型文件
├── music/                          # 音乐文件
└── test/                           # 测试页面
    └── test_page.html              # WebSocket 测试客户端
```

---

## 三、启动流程

### 3.1 应用入口 (app.py)

```python
async def main():
    # 1. 检查 FFmpeg 安装
    check_ffmpeg_installed()
    
    # 2. 加载配置（优先级：data/.config.yaml > config.yaml）
    config = load_config()
    
    # 3. 生成认证密钥
    auth_key = generate_auth_key()
    config["server"]["auth_key"] = auth_key
    
    # 4. 启动全局 GC 管理器（定期垃圾回收）
    gc_manager = get_gc_manager(interval_seconds=300)
    await gc_manager.start()
    
    # 5. 启动 WebSocket 服务器（核心服务，端口 8000）
    ws_server = WebSocketServer(config)
    ws_task = asyncio.create_task(ws_server.start())
    
    # 6. 启动 HTTP 服务器（OTA + 视觉分析，端口 8003）
    ota_server = SimpleHttpServer(config)
    ota_task = asyncio.create_task(ota_server.start())
    
    # 7. 阻塞等待退出信号（Ctrl+C / SIGTERM）
    await wait_for_exit()
    
    # 8. 清理资源
    await gc_manager.stop()
    ws_task.cancel()
    ota_task.cancel()
```

### 3.2 WebSocket 服务器初始化

```python
class WebSocketServer:
    def __init__(self, config: dict):
        # 1. 初始化共享的 AI 模块实例
        modules = initialize_modules(
            logger, config,
            vad=True, asr=True, llm=True,
            memory=True, intent=True
        )
        self._vad = modules["vad"]
        self._asr = modules["asr"]
        self._llm = modules["llm"]
        self._memory = modules["memory"]
        self._intent = modules["intent"]
        
        # 2. 初始化认证管理器
        self.auth = AuthManager(secret_key, expire_seconds)
    
    async def start(self):
        # 3. 启动 WebSocket 服务器
        async with websockets.serve(
            self._handle_connection, 
            host="0.0.0.0", 
            port=8000
        ):
            await asyncio.Future()  # 永久运行
```

### 3.3 新连接处理流程

```
客户端连接
    ↓
WebSocketServer._handle_connection()
    ↓
1. 提取 device-id（从 Header 或 URL 参数）
    ↓
2. 认证检查（如果启用）
   ├─ 白名单设备 → 直接放行
   └─ 其他设备 → 验证 JWT Token
    ↓
3. 创建 ConnectionHandler 实例
   （每个连接独立实例，传入共享的 AI 模块）
    ↓
4. 调用 handler.handle_connection(websocket)
```

---

## 四、核心组件详解

### 4.1 ConnectionHandler（连接处理器）

**职责**：管理单个 WebSocket 连接的完整生命周期

**关键属性**：
```python
class ConnectionHandler:
    # 连接信息
    self.session_id = str(uuid.uuid4())
    self.websocket: websockets.ServerConnection
    self.device_id: str
    self.client_ip: str
    
    # AI 模块引用（共享实例）
    self.vad = _vad
    self.asr = _asr
    self.llm = _llm
    self.tts = None  # 动态初始化
    self.memory = _memory
    self.intent = _intent
    
    # 状态管理
    self.client_abort = False          # 是否打断
    self.client_is_speaking = False    # 客户端是否在播放
    self.client_listen_mode = "auto"   # 监听模式
    
    # 音频缓冲
    self.asr_audio_queue = queue.Queue()
    self.client_audio_buffer = bytearray()
    
    # 线程池
    self.executor = ThreadPoolExecutor(max_workers=5)
```

**核心方法**：
```python
async def handle_connection(self, ws):
    """处理连接的完整生命周期"""
    # 1. 后台初始化 AI 模块
    asyncio.create_task(self._background_initialize())
    
    # 2. 主循环：接收消息
    async for message in self.websocket:
        await self._route_message(message)
    
    # 3. 关闭时保存记忆
    await self._save_and_close(ws)

async def _route_message(self, message):
    """消息路由"""
    if isinstance(message, str):
        await handleTextMessage(self, message)  # 文本消息
    elif isinstance(message, bytes):
        self.asr_audio_queue.put(message)        # 音频消息
```

### 4.2 Handle 层（业务逻辑处理器）

#### **helloHandle.py** - 握手处理
```python
async def handleHelloMessage(conn, msg_json):
    """处理客户端 hello 消息"""
    # 1. 提取音频参数
    audio_params = msg_json.get("audio_params")
    conn.audio_format = audio_params.get("format", "opus")
    
    # 2. 检查 MCP 特性
    features = msg_json.get("features")
    if features.get("mcp"):
        conn.mcp_client = MCPClient()
    
    # 3. 发送欢迎消息
    await conn.websocket.send(json.dumps(conn.welcome_msg))
```

#### **receiveAudioHandle.py** - 音频接收处理
```python
async def handleAudioMessage(conn, audio):
    """处理音频帧"""
    # 1. VAD 检测（是否有声音）
    have_voice = conn.vad.is_vad(conn, audio)
    
    # 2. 长时间空闲检测（用于自动结束对话）
    await no_voice_close_connect(conn, have_voice)
    
    # 3. 发送给 ASR 处理
    await conn.asr.receive_audio(conn, audio, have_voice)

async def startToChat(conn, text):
    """开始对话流程"""
    # 1. 意图识别
    intent_handled = await handle_user_intent(conn, text)
    if intent_handled:
        return  # 意图已处理（如播放音乐）
    
    # 2. 发送 STT 消息给客户端
    await send_stt_message(conn, text)
    
    # 3. 在线程池中调用 LLM
    conn.executor.submit(conn.chat, text)
```

#### **sendAudioHandle.py** - 音频发送处理
```python
async def sendAudioMessage(conn, sentenceType, audios, text):
    """发送 TTS 音频给客户端"""
    # 1. 发送状态消息
    if sentenceType == SentenceType.FIRST:
        await send_tts_message(conn, "start")
        await send_tts_message(conn, "sentence_start", text)
    
    # 2. 发送音频帧（带流控）
    for opus_packet in audios:
        await conn.websocket.send(opus_packet)
        await audio_rate_controller.wait()  # 控制发送速率
    
    # 3. 发送结束消息
    if sentenceType == SentenceType.LAST:
        await send_tts_message(conn, "sentence_end")
        await send_tts_message(conn, "stop")
```

### 4.3 Providers 层（AI 能力抽象）

**设计模式**：策略模式 + 工厂模式

#### **统一接口示例（ASR）**
```python
class ASRProviderBase:
    """ASR 提供商基类"""
    async def speech_to_text(self, audio_data, session_id):
        raise NotImplementedError
    
    async def receive_audio(self, conn, audio, have_voice):
        raise NotImplementedError

# 具体实现
class FunASRProvider(ASRProviderBase):
    """FunASR 本地识别"""
    async def speech_to_text(self, audio_data, session_id):
        # 调用本地 FunASR 模型
        result = await self.model.recognize(audio_data)
        return result.text

class DoubaoASRProvider(ASRProviderBase):
    """火山引擎云端识别"""
    async def speech_to_text(self, audio_data, session_id):
        # 调用火山引擎 API
        response = await self.client.recognize(audio_data)
        return response.text
```

#### **支持的 Provider 列表**

| 模块 | 本地方案 | 云端方案 |
|------|---------|---------|
| **VAD** | SileroVAD | - |
| **ASR** | FunASR, SherpaASR | Doubao, Aliyun, Tencent |
| **LLM** | Ollama, LMStudio | ChatGLM, Doubao, Qwen, Gemini |
| **TTS** | FishSpeech, GPT-SoVITS | Edge, Doubao, CosyVoice |
| **Memory** | LocalShort | Mem0ai, PowerMem |
| **Intent** | IntentLLM | FunctionCall |

**配置切换示例**：
```yaml
selected_module:
  ASR: FunASR        # 切换到 DoubaoASR 即可使用云端识别
  LLM: ChatGLMLLM
  TTS: EdgeTTS

ASR:
  FunASR:
    type: fun_local
    model_dir: models/SenseVoiceSmall
  DoubaoASR:
    type: doubao
    appid: xxx
    access_token: xxx
```

---

## 五、数据流动路径

### 5.1 完整交互时序图

```
用户说话 "你好小智"
    ↓
【客户端】录音 → Opus 编码 → WebSocket 发送
    ↓
【服务端】ConnectionHandler 接收音频帧
    ↓
handleAudioMessage()
    ↓
1. VAD 检测（是否有声音）
   ├─ have_voice = True → 累积音频
   └─ have_voice = False → 静音计时
    ↓
2. 静音超时（默认 800ms）→ 触发 ASR
    ↓
ASR.speech_to_text(audio_frames)
    ↓
输出: "你好小智"
    ↓
startToChat(text)
    ↓
3. 意图识别
   ├─ handle_user_intent()
   ├─ 检测到唤醒词 → 播放欢迎语
   └─ 普通对话 → 继续
    ↓
4. 发送 STT 消息给客户端
   {type: "stt", text: "你好小智"}
    ↓
5. 调用 LLM.chat(text)
   ├─ 构建 Prompt（系统提示词 + 对话历史）
   ├─ 流式调用 LLM API
   └─ 逐字接收回复
    ↓
6. TTS 转换（并行进行）
   ├─ 收到 LLM 第一个句子
   ├─ TTS.to_tts(sentence)
   └─ 生成 Opus 音频
    ↓
7. 发送 TTS 状态消息
   {type: "tts", state: "start"}
   {type: "tts", state: "sentence_start", text: "..."}
    ↓
8. 发送音频数据（Binary Frame）
   ↓ (持续发送直到句子结束)
   {type: "tts", state: "sentence_end"}
    ↓
9. 所有句子播放完毕
   {type: "tts", state: "stop"}
    ↓
10. 保存对话历史到 Memory
    ↓
等待用户下一次说话...
```

### 5.2 音频流处理细节

```python
# 1. 客户端发送音频帧（60ms/帧）
while recording:
    opus_frame = encode_audio(pcm_data)
    websocket.send(opus_frame)

# 2. 服务端接收并放入队列
async def _route_message(self, message):
    if isinstance(message, bytes):
        self.asr_audio_queue.put(message)

# 3. ASR 后台线程消费队列
async def receive_audio(self, conn, audio, have_voice):
    if have_voice:
        self.audio_buffer.append(audio)
    else:
        # 静音超时，触发识别
        if len(self.audio_buffer) > threshold:
            text = await self.speech_to_text(self.audio_buffer)
            await startToChat(conn, text)
```

### 5.3 流式处理优势

**传统方式**：
```
用户说完 → ASR 识别 → LLM 完整回复 → TTS 完整转换 → 播放
延迟：3-5 秒
```

**流式处理**：
```
用户说完 → ASR 识别 → LLM 流式输出 → TTS 逐句转换 → 立即播放
延迟：800ms - 1.5 秒
```

---

## 六、WebSocket 协议

### 6.1 客户端 → 服务端消息

#### **Hello 握手消息**
```json
{
    "type": "hello",
    "device_id": "AA:BB:CC:DD:EE:FF",
    "device_name": "小智音箱",
    "token": "jwt_token_here",
    "features": {
        "mcp": true
    },
    "audio_params": {
        "format": "opus",
        "sample_rate": 24000,
        "channels": 1,
        "frame_duration": 60
    }
}
```

#### **Listen 消息（文本输入）**
```json
{
    "type": "listen",
    "state": "detect",
    "text": "你好小智"
}
```

#### **Abort 消息（打断）**
```json
{
    "session_id": "xxx",
    "type": "abort",
    "reason": "wake_word_detected"
}
```

#### **音频数据**
- **格式**：Opus 编码的二进制帧
- **传输**：WebSocket Binary Frame
- **帧大小**：约 60-120 字节（60ms @ 24kHz）

### 6.2 服务端 → 客户端消息

#### **Hello 响应**
```json
{
    "type": "hello",
    "version": 1,
    "transport": "websocket",
    "session_id": "unique-session-id",
    "audio_params": {
        "format": "opus",
        "sample_rate": 24000,
        "channels": 1,
        "frame_duration": 60
    }
}
```

#### **STT 消息（识别结果）**
```json
{
    "type": "stt",
    "text": "你好小智",
    "session_id": "xxx"
}
```

#### **TTS 状态消息**
```json
// 开始播放
{"type": "tts", "state": "start", "session_id": "xxx"}

// 句子开始
{"type": "tts", "state": "sentence_start", "text": "你好！", "session_id": "xxx"}

// 句子结束
{"type": "tts", "state": "sentence_end", "text": "你好！", "session_id": "xxx"}

// 播放结束
{"type": "tts", "state": "stop", "session_id": "xxx"}
```

#### **LLM 回复消息**
```json
{
    "type": "llm",
    "text": "你好！我是小智...",
    "emotion": "happy",
    "session_id": "xxx"
}
```

#### **音频数据**
- **格式**：Opus 编码的二进制帧
- **传输**：WebSocket Binary Frame
- **时机**：在 `tts.state = 'start'` 和 `'stop'` 之间持续发送

### 6.3 MCP 工具调用协议

#### **服务端下发工具请求**
```json
{
    "session_id": "xxx",
    "type": "mcp",
    "payload": {
        "method": "tools/call",
        "params": {
            "name": "get_weather",
            "arguments": {
                "location": "北京"
            }
        },
        "id": 123
    }
}
```

#### **客户端返回工具结果**
```json
{
    "session_id": "xxx",
    "type": "mcp",
    "payload": {
        "jsonrpc": "2.0",
        "id": 123,
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": "北京今天晴天，气温 20°C"
                }
            ],
            "isError": false
        }
    }
}
```

---

## 七、关键技术点

### 7.1 异步架构

**主事件循环**：
```python
# WebSocket 消息处理
async for message in self.websocket:
    await self._route_message(message)

# 后台任务
asyncio.create_task(self._background_initialize())
asyncio.create_task(self._check_timeout())
```

**线程池执行耗时操作**：
```python
# LLM 调用在线程池中执行，避免阻塞事件循环
self.executor = ThreadPoolExecutor(max_workers=5)
conn.executor.submit(conn.chat, text)
```

### 7.2 队列解耦

**音频接收队列**：
```python
# 生产者：WebSocket 接收线程
self.asr_audio_queue.put(audio_frame)

# 消费者：ASR 处理线程
audio_frame = self.asr_audio_queue.get()
```

**TTS 音频队列**：
```python
# 生产者：TTS 生成线程
self.tts.tts_audio_queue.put((SentenceType.FIRST, opus_packets, text))

# 消费者：音频发送线程
sentence_type, audios, text = self.tts.tts_audio_queue.get()
await sendAudioMessage(conn, sentence_type, audios, text)
```

### 7.3 状态机管理

```python
class ConnectionHandler:
    # 客户端状态
    self.client_abort = False          # 是否打断当前播放
    self.client_is_speaking = False    # 客户端是否在播放
    self.client_listen_mode = "auto"   # 监听模式：auto/manual
    
    # VAD 状态
    self.client_have_voice = False     # 当前是否有声音
    self.client_voice_stop = False     # 语音是否停止
    self.vad_last_voice_time = 0.0     # 最后一次说话时间
    
    # 会话状态
    self.just_woken_up = False         # 是否刚被唤醒
    self.close_after_chat = False      # 聊天结束后是否关闭
```

**状态流转**：
```
Idle → Listening (VAD 检测到声音)
     → Processing (ASR 识别中)
     → Speaking (TTS 播放中)
     → Idle (等待下一轮)
     
Listening → Abort (用户打断) → Idle
Speaking  → Abort (用户打断) → Idle
```

### 7.4 流式处理

**LLM 流式输出 + TTS 流式输入**：
```python
async def chat(self, text):
    buffer = ""
    async for chunk in self.llm.stream_chat(prompt):
        buffer += chunk
        
        # 检测到句子结束
        if is_sentence_complete(buffer):
            # 立即启动 TTS 转换
            tts_task = asyncio.create_task(
                self.tts.to_tts(buffer)
            )
            buffer = ""
```

### 7.5 音频流控

**问题**：快速发送音频帧会导致客户端缓冲区溢出

**解决方案**：`AudioRateController` 控制发送速率
```python
class AudioRateController:
    def __init__(self, sample_rate=24000, frame_duration=60):
        self.frame_interval = frame_duration / 1000.0  # 0.06s
    
    async def wait(self):
        """等待合适的发送时间"""
        await asyncio.sleep(self.frame_interval)

# 使用
for opus_packet in audios:
    await conn.websocket.send(opus_packet)
    await audio_rate_controller.wait()  # 精确控制间隔
```

---

## 八、性能优化策略

### 8.1 优化措施汇总

| 优化点 | 方法 | 效果 |
|--------|------|------|
| **音频流控** | `AudioRateController` 控制发送速率 | 避免网络拥塞，降低卡顿 |
| **分代 GC** | 定期回收年轻代对象（generation=0） | 减少 STW 时间至 <10ms |
| **连接复用** | 复用 WebSocket/TTS 连接 | 降低握手开销 30-50% |
| **唤醒词缓存** | 缓存唤醒词回复音频 | 响应时间从 2s 降至 200ms |
| **异步初始化** | `_background_initialize()` 不阻塞主循环 | 首屏加载时间减少 40% |
| **超时保护** | `_check_timeout()` 定时检查僵尸连接 | 防止内存泄漏 |
| **队列限流** | 限制 `asr_audio_queue` 大小 | 防止内存溢出 |
| **懒加载** | TTS 模块按需初始化 | 减少初始内存占用 |

### 8.2 GC 管理器配置

```yaml
# config.yaml
gc_manager:
  interval_seconds: 300        # 每 5 分钟执行一次
  generation: 0                # 只回收年轻代（快速）
  enable_adaptive: true        # 启用自适应调度
  memory_threshold_percent: 75 # 超过 75% 立即 GC
```

**效果对比**：
- **优化前**：全量回收，STW 时间 50-200ms
- **优化后**：年轻代回收，STW 时间 5-20ms

### 8.3 内存管理最佳实践

```python
# ✅ 推荐：及时释放大对象
async def process_audio(self, audio_data):
    result = await self.asr.recognize(audio_data)
    del audio_data  # 立即释放大音频数据
    return result

# ❌ 避免：长时间持有大对象
self.all_audio_history.append(audio_data)  # 会导致内存泄漏
```

---

## 九、扩展开发指南

### 9.1 添加新的 ASR Provider

**步骤 1**：创建 Provider 类
```python
# core/providers/asr/my_custom_asr.py
from core.providers.asr.base import ASRProviderBase

class MyCustomASRProvider(ASRProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__()
        self.api_key = config.get("api_key")
        self.api_url = config.get("api_url")
    
    async def speech_to_text(self, audio_data, session_id):
        # 调用你的 ASR API
        response = await self.call_api(audio_data)
        return response.text
```

**步骤 2**：注册 Provider
```python
# core/providers/asr/__init__.py
from .my_custom_asr import MyCustomASRProvider

ASR_PROVIDERS = {
    "fun_local": FunASRProvider,
    "doubao": DoubaoASRProvider,
    "my_custom": MyCustomASRProvider,  # 新增
}
```

**步骤 3**：配置使用
```yaml
# config.yaml
selected_module:
  ASR: MyCustomASR

ASR:
  MyCustomASR:
    type: my_custom
    api_key: your_api_key
    api_url: https://your-api.com/asr
```

### 9.2 添加功能插件

**步骤 1**：创建插件函数
```python
# plugins_func/functions/get_stock.py
from plugins_func.register import register_function, ActionResponse, Action

@register_function("get_stock", "查询股票价格", 
                   {"symbol": {"type": "string", "description": "股票代码"}})
def get_stock(symbol: str):
    """查询股票实时价格"""
    price = fetch_stock_price(symbol)
    return ActionResponse(Action.RESPONSE, f"{symbol} 当前价格：{price}元")
```

**步骤 2**：在配置中启用
```yaml
Intent:
  function_call:
    functions:
      - get_weather
      - get_stock  # 新增
```

### 9.3 自定义意图识别

```python
# core/handle/intentHandler.py
async def handle_user_intent(conn, text):
    """自定义意图识别逻辑"""
    # 1. 关键词匹配
    if "播放音乐" in text:
        await play_music(conn, extract_song_name(text))
        return True
    
    # 2. 正则表达式
    if re.match(r"查询.*天气", text):
        await get_weather(conn, extract_city(text))
        return True
    
    # 3. 调用 LLM 意图识别
    intent = await conn.intent.recognize(text)
    if intent:
        await execute_intent(conn, intent)
        return True
    
    return False  # 无匹配意图，进入普通对话
```

---

## 十、常见问题排查

### 10.1 连接问题

**Q: 客户端无法连接 WebSocket**

检查清单：
1. 防火墙是否开放 8000 端口
2. `config.yaml` 中 `server.ip` 是否为 `0.0.0.0`
3. 认证是否启用但未提供 token
4. 查看服务端日志：`tmp/server.log`

### 10.2 音频问题

**Q: 客户端听不到声音**

检查清单：
1. TTS 模块是否正确初始化（查看日志）
2. 音频格式是否匹配（Opus @ 24kHz）
3. 客户端是否正确解码 Opus
4. 测试 TTS：直接使用 EdgeTTS 生成音频文件

### 10.3 性能问题

**Q: 服务器响应慢**

优化建议：
1. 检查 LLM API 响应时间（通常占 60-80%）
2. 启用流式处理（`streaming: true`）
3. 使用本地 ASR/LLM 减少网络延迟
4. 调整 GC 间隔：`gc_manager.interval_seconds: 600`

---

## 附录

### A. 配置文件完整示例

参考 `config.yaml` 和 `docs/Deployment.md`

### B. 相关文档

- [部署指南](../docs/Deployment.md)
- [FAQ](../docs/FAQ.md)
- [固件配置](../docs/firmware-setting.md)
- [MCP 集成](../docs/mcp-endpoint-integration.md)

### C. 技术支持

- GitHub Issues: https://github.com/xinnan-tech/xiaozhi-esp32-server/issues
- 社区讨论区：项目 README 中的联系方式

---

**最后更新**: 2026-04-28  
**版本**: v2.1.0
