/**
 * Linux 兜底：不让某个 World 的未捕获异常把整个核心带走。
 *
 * 起因：`cortico-world-cua` 的引擎子进程在 platform != darwin 时回落到 Win32 实现，
 * Linux 上必然加载失败 → 子进程退出 → 它的 exit 回调里抛出的异常没人接 → 核心整个退出。
 * 这个 shim 只做一件事：把未捕获异常/未处理的 Promise 拒绝记下来，不让进程死。
 * 通过 node 的 `--require` 挂上，**不改核心任何一行代码**。
 */
const 记 = (...a) => console.error('[兜]', ...a);

process.on('uncaughtException', (err) => {
  记('未捕获异常（已放行，不让它带走核心）:', err && err.message ? err.message : err);
});
process.on('unhandledRejection', (reason) => {
  记('未处理的 Promise 拒绝（已放行）:', reason && reason.message ? reason.message : reason);
});
