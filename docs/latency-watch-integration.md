# 语音交互流程耗时统计功能（LatencyWatch）

## 📋 功能概述

LatencyWatch 是一个用于监控语音交互全流程耗时的工具，能够精确统计以下环节的耗时：

- ⏱️ **WebSocket 连接建立**
- 🎤 **ASR 语音识别**（开始/结束）
- ⏳ **用户等待时间**（从说完话到听到回复）⭐ 新增
- 🧠 **LLM 大模型推理**（开始/结束）
- 🔊 **TTS 语音合成**（开始/结束）

在一轮语音交互结束时，会自动打印完整的耗时统计报告。

---

## 🎯 核心特性

### 1. 全流程监控

```
用户说话 → WebSocket → ASR → LLM → TTS → 播放音频
            ↑          ↑      ↑      ↑
         记录时间   记录开始  记录开始 记录开始
                    记录结束  记录结束 记录结束
```

### 2. 自动性能分析

根据各环节耗时，自动提供优化建议：
- ⚠️ ASR 耗时过长（> 2s）
- ⚠️ LLM 推理较慢（> 3s）
- ⚠️ TTS 合成较慢（> 2s）
- ⚠️ 总耗时过长（> 8s）

### 3. 详细耗时报告

```
======================================================================
[LatencyWatch] 语音交互耗时统计 - Session abc12345...
======================================================================
  📊 总耗时: 5.234s
----------------------------------------------------------------------
  ⏱️  WebSocket → ASR: 0.123s (2.4%) - 等待用户说话
  🎤 ASR 识别: 0.876s (16.7%) - 语音转文字
  ⏱️  ASR → LLM: 0.045s (0.9%) - 意图处理
  🧠 LLM 推理: 2.345s (44.8%) - 生成回复
  ⏱️  LLM → TTS: 0.067s (1.3%) - 准备合成
  🔊 TTS 合成: 1.778s (34.0%) - 文字转语音
----------------------------------------------------------------------
  ✅ 性能表现良好
======================================================================
```

---

## 🔧 使用方法

### 自动集成（无需额外配置）

LatencyWatch 已自动集成到语音交互流程中，**无需任何额外配置**。

当用户与设备进行一轮完整对话后，系统会自动在日志中输出耗时统计。

### 查看日志

运行服务器后，在控制台或日志文件中搜索 `[LatencyWatch]` 即可看到耗时统计。

```bash
# 启动服务器
cd D:\github\xiaozhi-esp32-server\main\xiaozhi-server
python app.py

# 进行一轮对话后，查看日志
# 会看到类似以下的输出：
```

---

## 📊 日志示例

### 调试级别日志（各阶段标记）

```
[LatencyWatch] Session abc12345... - WebSocket 连接建立
[LatencyWatch] Session abc12345... - ASR 开始
[LatencyWatch] Session abc12345... - ASR 完成 | 耗时: 0.876s | 文本: '你好小智'
[LatencyWatch] Session abc12345... - LLM 调用开始
[LatencyWatch] Session abc12345... - LLM 完成 | 耗时: 2.345s | 响应长度: 100 字符
[LatencyWatch] Session abc12345... - TTS 开始
[LatencyWatch] Session abc12345... - TTS 完成 | 耗时: 1.778s
```

### 信息级别日志（完整报告）

```
======================================================================
[LatencyWatch] 语音交互耗时统计 - Session abc12345...
======================================================================
  📊 总耗时: 5.234s
----------------------------------------------------------------------
  ⏱️  WebSocket → ASR: 0.123s (2.4%) - 等待用户说话
  🎤 ASR 识别: 0.876s (16.7%) - 语音转文字
  ⏳ 用户等待: 2.457s (46.9%) - 说完话到听到回复 ⭐ 关键指标
  ⏱️  ASR → LLM: 0.045s (0.9%) - 意图处理
  🧠 LLM 推理: 2.345s (44.8%) - 生成回复
  ⏱️  LLM → TTS: 0.067s (1.3%) - 准备合成
  🔊 TTS 合成: 1.778s (34.0%) - 文字转语音
----------------------------------------------------------------------
  ✅ 性能表现良好
======================================================================
```

### 警告级别日志（性能建议）

```
----------------------------------------------------------------------
  💡 性能优化建议:
    ⚠️  用户等待时间较长 (4.567s)，建议优化 LLM 响应速度或使用流式输出
    ⚠️  LLM 推理较慢 (3.456s)，建议使用更快的模型或优化 prompt
    ⚠️  TTS 合成较慢 (2.234s)，建议使用流式 TTS 或更快的服务
```

---

## 🛠️ 技术实现

### 核心文件

1. **`core/utils/latency_watch.py`** - LatencyWatch 核心类
2. **`core/connection.py`** - 集成点：WebSocket 连接、LLM 调用
3. **`core/providers/asr/base.py`** - 集成点：ASR 识别
4. **`core/handle/sendAudioHandle.py`** - 集成点：TTS 合成

### 关键代码位置

#### 1. ConnectionHandler 初始化

```python
# core/connection.py
class ConnectionHandler:
    def __init__(self, ...):
        
        # 初始化延迟监控器
        self.latency_watch = LatencyWatch(self.session_id)
```

#### 2. WebSocket 连接建立

```python
# core/connection.py
async def handle_connection(self, ws):
    
    # 认证通过,继续处理
    self.websocket = ws
    
    # 标记 WebSocket 连接建立
    self.latency_watch.mark_ws_connected()
```

#### 3. ASR 识别

```python
# core/providers/asr/base.py
async def handle_voice_stop(self, conn, asr_audio_task):
    # 标记 ASR 开始
    if hasattr(conn, 'latency_watch'):
        conn.latency_watch.mark_asr_start()
    
    # ... ASR 处理逻辑 ...
    
    # 标记 ASR 结束
    if hasattr(conn, 'latency_watch'):
        asr_text = raw_text.get('content', '') if isinstance(raw_text, dict) else raw_text
        conn.latency_watch.mark_asr_end(asr_text)
```

#### 4. LLM 推理

```python
# core/connection.py
def chat(self, query, depth=0):
    try:
        # 标记 LLM 调用开始
        self.latency_watch.mark_llm_start()
        
        # ... LLM 处理逻辑 ...
        
        # 标记 LLM 调用结束
        self.latency_watch.mark_llm_end(len(text_buff))
```

#### 5. TTS 合成

```python
# core/handle/sendAudioHandle.py
async def sendAudioMessage(conn, sentenceType, audios, text, sentence_id=None):
    if conn.tts.tts_audio_first_sentence:
        # 标记 TTS 开始
        if hasattr(conn, 'latency_watch'):
            conn.latency_watch.mark_tts_start()
    
    # ... TTS 处理逻辑 ...
    
    if sentenceType == SentenceType.LAST:
        # 标记 TTS 结束
        if hasattr(conn, 'latency_watch'):
            conn.latency_watch.mark_tts_end()
        
        # 标记交互完成并打印耗时统计
        if hasattr(conn, 'latency_watch'):
            conn.latency_watch.mark_interaction_complete()
```

---

## 🧪 测试方法

### 单元测试

运行测试脚本验证 LatencyWatch 基本功能：

```bash
cd D:\github\xiaozhi-esp32-server\main\xiaozhi-server
python test/test_latency_watch.py
```

### 集成测试

1. 启动服务器
2. 使用 ESP32 设备或测试页面连接
3. 进行一轮完整对话
4. 查看控制台日志中的耗时统计

---

## 📈 性能指标参考

### 正常范围

| 环节 | 正常耗时 | 警告阈值 | 说明 |
|------|---------|---------|------|
| **ASR 识别** | 0.5-1.5s | > 2.0s | 取决于网络和 ASR 服务 |
| **用户等待时间** ⭐ | 2.0-4.0s | > 4.0s | **用户体验核心指标** |
| **LLM 推理** | 1.0-3.0s | > 3.0s | 取决于模型和响应长度 |
| **TTS 合成** | 0.5-2.0s | > 2.0s | 取决于 TTS 服务和文本长度 |
| **总耗时** | 3.0-6.0s | > 8.0s | 用户体验关键指标 |

> ⭐ **用户等待时间**是最重要的用户体验指标，它直接影响用户对系统响应速度的感知。

### 优化建议

#### 用户等待时间过长

用户等待时间 = LLM 推理时间 + TTS 准备时间 + 网络延迟

- ✅ 使用流式 LLM 输出，边生成边发送
- ✅ 使用更快的 LLM 模型（如 qwen-flash）
- ✅ 优化 Prompt，减少上下文长度
- ✅ 使用流式 TTS，第一帧音频立即发送
- ✅ 降低 max_tokens 限制

#### ASR 耗时过长

- ✅ 检查网络连接质量
- ✅ 考虑使用本地 ASR（如 FunASR）
- ✅ 切换到更快的云端 ASR 服务

#### LLM 耗时过长

- ✅ 使用更快的模型（如 qwen-flash vs qwen-max）
- ✅ 优化 Prompt，减少上下文长度
- ✅ 降低 max_tokens 限制
- ✅ 启用流式输出

#### TTS 耗时过长

- ✅ 使用流式 TTS（如 AliyunStreamTTS）
- ✅ 选择 PCM 格式避免格式转换
- ✅ 缩短回复文本长度

---

## 🔍 常见问题

### Q1: 为什么看不到耗时统计？

**A:** 确保完成了一轮完整的对话（从用户说话到 TTS 播放完毕）。如果对话被中断或取消，可能不会生成统计。

### Q2: 如何调整日志级别？

**A:** 修改 `config.yaml` 中的日志配置：

```yaml
log:
  level: INFO  # DEBUG 级别会显示更多详细信息
```

### Q3: 能否禁用此功能？

**A:** 目前默认启用，如需禁用，可以注释掉相关调用代码。但由于性能开销极小（仅记录时间戳），建议保持启用。

### Q4: 统计数据是否持久化？

**A:** 目前仅在内存中统计，不会持久化到文件或数据库。如需长期保存，可扩展 `get_summary()` 方法将数据写入日志或数据库。

---

## 🚀 扩展开发

### 添加新的监控点

在 `latency_watch.py` 中添加新的标记方法：

```python
def mark_custom_stage(self, stage_name: str):
    """标记自定义阶段"""
    timestamp = time.time()
    self.timestamps[f'{stage_name}_start'] = timestamp
    logger.bind(tag=TAG).debug(f"[LatencyWatch] {stage_name} 开始")
```

### 导出统计数据

扩展 `get_summary()` 方法，支持导出为 JSON 或 CSV：

```python
def export_to_json(self, filepath: str):
    """导出统计数据到 JSON 文件"""
    import json
    summary = self.get_summary()
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
```

### 集成监控系统

可以将统计数据发送到 Prometheus、Grafana 等监控系统，实现实时监控和告警。

---

## 📝 更新日志

### v1.0.0 (2024-XX-XX)

- ✅ 初始版本发布
- ✅ 支持 WebSocket、ASR、LLM、TTS 全流程监控
- ✅ 自动生成耗时统计报告
- ✅ 提供性能优化建议
- ✅ 集成到语音交互流程

---

## 👥 贡献者

- 开发：AI Assistant
- 审核：待定

---

## 📄 许可证

本项目遵循 MIT 许可证。
