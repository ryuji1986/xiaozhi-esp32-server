"""
全局GC管理模块
定期执行垃圾回收，避免频繁触发GC导致的GIL锁问题
"""

import gc
import asyncio
import threading
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()


class GlobalGCManager:
    """全局垃圾回收管理器"""

    def __init__(self, interval_seconds=300, full_gc_interval=6):
        """
        初始化GC管理器

        Args:
            interval_seconds: GC执行间隔（秒），默认300秒（5分钟）
            full_gc_interval: 执行一次完整（第2代）GC的轮次间隔，默认6轮
        """
        self.interval_seconds = interval_seconds
        self.full_gc_interval = max(1, int(full_gc_interval))
        self._task = None
        self._stop_event = asyncio.Event()
        self._lock = threading.Lock()
        self._gc_round = 0

    async def start(self):
        """启动定时GC任务"""
        if self._task is not None:
            logger.bind(tag=TAG).warning("GC管理器已经在运行")
            return

        logger.bind(tag=TAG).info(
            f"启动全局GC管理器，间隔{self.interval_seconds}秒，完整GC轮次={self.full_gc_interval}"
        )
        self._stop_event.clear()
        self._task = asyncio.create_task(self._gc_loop())

    async def stop(self):
        """停止定时GC任务"""
        if self._task is None:
            return

        logger.bind(tag=TAG).info("停止全局GC管理器")
        self._stop_event.set()

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        self._task = None

    async def _gc_loop(self):
        """GC循环任务"""
        try:
            while not self._stop_event.is_set():
                # 等待指定间隔
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=self.interval_seconds
                    )
                    # 如果stop_event被设置，退出循环
                    break
                except asyncio.TimeoutError:
                    # 超时表示到了执行GC的时间
                    pass

                # 执行GC
                await self._run_gc()

        except asyncio.CancelledError:
            logger.bind(tag=TAG).info("GC循环任务被取消")
            raise
        except Exception as e:
            logger.bind(tag=TAG).error(f"GC循环任务异常: {e}")
        finally:
            logger.bind(tag=TAG).info("GC循环任务已退出")

    async def _run_gc(self):
        """执行垃圾回收"""
        try:
            # 在线程池中执行GC，避免阻塞事件循环
            loop = asyncio.get_running_loop()

            def do_gc():
                with self._lock:
                    self._gc_round += 1
                    generation = 0
                    if self._gc_round % self.full_gc_interval == 0:
                        generation = 2
                    elif self._gc_round % 2 == 0:
                        generation = 1

                    before_count = gc.get_count()
                    collected = gc.collect(generation)
                    after_count = gc.get_count()
                    return generation, before_count, collected, after_count

            generation, before_count, collected, after_count = await loop.run_in_executor(
                None, do_gc
            )
            logger.bind(tag=TAG).debug(
                f"全局GC执行完成(gen={generation}) - 回收对象: {collected}, "
                f"count: {before_count} -> {after_count}"
            )
        except Exception as e:
            logger.bind(tag=TAG).error(f"执行GC时出错: {e}")


# 全局单例
_gc_manager_instance = None


def get_gc_manager(interval_seconds=300, full_gc_interval=6):
    """
    获取全局GC管理器实例（单例模式）

    Args:
        interval_seconds: GC执行间隔（秒），默认300秒（5分钟）
        full_gc_interval: 执行一次完整（第2代）GC的轮次间隔，默认6轮

    Returns:
        GlobalGCManager实例
    """
    global _gc_manager_instance
    if _gc_manager_instance is None:
        _gc_manager_instance = GlobalGCManager(interval_seconds, full_gc_interval)
    return _gc_manager_instance
