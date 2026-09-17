"""Run the whole corpus end to end.

Stages 1 and 2 are GPU bound and must stay in one process; stage 3 is bound by
the API's rate limit, so it is sharded across several processes and merged.
Every stage resumes from what is already on disk, so an interrupted run can be
restarted with the same command.

Usage (from tag-system/):
  python -m tagger.run_corpus                        # dry run: prints the plan
  python -m tagger.run_corpus --go                   # actually run
  python -m tagger.run_corpus --go --shards 4        # parallel stage-3 workers
  python -m tagger.run_corpus --go --stages 3        # only stage 3 (after 1/2)
"""

import argparse
import atexit
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from .config import CONFIGS

ROOT = Path(__file__).resolve().parent.parent

_SKIP_DIRS = {"shard", "_smoke", "_cachetest"}


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            # tasklist prints in the console codepage (GBK here), so take bytes
            # and decode leniently rather than letting Python guess UTF-8.
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                                 capture_output=True, timeout=20).stdout
            return str(pid) in out.decode("utf-8", "ignore") or \
                str(pid) in out.decode("gbk", "ignore")
        except Exception:                                    # noqa: BLE001
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def acquire_lock(work: Path) -> Path:
    """Refuse to start if a run is already writing to this directory.

    Two copies writing the same cache silently duplicate every record and fight
    over the GPU. That is not hypothetical: a launcher's dry-run flag failed to
    bind and five full runs started at once, 2.1x duplicating the cache and
    filling RAM with five copies of the corpus.
    """
    work.mkdir(parents=True, exist_ok=True)
    lock = work / ".run_lock"
    if lock.exists():
        try:
            info = json.loads(lock.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            info = {}
        pid = int(info.get("pid", 0) or 0)
        if _pid_alive(pid):
            print(f"!! 已有任务在跑 (pid={pid}, 启动于 {info.get('started','?')})")
            print(f"   锁文件: {lock}")
            print("   要重来: 先 Get-Process python | Stop-Process，再删除锁文件")
            sys.exit(2)
        print(f"   （清理过期锁: pid={pid} 已不存在）")
    lock.write_text(json.dumps({"pid": os.getpid(),
                                "started": time.strftime("%Y-%m-%d %H:%M:%S")}),
                    encoding="utf-8")
    atexit.register(lambda: lock.unlink(missing_ok=True))
    return lock


def shard_stage3(cache: Path, work: Path, n: int) -> list[Path]:
    """Split the stage-2 cache into n shards, one directory each.

    Streamed: the cache carries each book's full text and reaches several GB on
    a full corpus, so it must not be slurped into memory.
    """
    dirs = []
    for i in range(n):
        d = work / f"shard{i:02d}"
        d.mkdir(parents=True, exist_ok=True)
        dirs.append(d)
    handles = [(d / ".stage2_cache.jsonl").open("w", encoding="utf-8") for d in dirs]
    try:
        with cache.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if line.strip():
                    handles[i % n].write(line)
    finally:
        for h in handles:
            h.close()
    return dirs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=r"D:/本地项目/小说清洗/清洗完成")
    ap.add_argument("--work", default="tagger/work/corpus")
    ap.add_argument("--shards", type=int, default=4,
                    help="parallel stage-3 processes (keep <= 5; the gateway "
                         "allows ~20 requests per 28s)")
    ap.add_argument("--config", default="default")
    ap.add_argument("--stages", default="1,2,3")
    ap.add_argument("--go", action="store_true", help="without this, only print the plan")
    args = ap.parse_args()

    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    final = work / "final.jsonl"
    s1 = work / ".stage1_cache.jsonl"
    s2 = work / ".stage2_cache.jsonl"
    stages = [int(x) for x in args.stages.split(",") if x.strip()]

    if not args.go:
        pass                       # dry run: skip the lock so checks never block
    else:
        acquire_lock(work)

    n_books = len(list(Path(args.corpus).glob("*.txt")))
    print("=" * 74)
    print("全库打标计划")
    print("=" * 74)
    print(f"  语料      : {args.corpus}  ({n_books:,} 本)")
    print(f"  输出      : {work}")
    print(f"  档位      : {args.config}   stage3 并行度 {args.shards}")
    print(f"  阶段      : {stages}")
    print()
    print("  预计耗时（基于实测）:")
    print(f"    Stage 1 chunk 召回 (GPU 串行)  约 5 小时")
    print(f"    Stage 2 重排       (GPU 串行)  约 13 小时")
    print(f"    Stage 3 判定       ({args.shards} 路并行)  约 {29 // max(args.shards,1)} 小时")
    # measured (cold prompt cache: 1 batch misses + 3 batches hit ~35%)
    print(f"  预计成本: deepseek-flash ¥0.054/本 × {n_books:,} ≈ "
          f"¥{0.054 * n_books:,.0f}   (缓存命中仅约 26%，冷前缀首次请求不命中)")
    print()
    def count(p):
        n = 0
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        n += 1
        return n

    print("  断点续跑进度:")
    for label, path in (("Stage 1 召回", s1), ("Stage 2 重排", s2)):
        n = count(path)
        print(f"    {label}: {n:>6,} 本" + ("  (已完成，会自动跳过)" if n else ""))
    # stage 3 writes per shard; the merged file only appears at the very end,
    # so a merged-only count shows 0 while the shards are half done
    shard_dirs = sorted(d for d in work.glob("shard*") if d.is_dir())
    n3 = sum(count(d / "final.jsonl") for d in shard_dirs) if shard_dirs else count(final)
    src = f"{len(shard_dirs)} 个分片合计" if shard_dirs else "合并文件"
    print(f"    Stage 3 判定: {n3:>6,} 本  ({src})")
    print("  中断后重跑同一条命令即可，已完成的不会重做。")
    if not args.go:
        print("\n  这是计划预览。确认后加 --go 执行。")
        return

    env = dict(os.environ)
    if not env.get("OPENCODE_API_KEY"):
        print("!! OPENCODE_API_KEY 未设置，Stage 3 会失败")
        return

    # One key per shard. Separate keys are separate ACCOUNTS, so they have
    # independent rate limits -- that is what makes sharding pay off at all.
    keys = [k.strip() for k in env.get("OPENCODE_API_KEYS", "").split(",") if k.strip()]
    if not keys:
        keys = [env["OPENCODE_API_KEY"]]
    if len(keys) < args.shards:
        print(f"!! 只有 {len(keys)} 个 key 但有 {args.shards} 个分片，"
              f"多出的分片会共用 key（并发额度共享，不会更快）")
    print(f"  使用 {len(keys)} 个 key，分片 {args.shards} 路 × 每路并发 "
          f"{CONFIGS[args.config].stage3_workers}")

    def run(cmd, log, extra_env=None):
        print(f"  -> {' '.join(cmd)}")
        e = dict(env)
        if extra_env:
            e.update(extra_env)
        with open(log, "a", encoding="utf-8") as f:
            return subprocess.run(cmd, cwd=ROOT, env=e, stdout=f,
                                  stderr=subprocess.STDOUT).returncode

    t0 = time.time()
    if 1 in stages:
        print("\n[1/3] Stage 1 chunk 召回 …")
        rc = run([sys.executable, "-u", "-m", "tagger.pipeline", "--book-dir", args.corpus,
                  "--output", str(final), "--config", args.config, "--stages", "1"],
                 work / "s1.log")
        print(f"      exit={rc}  ({time.time() - t0:.0f}s)")
        if rc != 0:
            return
    if 2 in stages:
        print("\n[2/3] Stage 2 重排 …")
        t1 = time.time()
        rc = run([sys.executable, "-u", "-m", "tagger.pipeline", "--output", str(final),
                  "--config", args.config, "--stages", "2"], work / "s2.log")
        print(f"      exit={rc}  ({time.time() - t1:.0f}s)")
        if rc != 0:
            return
    if 3 in stages:
        print(f"\n[3/3] Stage 3 判定（{args.shards} 路并行）…")
        if not s2.exists():
            print(f"!! 缺少 {s2}，先跑 stage 1,2")
            return
        t2 = time.time()
        dirs = shard_stage3(s2, work, args.shards)
        procs = []
        for i, d in enumerate(dirs):
            f = open(d / "s3.log", "a", encoding="utf-8")
            key = keys[i % len(keys)]
            procs.append((subprocess.Popen(
                [sys.executable, "-u", "-m", "tagger.pipeline", "--output", str(d / "final.jsonl"),
                 "--config", args.config, "--stages", "3"], cwd=ROOT,
                env={**env, "OPENCODE_API_KEY": key},
                stdout=f, stderr=subprocess.STDOUT), f))
            time.sleep(1)                     # stagger the starts
        for p, f in procs:
            p.wait()
            f.close()
        # Merge defensively: changing --shards reshuffles which books a shard
        # holds, so across runs the same book can land in two shards; and a
        # process killed mid-flush can leave a truncated last line. Keep the
        # last complete record per book, drop anything unparsable.
        seen, dups, bad = {}, 0, 0
        for d in dirs:
            p = d / "final.jsonl"
            if not p.exists():
                continue
            for line in p.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    bad += 1
                    continue
                if rec.get("book") in seen:
                    dups += 1
                seen[rec["book"]] = line
        with open(final, "w", encoding="utf-8") as out:
            for line in seen.values():
                out.write(line + "\n")
        print(f"      合并 {len(seen):,} 本 -> {final}  ({time.time() - t2:.0f}s)")
        if dups or bad:
            print(f"      （去重 {dups} 条重复记录，丢弃 {bad} 条损坏行）")

    print(f"\n全部完成，用时 {(time.time() - t0) / 3600:.1f} 小时")
    print(f"输出: {final}")


if __name__ == "__main__":
    main()
