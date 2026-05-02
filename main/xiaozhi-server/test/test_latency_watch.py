"""
LatencyWatch 功能测试脚本
用于验证语音交互流程耗时统计功能是否正常工作
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.utils.latency_watch import LatencyWatch


def test_latency_watch():
    """测试 LatencyWatch 基本功能"""
    print("=" * 70)
    print("LatencyWatch 功能测试")
    print("=" * 70)
    
    # 创建监控器实例
    session_id = "test-session-12345"
    watch = LatencyWatch(session_id)
    
    print(f"\n✅ 创建 LatencyWatch 实例成功")
    print(f"   Session ID: {session_id}")
    
    # 模拟各个阶段的标记
    print("\n📍 模拟语音交互流程...")
    
    # 1. WebSocket 连接建立
    watch.mark_ws_connected()
    print("   ✓ WebSocket 连接建立")
    
    import time
    time.sleep(0.1)  # 模拟延迟
    
    # 2. ASR 开始
    watch.mark_asr_start()
    print("   ✓ ASR 开始")
    
    time.sleep(0.5)  # 模拟 ASR 处理时间
    
    # 3. ASR 结束
    watch.mark_asr_end("你好，这是一段测试文本")
    print("   ✓ ASR 结束")
    
    time.sleep(0.2)  # 模拟间隔
    
    # 4. LLM 开始
    watch.mark_llm_start()
    print("   ✓ LLM 调用开始")
    
    time.sleep(1.0)  # 模拟 LLM 推理时间
    
    # 5. LLM 结束
    watch.mark_llm_end(response_length=100)
    print("   ✓ LLM 调用结束")
    
    time.sleep(0.1)  # 模拟间隔
    
    # 6. TTS 开始
    watch.mark_tts_start()
    print("   ✓ TTS 合成开始")
    
    time.sleep(0.8)  # 模拟 TTS 合成时间
    
    # 7. TTS 结束
    watch.mark_tts_end()
    print("   ✓ TTS 合成结束")
    
    # 8. 交互完成
    print("\n📊 生成耗时统计报告...")
    watch.mark_interaction_complete()
    
    # 获取摘要信息
    summary = watch.get_summary()
    print(f"\n✅ 耗时统计摘要:")
    print(f"   Session ID: {summary['session_id']}")
    print(f"   总耗时: {summary['timings'].get('total_duration', 0):.3f}s")
    print(f"   ASR 耗时: {summary['timings'].get('asr_duration', 0):.3f}s")
    print(f"   用户等待时间: {summary['timings'].get('user_wait_time', 0):.3f}s")
    print(f"   LLM 耗时: {summary['timings'].get('llm_duration', 0):.3f}s")
    print(f"   TTS 耗时: {summary['timings'].get('tts_duration', 0):.3f}s")
    
    print("\n" + "=" * 70)
    print("测试完成！")
    print("=" * 70)


if __name__ == "__main__":
    try:
        test_latency_watch()
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
