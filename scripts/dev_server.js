const { spawn } = require('child_process');
const path = require('path');

const root = path.resolve(__dirname, '..');
const args = process.argv.slice(2);
function argument(name, fallback) {
  const inline = args.find(value => value.startsWith(`--${name}=`));
  if (inline) return inline.slice(name.length + 3);
  const index = args.indexOf(`--${name}`);
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback;
}
const host = argument('host', '0.0.0.0');
const port = Number(argument('port', '7100'));
const python = path.join(root, '.venv', 'Scripts', 'python.exe');
const env = {
  ...process.env,
  GTN_BIND_HOST: host,
  GTN_PORT: String(port),
  GTN_DB_PATH: process.env.GTN_DB_PATH || 'D:/var/lib/gtn/gtn.sqlite3',
  SECRET_KEY: process.env.SECRET_KEY || 'dev-fixed-secret-2026',
  GTN_SESSION_COOKIE_SECURE: process.env.GTN_SESSION_COOKIE_SECURE || '0',
};
const child = spawn(python, ['app.py'], { cwd: root, env, stdio: 'inherit', windowsHide: true });
let stopping = false;
function stop() {
  if (stopping) return;
  stopping = true;
  if (child.pid) spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore', windowsHide: true });
}
process.on('SIGINT', stop);
process.on('SIGTERM', stop);
child.on('exit', code => {
  if (!stopping) process.exitCode = code || 0;
});
