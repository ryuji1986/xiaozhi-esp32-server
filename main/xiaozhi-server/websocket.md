# WebSocket 语音消息数据格式规范

> **xiaozhi-server** WebSocket 协议中音频数据的传输格式详解

本文档详细说明 xiaozhi-server 模块在 WebSocket 通信中处理语音消息时的数据格式、编码方式和传输机制。

---

## 📋 目录

- [一、概述](#一概述)
- [二、音频参数配置](#二音频参数配置)
- [三、客户端 → 服务端（上行音频）](#三客户端--服务端上行音频)
- [四、服务端 → 客户端（下行音频）](#四服务端--客户端下行音频)
- [五、MQTT 网关模式](#五mqtt-网关模式)
- [六、Opus 编码细节](#六opus-编码细节)
- [七、数据处理流程](#七数据处理流程)
- [八、代码实现位置](#八代码实现位置)
- [九、常见问题](#九常见问题)

---

## 一、概述

### 1.1 协议特点

xiaozhi-server 使用 **WebSocket 二进制帧**传输音频数据，具有以下特点：

- ✅ **低延迟**：60ms 帧时长，实时交互
- ✅ **高压缩**：Opus 编码，压缩比约 20:1
- ✅ **双模式**：支持直连模式和 MQTT 网关模式
- ✅ **流式传输**：边录边传，边说边播

### 1.2 两种传输模式

| 模式 | 适用场景 | 数据格式 |
|------|---------|---------|
| **直连模式** | ESP32 设备/测试页面直连服务器 | 纯 Opus 数据 |
| **MQTT 网关模式** | 通过 MQTT 网关转发 | 16字节头部 + Opus 数据 |

---

## 二、音频参数配置

### 2.1 配置文件

在 `config.yaml` 中定义默认音频参数：

```yaml
xiaozhi:
  type: hello
  version: 1
  transport: websocket
  audio_params:
    format: opus           # 编码格式
    sample_rate: 24000     # 采样率：8000/12000/16000/24000/48000
    channels: 1            # 声道数（固定为1）
    frame_duration: 60     # 帧时长（毫秒）
```

### 2.2 握手时参数交换

**客户端发送 Hello 消息**：
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

**服务端响应 Hello 消息**：
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

### 2.3 参数说明

| 参数 | 类型 | 说明 | 可选值 |
|------|------|------|--------|
| `format` | string | 音频编码格式 | `"opus"`（唯一支持） |
| `sample_rate` | int | 采样率（Hz） | `8000`, `12000`, `16000`, `24000`, `48000` |
| `channels` | int | 声道数 | `1`（单声道，固定） |
| `frame_duration` | int | 帧时长（ms） | `60`（推荐）, `20`, `40` |

**推荐配置**：
- **高采样率**：24000 Hz（音质更好）
- **低带宽**：16000 Hz（节省流量）
- **帧时长**：60 ms（平衡延迟和效率）

---

## 三、客户端 → 服务端（上行音频）

### 3.1 直连模式（标准格式）

#### **数据格式**
```
┌─────────────────────────┐
│   Opus 编码的音频帧      │
│   (纯二进制数据)          │
└─────────────────────────┘
```

#### **特征**
- **编码格式**：Opus
- **采样率**：24000 Hz（或握手时协商的值）
- **声道数**：1（单声道）
- **位深度**：16-bit PCM 编码后转 Opus
- **帧时长**：60 ms
- **帧大小**：约 60-120 字节/帧（取决于比特率）
- **传输方式**：WebSocket Binary Frame

#### **代码示例（客户端）**
```javascript
// JavaScript 客户端录音并发送
const opusEncoder = new OpusEncoder(24000, 1); // 24kHz, 单声道
const frameSize = 1440; // 24000 * 60 / 1000

while (recording) {
    // 获取 PCM 数据（Int16Array）
    const pcmData = getPCMFrame(frameSize);
    
    // 编码为 Opus
    const opusFrame = opusEncoder.encode(pcmData);
    
    // 通过 WebSocket 发送
    websocket.send(opusFrame.buffer);
}
```

#### **代码位置**
[connection.py:369-382](file:///D:/github/xiaozhi-esp32-server/main/xiaozhi-server/core/connection.py#L369-L382)
```python
async def _route_message(self, message):
    """消息路由"""
    if isinstance(message, str):
        await handleTextMessage(self, message)
    elif isinstance(message, bytes):
        # 直连模式：直接放入队列
        self.asr_audio_queue.put(message)
```

---

### 3.2 MQTT 网关模式（带16字节头部）

#### **数据格式**
```
┌──────────┬──────────┬──────────┬──────────┬──────────────┐
│ Type(1B) │ Resvd(1B)│ Seq(2B)  │ Timestamp│ Audio Length │
│          │          │          │  (4B)    │    (4B)      │
├──────────┴──────────┴──────────┴──────────┴──────────────┤
│                    Opus 音频数据                           │
│                   (可变长度)                               │
└──────────────────────────────────────────────────────────┘
```

#### **头部结构（16字节）**

| 偏移 | 长度 | 字段 | 字节序 | 说明 |
|------|------|------|--------|------|
| 0 | 1 byte | type | - | 固定为 `1`（音频数据类型） |
| 1 | 1 byte | reserved | - | 保留字段，填 `0` |
| 2-3 | 2 bytes | sequence | Big-Endian | 序列号，从 0 递增 |
| 4-7 | 4 bytes | timestamp | Big-Endian | 时间戳（毫秒） |
| 8-11 | 4 bytes | payload_length | Big-Endian | 音频数据长度 |
| 12-15 | 4 bytes | audio_length | Big-Endian | 音频数据长度（冗余） |
| 16+ | N bytes | audio_data | - | Opus 音频数据 |

#### **代码位置**
[connection.py:384-415](file:///D:/github/xiaozhi-esp32-server/main/xiaozhi-server/core/connection.py#L384-L415)
```python
async def _process_mqtt_audio_message(self, message):
    """处理来自MQTT网关的音频消息"""
    try:
        # 提取头部信息
        timestamp = int.from_bytes(message[8:12], "big")
        audio_length = int.from_bytes(message[12:16], "big")

        # 提取音频数据
        if audio_length > 0 and len(message) >= 16 + audio_length:
            audio_data = message[16 : 16 + audio_length]
            # 基于时间戳进行排序处理
            self._process_websocket_audio(audio_data, timestamp)
            return True
    except Exception as e:
        self.logger.bind(tag=TAG).error(f"解析WebSocket音频包失败: {e}")
    
    return False
```

#### **乱序包处理**
```python
def _process_websocket_audio(self, audio_data, timestamp):
    """处理WebSocket格式的音频包（支持乱序）"""
    if not hasattr(self, "audio_timestamp_buffer"):
        self.audio_timestamp_buffer = {}
        self.last_processed_timestamp = 0
        self.max_timestamp_buffer_size = 20

    # 如果时间戳是递增的，直接处理
    if timestamp >= self.last_processed_timestamp:
        self.asr_audio_queue.put(audio_data)
        self.last_processed_timestamp = timestamp
        
        # 处理缓冲区中的后续包
        self._flush_buffered_audio()
    else:
        # 乱序包，暂存到缓冲区
        if len(self.audio_timestamp_buffer) < self.max_timestamp_buffer_size:
            self.audio_timestamp_buffer[timestamp] = audio_data
```

---

## 四、服务端 → 客户端（下行音频）

### 4.1 直连模式（标准格式）

#### **数据格式**
```
┌─────────────────────────┐
│   Opus 编码的音频帧      │
│   (纯二进制数据)          │
└─────────────────────────┘
```

与上行格式完全相同。

#### **发送流程**
```python
# sendAudioHandle.py
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

#### **音频流控**
为避免客户端缓冲区溢出，使用 `AudioRateController` 控制发送速率：

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
    await audio_rate_controller.wait()  # 精确间隔 60ms
```

---

### 4.2 MQTT 网关模式（带16字节头部）

#### **数据格式**
```
┌──────────┬──────────┬──────────┬──────────┬──────────────┐
│ Type(1B) │ Resvd(1B)│ Seq(2B)  │ Timestamp│ Audio Length │
│          │          │          │  (4B)    │    (4B)      │
├──────────┴──────────┴──────────┴──────────┴──────────────┤
│                    Opus 音频数据                           │
└──────────────────────────────────────────────────────────┘
```

#### **头部封装代码**
[sendAudioHandle.py:79-100](file:///D:/github/xiaozhi-esp32-server/main/xiaozhi-server/core/handle/sendAudioHandle.py#L79-L100)
```python
async def _send_to_mqtt_gateway(conn, opus_packet, timestamp, sequence):
    """发送带16字节头部的opus数据包给mqtt_gateway"""
    # 为opus数据包添加16字节头部
    header = bytearray(16)
    header[0] = 1  # type
    header[2:4] = len(opus_packet).to_bytes(2, "big")  # payload length
    header[4:8] = sequence.to_bytes(4, "big")  # sequence
    header[8:12] = timestamp.to_bytes(4, "big")  # 时间戳
    header[12:16] = len(opus_packet).to_bytes(4, "big")  # opus长度

    # 发送包含头部的完整数据包
    complete_packet = bytes(header) + opus_packet
    await conn.websocket.send(complete_packet)
```

---

## 五、MQTT 网关模式

### 5.1 为什么需要 MQTT 网关模式？

**应用场景**：
- ESP32 设备通过 MQTT 连接到网关
- 网关将 MQTT 消息转换为 WebSocket 转发到服务器
- 需要额外的元数据（时间戳、序列号）来处理网络抖动和乱序

**优势**：
- ✅ **时间戳排序**：处理网络延迟导致的乱序包
- ✅ **序列号检测**：发现丢包并重传
- ✅ **缓冲机制**：容忍短暂的网络波动

### 5.2 判断连接来源

```python
# connection.py
async def handle_connection(self, ws):
    # 检查是否来自MQTT连接
    request_path = ws.request.path
    self.conn_from_mqtt_gateway = request_path.endswith("?from=mqtt_gateway")
    if self.conn_from_mqtt_gateway:
        self.logger.bind(tag=TAG).info("连接来自:MQTT网关")
```

### 5.3 数据格式对比

| 特性 | 直连模式 | MQTT 网关模式 |
|------|---------|--------------|
| **头部** | 无 | 16 字节 |
| **音频编码** | Opus | Opus |
| **采样率** | 24000 Hz | 24000 Hz |
| **帧时长** | 60 ms | 60 ms |
| **帧大小** | 60-120 bytes | 76-136 bytes (含头部) |
| **时间戳** | 无 | 有（用于排序） |
| **序列号** | 无 | 有（用于丢包检测） |
| **乱序处理** | 不支持 | 支持（20帧缓冲） |
| **适用场景** | WebSocket 直连 | 通过 MQTT 网关转发 |

---

## 六、Opus 编码细节

### 6.1 编码器配置

[opus_encoder_utils.py](file:///D:/github/xiaozhi-esp32-server/main/xiaozhi-server/core/utils/opus_encoder_utils.py)
```python
class OpusEncoderUtils:
    def __init__(self, sample_rate: int, channels: int, frame_size_ms: int):
        self.sample_rate = sample_rate      # 24000 Hz
        self.channels = channels            # 1 (单声道)
        self.frame_size_ms = frame_size_ms  # 60 ms
        
        # 计算每帧样本数
        self.frame_size = (sample_rate * frame_size_ms) // 1000
        # = 24000 * 60 / 1000 = 1440 samples
        
        # 总帧大小（字节）
        self.total_frame_size = self.frame_size * channels * 2
        # = 1440 * 1 * 2 = 2880 bytes (16-bit PCM)
        
        # 创建 Opus 编码器
        self.encoder = Encoder(
            sample_rate, 
            channels, 
            APPLICATION_AUDIO  # 音频优化模式
        )
        self.encoder.bitrate = 24000   # 比特率 24kbps
        self.encoder.complexity = 10   # 最高质量 (0-10)
```

### 6.2 编码流程

```python
# PCM → Opus 编码
def encode_pcm_to_opus(self, pcm_data: bytes) -> bytes:
    """将 PCM 数据编码为 Opus"""
    # 1. 转换为 numpy 数组（int16）
    pcm_array = np.frombuffer(pcm_data, dtype=np.int16)
    
    # 2. 编码为 Opus
    opus_data = self.encoder.encode(pcm_array, self.frame_size)
    
    return opus_data  # 约 60-120 bytes
```

### 6.3 解码流程

[util.py:391-418](file:///D:/github/xiaozhi-esp32-server/main/xiaozhi-server/core/utils/util.py#L391-L418)
```python
def opus_datas_to_wav_bytes(opus_datas, sample_rate=16000, channels=1):
    """将opus帧列表解码为wav字节流"""
    decoder = opuslib_next.Decoder(sample_rate, channels)
    
    pcm_datas = []
    frame_duration = 60  # ms
    frame_size = int(sample_rate * frame_duration / 1000)  # 960 @ 16kHz
    
    for opus_frame in opus_datas:
        # 解码为 PCM（返回 bytes，2字节/采样点）
        pcm = decoder.decode(opus_frame, frame_size)
        pcm_datas.append(pcm)
    
    # 合并 PCM 数据
    pcm_bytes = b"".join(pcm_datas)
    
    # 写入 WAV 文件头
    wav_buffer = BytesIO()
    with wave.open(wav_buffer, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    
    return wav_buffer.getvalue()
```

### 6.4 压缩效果

| 原始 PCM | Opus 编码 | 压缩比 |
|----------|-----------|--------|
| 2880 bytes (60ms @ 24kHz) | 60-120 bytes | ~24:1 |
| 1920 bytes (60ms @ 16kHz) | 50-100 bytes | ~19:1 |

**比特率选择**：
- **24 kbps**：高质量，适合 WiFi 环境
- **16 kbps**：中等质量，平衡音质和带宽
- **12 kbps**：低带宽，适合移动网络

---

## 七、数据处理流程

### 7.1 接收流程（客户端 → 服务端）

```
┌─────────────────────────────────────────────────────────┐
│              音频接收完整流程                             │
└─────────────────────────────────────────────────────────┘

1. WebSocket 接收二进制帧
   ↓
2. 判断连接类型
   ├─ 直连模式 → 直接使用原始数据
   └─ MQTT 网关 → 解析16字节头部，提取 Opus 数据
   ↓
3. 放入 asr_audio_queue 队列
   ↓
4. ASR 后台线程消费队列
   ↓
5. VAD 检测（是否有声音）
   ├─ have_voice = True  → 累积音频帧
   └─ have_voice = False → 静音计时
   ↓
6. 静音超时（默认 800ms）→ 触发 ASR 识别
   ↓
7. Opus 解码为 PCM
   ↓
8. ASR 识别 → 输出文本
   ↓
9. 进入对话流程（意图识别 → LLM → TTS）
```

**关键代码**：
[receiveAudioHandle.py:17-30](file:///D:/github/xiaozhi-esp32-server/main/xiaozhi-server/core/handle/receiveAudioHandle.py#L17-L30)
```python
async def handleAudioMessage(conn, audio):
    """处理音频帧"""
    # 1. VAD 检测
    have_voice = conn.vad.is_vad(conn, audio)
    
    # 2. 长时间空闲检测
    await no_voice_close_connect(conn, have_voice)
    
    # 3. 发送给 ASR 处理
    await conn.asr.receive_audio(conn, audio, have_voice)
```

---

### 7.2 发送流程（服务端 → 客户端）

```
┌─────────────────────────────────────────────────────────┐
│              音频发送完整流程                             │
└─────────────────────────────────────────────────────────┘

1. LLM 流式输出文本
   ↓
2. 检测到句子结束
   ↓
3. TTS 转换文本 → 音频（WAV/MP3）
   ↓
4. 转换为 PCM（16kHz, 16-bit, 单声道）
   ↓
5. Opus 编码
   ↓
6. 判断连接类型
   ├─ 直连模式 → 直接发送 Opus 数据
   └─ MQTT 网关 → 添加16字节头部
   ↓
7. 音频流控（60ms 间隔）
   ↓
8. WebSocket Binary Frame 发送
   ↓
9. 客户端接收并播放
```

**关键代码**：
[sendAudioHandle.py:103-150](file:///D:/github/xiaozhi-esp32-server/main/xiaozhi-server/core/handle/sendAudioHandle.py#L103-L150)
```python
async def sendAudio(conn, audios, frame_duration=60):
    """发送音频包，使用 AudioRateController 进行流量控制"""
    rate_controller = AudioRateController(
        sample_rate=conn.sample_rate,
        frame_duration=frame_duration
    )
    
    # 预缓冲：快速发送前几帧，减少初始延迟
    pre_buffer_count = min(PRE_BUFFER_COUNT, len(audios))
    for i in range(pre_buffer_count):
        await conn.websocket.send(audios[i])
    
    # 等待预缓冲播放完成
    await asyncio.sleep(pre_buffer_count * frame_duration / 1000.0)
    
    # 剩余帧按节奏发送
    for i in range(pre_buffer_count, len(audios)):
        await conn.websocket.send(audios[i])
        await rate_controller.wait()
```

---

## 八、代码实现位置

### 8.1 核心文件清单

| 功能 | 文件路径 | 关键行号 |
|------|---------|---------|
| **消息路由** | [core/connection.py](file:///D:/github/xiaozhi-esp32-server/main/xiaozhi-server/core/connection.py) | 369-382 |
| **MQTT 音频解析** | [core/connection.py](file:///D:/github/xiaozhi-esp32-server/main/xiaozhi-server/core/connection.py) | 384-415 |
| **VAD 检测** | [core/handle/receiveAudioHandle.py](file:///D:/github/xiaozhi-esp32-server/main/xiaozhi-server/core/handle/receiveAudioHandle.py) | 17-30 |
| **音频发送** | [core/handle/sendAudioHandle.py](file:///D:/github/xiaozhi-esp32-server/main/xiaozhi-server/core/handle/sendAudioHandle.py) | 103-150 |
| **MQTT 音频封装** | [core/handle/sendAudioHandle.py](file:///D:/github/xiaozhi-esp32-server/main/xiaozhi-server/core/handle/sendAudioHandle.py) | 79-100 |
| **Opus 编码工具** | [core/utils/opus_encoder_utils.py](file:///D:/github/xiaozhi-esp32-server/main/xiaozhi-server/core/utils/opus_encoder_utils.py) | 全文 |
| **音频转换工具** | [core/utils/util.py](file:///D:/github/xiaozhi-esp32-server/main/xiaozhi-server/core/utils/util.py) | 251-420 |
| **音频流控** | [core/utils/audioRateController.py](file:///D:/github/xiaozhi-esp32-server/main/xiaozhi-server/core/utils/audioRateController.py) | 全文 |

### 8.2 客户端参考实现

**JavaScript 客户端**：
- [test/js/core/network/websocket.js](file:///D:/github/xiaozhi-esp32-server/main/xiaozhi-server/test/js/core/network/websocket.js) - WebSocket 连接管理
- [test/js/core/audio/recorder.js](file:///D:/github/xiaozhi-esp32-server/main/xiaozhi-server/test/js/core/audio/recorder.js) - 录音和 Opus 编码
- [test/js/core/audio/opus-codec.js](file:///D:/github/xiaozhi-esp32-server/main/xiaozhi-server/test/js/core/audio/opus-codec.js) - Opus 编解码器

---

## 九、常见问题

### 9.1 音频质量问题

**Q: 客户端听到的声音模糊或有杂音**

**排查步骤**：
1. 检查采样率是否匹配（客户端和服务端都应为 24000 Hz）
2. 确认 Opus 编码器参数正确（frame_size = 1440 @ 24kHz）
3. 检查网络延迟，启用音频流控
4. 测试 TTS：直接保存音频文件检查音质

**解决方案**：
```yaml
# config.yaml
xiaozhi:
  audio_params:
    sample_rate: 24000  # 确保与客户端一致
    frame_duration: 60  # 推荐 60ms
```

---

### 9.2 延迟问题

**Q: 从说话到听到回复延迟过高（>3秒）**

**优化建议**：
1. **启用流式处理**：LLM 和 TTS 都使用流式 API
2. **减少帧时长**：从 60ms 改为 20ms（增加带宽）
3. **优化网络**：使用本地部署的 ASR/LLM/TTS
4. **调整 VAD 参数**：减少静音检测时间

```yaml
# config.yaml
close_connection_no_voice_time: 60  # 减少空闲超时
```

---

### 9.3 丢包问题

**Q: 音频断断续续，有丢包现象**

**解决方案**：
1. **MQTT 网关模式**：启用序列号和重传机制
2. **增加缓冲**：客户端增加音频缓冲队列
3. **降低比特率**：从 24kbps 降到 16kbps
4. **检查网络**：确保 WebSocket 连接稳定

---

### 9.4 内存泄漏

**Q: 服务器运行一段时间后内存持续增长**

**排查方法**：
1. 检查 `asr_audio_queue` 是否有积压
2. 确认音频文件及时删除（`delete_audio: true`）
3. 启用 GC 管理器定期清理

```yaml
# config.yaml
gc_manager:
  interval_seconds: 300
  generation: 0
  enable_adaptive: true
```

---

### 9.5 兼容性测试

**测试工具**：
- 使用 `test/test_page.html` 进行浏览器测试
- 使用 Wireshark 抓包分析 WebSocket 帧
- 使用 FFmpeg 验证 Opus 编码

```bash
# 查看 WebSocket 流量
wireshark -i any -f "tcp port 8000"

# 测试 Opus 编码
ffmpeg -i test.wav -c:a libopus -b:a 24k test.opus
```

---

## 附录

### A. Opus 编码规格

| 参数 | 值 |
|------|-----|
| 编码格式 | Opus (RFC 6716) |
| 应用模式 | APPLICATION_AUDIO |
| 比特率 | 24000 bps |
| 复杂度 | 10 (最高) |
| 帧时长 | 60 ms |
| 采样率 | 24000 Hz |
| 声道数 | 1 (单声道) |

### B. WebSocket 帧格式

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-------+-+-------------+-------------------------------+
|F|R|R|R| opcode|M| Payload len |    Extended payload length    |
|I|S|S|S|  (4)  |A|     (7)     |             (16/64)           |
|N|V|V|V|       |S|             |   (if payload len==126/127)   |
| |1|2|3|       |K|             |                               |
+-+-+-+-+-------+-+-------------+ - - - - - - - - - - - - - - - +
|     Extended payload length continued, if payload len == 127  |
+ - - - - - - - - - - - - - - - +-------------------------------+
|                               |Masking-key, if MASK set to 1  |
+-------------------------------+-------------------------------+
| Masking-key (continued)       |          Payload Data         |
+-------------------------------- - - - - - - - - - - - - - - - +
:                     Payload Data continued ...                :
+ - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - +
|                     Payload Data continued ...                |
+---------------------------------------------------------------+
```

**关键字段**：
- **opcode**：`0x2` (Binary Frame)
- **MASK**：客户端发送时为 `1`，服务端发送时为 `0`
- **Payload Data**：Opus 音频数据（或带16字节头部的数据）

### C. 相关文档

- [Opus 编码规范](https://www.rfc-editor.org/rfc/rfc6716)
- [WebSocket 协议](https://www.rfc-editor.org/rfc/rfc6455)
- [xiaozhi-server 架构概览](overview.md)
- [部署指南](../docs/Deployment.md)

---

**最后更新**: 2026-04-28  
**版本**: v2.1.0  
**维护者**: xiaozhi-esp32-server 社区
