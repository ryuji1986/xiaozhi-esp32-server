# 有界长度参数容量估算与调优指南（ASR / LLM / TTS）

> 适用范围：`main/xiaozhi-server` 当前已引入的有界保护策略，包括 ASR 队列上限、LLM/VLLM 文本累积上限、TTS 并发上限。

## 1. 当前代码中已生效的“有界”策略

### 1.1 ASR 音频队列（每连接）

- `asr_audio_queue_maxsize`：队列最大长度（默认 `100`）
- `asr_audio_queue_drop_oldest`：满载时丢最旧（默认 `true`）或丢当前

建议用于限制单连接突发音频输入导致的内存增长。

### 1.2 LLM/VLLM 流式累积保护（每连接）

- `llm_stream_max_chars`：流式回复缓存上限（默认 `12000`）
- `llm_tool_arguments_max_chars`：工具参数累计上限（默认 `8000`）
- `llm_tool_calls_max_count`：单轮工具调用最大数量（默认 `8`）

建议用于限制异常长输出、异常函数调用流导致的字符串内存失控。

### 1.3 OpenAI TTS 并发保护（全局）

- `max_concurrency`：全局 TTS 并发数上限（默认 `64`）
- `request_timeout`：请求超时（默认 `30s`）

建议用于限制外部厂商接口抖动引发的并发放大效应。

---

## 2. ASR 队列长度到内存的估算方法

### 2.1 单连接估算

```
Mem_per_conn ≈ queue_maxsize × avg_chunk_bytes × overhead_factor
```

参数说明：

- `queue_maxsize`：队列长度上限
- `avg_chunk_bytes`：单音频包平均字节数（建议用线上统计均值/P95）
- `overhead_factor`：Python 对象与容器开销系数（经验值 1.2~1.5）

### 2.2 全机估算

```
Mem_total ≈ N_peak × Mem_per_conn
```

- `N_peak`：峰值并发连接数

### 2.3 预算反推队列长度

若分配给 ASR 队列的总内存预算是 `B_asr`，则：

```
queue_maxsize ≤ B_asr / (N_peak × avg_chunk_bytes × overhead_factor)
```

建议乘以 0.7~0.8 安全系数后再落地。

---

## 3. 参数区间建议表（生产起步）

> 下表是“起步区间”，上线前请压测验证并按真实音频包大小修正。

| 资源规模（单实例） | 峰值并发连接（建议） | `asr_audio_queue_maxsize` | `asr_audio_queue_drop_oldest` | `llm_stream_max_chars` | `llm_tool_arguments_max_chars` | `llm_tool_calls_max_count` | `max_concurrency` (OpenAI TTS) |
|---|---:|---:|---|---:|---:|---:|---:|
| 4C / 8GB  | 300~800   | 50~120  | `true` | 6000~12000  | 2000~8000  | 4~8  | 16~48 |
| 8C / 16GB | 800~2000  | 80~200  | `true` | 8000~16000  | 4000~12000 | 6~12 | 32~96 |
| 16C / 32GB| 2000~5000 | 120~300 | `true` | 12000~24000 | 8000~20000 | 8~16 | 64~192 |

### 3.1 解释

- `asr_audio_queue_maxsize` 越大，抗瞬时抖动能力越强，但会增加排队时延与内存。
- `drop_oldest=true` 适合实时语音交互（优先保留新音频）。
- `llm_stream_max_chars` 越大，长回复完整度越高，但占用更多内存。
- `llm_tool_calls_max_count` 应与工具编排能力匹配，过大易被异常输出放大。
- `max_concurrency` 不应盲目跟随 CPU 提升，需要结合第三方厂商限流配额。

---

## 4. 服务器扩容后的调参策略

### 4.1 推荐步骤（小步快跑）

1. **先定预算**：给 ASR 队列总预算分配 10%~20% 进程内存。
2. **反推队列**：按公式计算理论上限，再乘 0.75 安全系数。
3. **小步上调**：每次仅提升 10%~30%，观察 24~72 小时。
4. **看指标回归**：若 P99 上升但丢包下降，说明队列过深，应回调。

### 4.2 观察指标

- 内存：RSS、GC 时间占比
- 语音链路：ASR 端到端延迟 P95/P99
- 稳定性：队列满载告警频率、429/5xx 比例
- 体验：用户“打断/回声/卡顿”投诉量

---

## 5. 常见误区

1. **只加队列长度，不做限流**：会把错误从丢包变成延迟恶化。
2. **只看平均值，不看P99**：高并发下尾延迟才是风险核心。
3. **一次性大幅提升参数**：容易触发级联故障，排障困难。
4. **忽略第三方配额**：TTS 并发超配额后 429 会引发重试风暴。

---

## 6. 建议的默认起步配置

```yaml
asr_audio_queue_maxsize: 100
asr_audio_queue_drop_oldest: true

llm_stream_max_chars: 12000
llm_tool_arguments_max_chars: 8000
llm_tool_calls_max_count: 8

# OpenAI TTS
max_concurrency: 64
request_timeout: 30
```

> 若是 4C/8GB 环境可适当保守：`asr_audio_queue_maxsize=60~80`, `max_concurrency=16~32`。
