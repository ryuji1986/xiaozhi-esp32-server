import argparse
import asyncio
import gc
import random
import statistics
import time
import tracemalloc
from typing import List, Dict, Any

import psutil


description = "GC压测：观测RSS、tracemalloc与GC暂停时间，可切换定时代际GC开关"


class LocalGCManager:
    """轻量GC管理器，复用服务端同类策略用于独立压测。"""

    def __init__(self, interval_seconds=10, full_gc_interval=6):
        self.interval_seconds = interval_seconds
        self.full_gc_interval = max(1, int(full_gc_interval))
        self._task = None
        self._stop_event = asyncio.Event()
        self._gc_round = 0

    async def start(self):
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._gc_loop())

    async def stop(self):
        if self._task is None:
            return
        self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _gc_loop(self):
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self.interval_seconds
                )
                break
            except asyncio.TimeoutError:
                self._run_gc_once()

    def _run_gc_once(self):
        self._gc_round += 1
        generation = 0
        if self._gc_round % self.full_gc_interval == 0:
            generation = 2
        elif self._gc_round % 2 == 0:
            generation = 1
        gc.collect(generation)


class GCMetrics:
    def __init__(self):
        self.pause_ms: List[float] = []
        self.collected: List[int] = []
        self.uncollectable: List[int] = []
        self._start_ts: Dict[int, float] = {}

    def callback(self, phase: str, info: Dict[str, Any]):
        generation = info.get("generation", -1)
        if phase == "start":
            self._start_ts[generation] = time.perf_counter()
        elif phase == "stop":
            start = self._start_ts.pop(generation, None)
            if start is not None:
                self.pause_ms.append((time.perf_counter() - start) * 1000)
            self.collected.append(info.get("collected", 0))
            self.uncollectable.append(info.get("uncollectable", 0))


async def churn_objects(
    duration_seconds: int,
    batch_size: int,
    payload_size: int,
    survivor_ratio: float,
    sleep_ms: int,
):
    survivors = []
    end_time = time.time() + duration_seconds
    while time.time() < end_time:
        batch = []
        for _ in range(batch_size):
            token = random.randint(1, 1_000_000)
            obj = {
                "token": token,
                "payload": "x" * payload_size,
                "arr": [token] * 8,
                "nested": {"a": token, "b": token * 2},
            }
            batch.append(obj)

        keep = int(len(batch) * survivor_ratio)
        if keep > 0:
            survivors.extend(batch[:keep])

        if len(survivors) > batch_size * 20:
            del survivors[: batch_size * 10]

        await asyncio.sleep(max(0, sleep_ms) / 1000)


def summarize(values: List[float]) -> str:
    if not values:
        return "n/a"
    p50 = statistics.median(values)
    p95 = sorted(values)[max(0, int(len(values) * 0.95) - 1)]
    p99 = sorted(values)[max(0, int(len(values) * 0.99) - 1)]
    return f"p50={p50:.2f}ms p95={p95:.2f}ms p99={p99:.2f}ms max={max(values):.2f}ms"


async def run_benchmark(args):
    process = psutil.Process()
    metrics = GCMetrics()

    gc.callbacks.append(metrics.callback)
    tracemalloc.start(25)

    gc_manager = None
    if args.use_gc_manager:
        gc_manager = LocalGCManager(
            interval_seconds=args.gc_interval,
            full_gc_interval=args.full_gc_interval,
        )
        await gc_manager.start()

    start_rss = process.memory_info().rss
    start = time.perf_counter()

    try:
        await churn_objects(
            duration_seconds=args.duration,
            batch_size=args.batch_size,
            payload_size=args.payload_size,
            survivor_ratio=args.survivor_ratio,
            sleep_ms=args.sleep_ms,
        )
    finally:
        if gc_manager is not None:
            await gc_manager.stop()

        elapsed = time.perf_counter() - start
        end_rss = process.memory_info().rss
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        if metrics.callback in gc.callbacks:
            gc.callbacks.remove(metrics.callback)

        total_collected = sum(metrics.collected)
        total_uncollectable = sum(metrics.uncollectable)

        print("\n========== GC压测结果 ==========")
        print(f"模式: {'定时代际GC开启' if args.use_gc_manager else '仅默认GC'}")
        print(f"运行时长: {elapsed:.2f}s")
        print(f"RSS: start={start_rss/1024/1024:.2f}MB end={end_rss/1024/1024:.2f}MB delta={(end_rss-start_rss)/1024/1024:.2f}MB")
        print(f"tracemalloc: current={current/1024/1024:.2f}MB peak={peak/1024/1024:.2f}MB")
        print(f"GC次数: {len(metrics.pause_ms)}")
        print(f"GC暂停: {summarize(metrics.pause_ms)}")
        print(f"回收对象总数: {total_collected}")
        print(f"不可回收对象总数: {total_uncollectable}")
        print("================================\n")


def parse_args():
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--duration", type=int, default=60, help="压测时长（秒）")
    parser.add_argument("--batch-size", type=int, default=5000, help="每轮对象创建数量")
    parser.add_argument("--payload-size", type=int, default=1024, help="每个对象payload长度（字节近似）")
    parser.add_argument("--survivor-ratio", type=float, default=0.05, help="每轮保留对象比例，用于模拟晋升")
    parser.add_argument("--sleep-ms", type=int, default=20, help="每轮休眠毫秒数")

    parser.add_argument("--use-gc-manager", action="store_true", help="开启定时代际GC模式")
    parser.add_argument("--gc-interval", type=int, default=10, help="定时GC轮询间隔（秒）")
    parser.add_argument("--full-gc-interval", type=int, default=6, help="多少轮执行一次gen2完整GC")
    return parser.parse_args()


def main():
    args = parse_args()
    asyncio.run(run_benchmark(args))


if __name__ == "__main__":
    main()
