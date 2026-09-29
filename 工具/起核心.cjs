/**
 * 常驻启动核心（无 Electron）。日志写到 /tmp/coop/核心.log，不自动退出。
 * 用法：node 起核心.cjs [外壳命令JSON]
 *   例：node 起核心.cjs '["python3","/tmp/coop/外壳.py"]'
 *       → 会以  python3 /tmp/coop/外壳.py --pet-url=http://127.0.0.1:<端口>/pet  启动
 */
const { fork } = require('node:child_process');
const { join } = require('node:path');
const { mkdirSync, createWriteStream } = require('node:fs');

const HOME = process.env.HOME ?? require('node:os').homedir();
const HERE = join(__dirname, '..');
const APP = process.env.COOP_APP ?? join(HERE, 'app');
const DATA = process.env.COOP_RUN ?? join(HERE, 'run');
mkdirSync(DATA, { recursive: true });
const log = createWriteStream(process.env.COOP_LOG ?? join(HERE, 'logs/核心.log'), { flags: 'a' });

const env = {
  ...process.env,
  NODE_USE_ENV_PROXY: '1',
  NO_PROXY: '127.0.0.1,localhost,::1',
  ELECTRON_SKIP_BINARY_DOWNLOAD: '1',        // 万一有 require('electron')，别下载
  CORTICO_COMPANION_ROOT: join(APP, 'build', 'cortico'),
};
if (process.argv[2]) env.CORTICO_DESKTOP_PET_HOST = process.argv[2];

const child = fork(join(APP, 'core', 'boot.ts'), [], {
  cwd: APP,
  execArgv: ['--max-old-space-size=96', '--max-semi-space-size=4', '--import', 'tsx', '--require', join(HERE, '兜异常.cjs')],
  env,
  stdio: ['ignore', 'pipe', 'pipe', 'ipc'],
});
child.stdout.pipe(log, { end: false });
child.stderr.pipe(log, { end: false });

child.on('message', (msg) => {
  const line = `[ipc ${new Date().toISOString()}] ${JSON.stringify(msg)}`;
  console.log(line);
  log.write(line + '\n');
  if (msg && msg.type === 'companion:ready') {
    console.log(`READY port=${msg.port} data=${msg.dataDir}`);
  }
});
child.on('exit', (code) => {
  console.log('核心退出 code=' + code);
  log.end();
  process.exit(0);
});
// 不设超时：靠外部 kill
