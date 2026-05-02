"""
语音交互流程耗时统计模块
用于监控 WebSocket 连接、ASR、LLM、TTS 各环节的性能
"""
import time
from typing import Dict, Optional
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()


class LatencyWatch:
    """语音交互流程耗时监控器"""

    def __init__(self, session_id: str):
        """
        初始化延迟监控器
        
        Args:
            session_id: 会话ID
        """
        self.session_id = session_id
        self.start_time: float = 0.0  # 交互开始时间
        self.timings: Dict[str, float] = {}  # 各阶段耗时记录
        self.timestamps: Dict[str, float] = {}  # 各阶段的时间戳
        
        # 关键时间节点
        self._ws_connected_time: Optional[float] = None  # WebSocket 连接建立时间
        self._asr_start_time: Optional[float] = None  # ASR 开始时间
        self._asr_end_time: Optional[float] = None  # ASR 结束时间（用户说完话）
        self._llm_start_time: Optional[float] = None  # LLM 调用开始时间
        self._llm_end_time: Optional[float] = None  # LLM 调用结束时间
        self._tts_start_time: Optional[float] = None  # TTS 开始时间（第一帧发送）
        self._tts_end_time: Optional[float] = None  # TTS 结束时间
        
    def mark_ws_connected(self):
        """标记 WebSocket 连接建立"""
        self._ws_connected_time = time.time()
        self.timestamps['ws_connected'] = self._ws_connected_time
        logger.bind(tag=TAG).debug(f"[LatencyWatch] Session {self.session_id[:8]}... - WebSocket 连接建立")
    
    def mark_asr_start(self):
        """标记 ASR 开始"""
        self._asr_start_time = time.time()
        self.timestamps['asr_start'] = self._asr_start_time
        logger.bind(tag=TAG).debug(f"[LatencyWatch] Session {self.session_id[:8]}... - ASR 开始")
    
    def mark_asr_end(self, text: str = ""):
        """
        标记 ASR 结束
        
        Args:
            text: 识别出的文本
        """
        self._asr_end_time = time.time()
        self.timestamps['asr_end'] = self._asr_end_time
        
        if self._asr_start_time:
            asr_duration = self._asr_end_time - self._asr_start_time
            self.timings['asr_duration'] = asr_duration
            logger.bind(tag=TAG).info(
                f"[LatencyWatch] Session {self.session_id[:8]}... - ASR 完成 | "
                f"耗时: {asr_duration:.3f}s | 文本: '{text[:50]}{'...' if len(text) > 50 else ''}'"
            )
    
    def mark_llm_start(self):
        """标记 LLM 调用开始"""
        self._llm_start_time = time.time()
        self.timestamps['llm_start'] = self._llm_start_time
        logger.bind(tag=TAG).debug(f"[LatencyWatch] Session {self.session_id[:8]}... - LLM 调用开始")
    
    def mark_llm_end(self, response_length: int = 0):
        """
        标记 LLM 调用结束
        
        Args:
            response_length: 响应文本长度
        """
        self._llm_end_time = time.time()
        self.timestamps['llm_end'] = self._llm_end_time
        
        if self._llm_start_time:
            llm_duration = self._llm_end_time - self._llm_start_time
            self.timings['llm_duration'] = llm_duration
            logger.bind(tag=TAG).info(
                f"[LatencyWatch] Session {self.session_id[:8]}... - LLM 完成 | "
                f"耗时: {llm_duration:.3f}s | 响应长度: {response_length} 字符"
            )
    
    def mark_tts_start(self):
        """标记 TTS 开始（第一帧音频发送给终端）"""
        self._tts_start_time = time.time()
        self.timestamps['tts_start'] = self._tts_start_time
        
        # 计算用户等待时间：从 ASR 结束到 TTS 第一帧发送
        if self._asr_end_time:
            user_wait_time = self._tts_start_time - self._asr_end_time
            self.timings['user_wait_time'] = user_wait_time
            logger.bind(tag=TAG).info(
                f"[LatencyWatch] Session {self.session_id[:8]}... - 用户等待时间: {user_wait_time:.3f}s"
            )
        
        logger.bind(tag=TAG).debug(f"[LatencyWatch] Session {self.session_id[:8]}... - TTS 开始（第一帧发送）")
    
    def mark_tts_end(self):
        """标记 TTS 结束"""
        self._tts_end_time = time.time()
        self.timestamps['tts_end'] = self._tts_end_time
        
        if self._tts_start_time:
            tts_duration = self._tts_end_time - self._tts_start_time
            self.timings['tts_duration'] = tts_duration
            logger.bind(tag=TAG).info(
                f"[LatencyWatch] Session {self.session_id[:8]}... - TTS 完成 | "
                f"耗时: {tts_duration:.3f}s"
            )
    
    def mark_interaction_complete(self):
        """标记一轮交互完成，打印完整耗时统计"""
        end_time = time.time()
        
        # 计算总耗时
        if self._ws_connected_time:
            total_duration = end_time - self._ws_connected_time
            self.timings['total_duration'] = total_duration
        
        # 计算各阶段之间的间隔
        if self._asr_start_time and self._ws_connected_time:
            self.timings['ws_to_asr'] = self._asr_start_time - self._ws_connected_time
        
        if self._llm_start_time and self._asr_end_time:
            self.timings['asr_to_llm'] = self._llm_start_time - self._asr_end_time
        
        if self._tts_start_time and self._llm_end_time:
            self.timings['llm_to_tts'] = self._tts_start_time - self._llm_end_time
        
        # 计算用户等待时间（如果还未计算）
        if 'user_wait_time' not in self.timings and self._asr_end_time and self._tts_start_time:
            self.timings['user_wait_time'] = self._tts_start_time - self._asr_end_time
        
        # 打印完整的耗时报告
        self._print_latency_report()
    
    def _print_latency_report(self):
        """打印延迟统计报告"""
        separator = "=" * 70
        logger.bind(tag=TAG).info(separator)
        logger.bind(tag=TAG).info(f"[LatencyWatch] 语音交互耗时统计 - Session {self.session_id[:8]}...")
        logger.bind(tag=TAG).info(separator)
        
        # 总体统计
        if 'total_duration' in self.timings:
            logger.bind(tag=TAG).info(
                f"  📊 总耗时: {self.timings['total_duration']:.3f}s"
            )
        
        logger.bind(tag=TAG).info("-" * 70)
        
        # 各阶段详细统计
        stages = [
            ('ws_to_asr', '⏱️  WebSocket → ASR', '等待用户说话'),
            ('asr_duration', '🎤 ASR 识别', '语音转文字'),
            ('user_wait_time', '⏳ 用户等待', '说完话到听到回复'),
            ('asr_to_llm', '⏱️  ASR → LLM', '意图处理'),
            ('llm_duration', '🧠 LLM 推理', '生成回复'),
            ('llm_to_tts', '⏱️  LLM → TTS', '准备合成'),
            ('tts_duration', '🔊 TTS 合成', '文字转语音'),
        ]
        
        for key, label, description in stages:
            if key in self.timings:
                duration = self.timings[key]
                percentage = ""
                if 'total_duration' in self.timings and self.timings['total_duration'] > 0:
                    pct = (duration / self.timings['total_duration']) * 100
                    percentage = f" ({pct:.1f}%)"
                
                logger.bind(tag=TAG).info(
                    f"  {label}: {duration:.3f}s{percentage} - {description}"
                )
        
        logger.bind(tag=TAG).info("-" * 70)
        
        # 性能分析建议
        self._print_performance_suggestions()
        
        logger.bind(tag=TAG).info(separator)
    
    def _print_performance_suggestions(self):
        """根据耗时情况提供性能优化建议"""
        suggestions = []
        
        # ASR 耗时过长
        if 'asr_duration' in self.timings and self.timings['asr_duration'] > 2.0:
            suggestions.append(
                f"⚠️  ASR 耗时较长 ({self.timings['asr_duration']:.3f}s)，建议检查网络或考虑使用更快的 ASR 服务"
            )
        
        # LLM 耗时过长
        if 'llm_duration' in self.timings and self.timings['llm_duration'] > 3.0:
            suggestions.append(
                f"⚠️  LLM 推理较慢 ({self.timings['llm_duration']:.3f}s)，建议使用更快的模型或优化 prompt"
            )
        
        # 用户等待时间过长
        if 'user_wait_time' in self.timings and self.timings['user_wait_time'] > 4.0:
            suggestions.append(
                f"⚠️  用户等待时间较长 ({self.timings['user_wait_time']:.3f}s)，建议优化 LLM 响应速度或使用流式输出"
            )
        
        # TTS 耗时过长
        if 'tts_duration' in self.timings and self.timings['tts_duration'] > 2.0:
            suggestions.append(
                f"⚠️  TTS 合成较慢 ({self.timings['tts_duration']:.3f}s)，建议使用流式 TTS 或更快的服务"
            )
        
        # 总耗时过长
        if 'total_duration' in self.timings and self.timings['total_duration'] > 8.0:
            suggestions.append(
                f"⚠️  总耗时过长 ({self.timings['total_duration']:.3f}s)，用户体验可能受影响"
            )
        
        # 打印建议
        if suggestions:
            logger.bind(tag=TAG).warning("  💡 性能优化建议:")
            for suggestion in suggestions:
                logger.bind(tag=TAG).warning(f"    {suggestion}")
        else:
            logger.bind(tag=TAG).info("  ✅ 性能表现良好")
    
    def get_summary(self) -> Dict[str, float]:
        """
        获取耗时统计摘要
        
        Returns:
            包含所有耗时数据的字典
        """
        return {
            'session_id': self.session_id,
            'timings': self.timings.copy(),
            'timestamps': self.timestamps.copy()
        }
    
    def reset(self):
        """重置监控器状态"""
        self.__init__(self.session_id)
