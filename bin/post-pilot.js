#!/usr/bin/env node

const { execSync, spawn } = require('child_process');
const { existsSync, mkdirSync } = require('fs');
const { join } = require('path');

const PROJECT_DIR = join(process.cwd(), '.post-pilot');
const PYTHON_PKG_DIR = join(__dirname, '..', 'simulation');

const isWin = process.platform === 'win32';
const binDir = isWin ? 'Scripts' : 'bin';
const pyExe = isWin ? 'python.exe' : 'python';

const VENV_DIR = join(PROJECT_DIR, '.venv');

function getVenvPython() { return join(VENV_DIR, binDir, pyExe); }
function getVenvPip() { return join(VENV_DIR, binDir, 'pip'); }

const FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];
const CLEAR = '\x1B[2K\r';
function startSpinner(msg) {
  let i = 0;
  const id = setInterval(() => {
    process.stdout.write(`${CLEAR}  ${FRAMES[i++ % FRAMES.length]} ${msg}`);
  }, 80);
  return {
    stop(finalMsg) {
      clearInterval(id);
      process.stdout.write(`${CLEAR}  ✓ ${finalMsg}\n`);
    },
    fail(finalMsg) {
      clearInterval(id);
      process.stdout.write(`${CLEAR}  ✗ ${finalMsg}\n`);
    },
  };
}

function runAsync(cmd, args, opts = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, { stdio: 'pipe', ...opts });
    let stderr = '';
    if (child.stderr) child.stderr.on('data', (d) => { stderr += d; });
    child.on('exit', (code) => {
      if (code === 0) resolve();
      else reject(new Error(`Exit ${code}: ${stderr.slice(-200)}`));
    });
    child.on('error', reject);
  });
}

function findPython() {
  const candidates = isWin ? ['python', 'python3'] : ['python3', 'python'];
  for (const cmd of candidates) {
    try {
      const version = execSync(`${cmd} --version 2>&1`, { encoding: 'utf8' }).trim();
      const match = version.match(/Python (\d+)\.(\d+)/);
      if (match && (parseInt(match[1]) > 3 || (parseInt(match[1]) === 3 && parseInt(match[2]) >= 11))) {
        return cmd;
      }
    } catch {}
  }
  return null;
}

async function ensureVenv(pythonCmd) {
  if (existsSync(getVenvPython())) return;

  mkdirSync(PROJECT_DIR, { recursive: true });

  const sp1 = startSpinner('Creating virtual environment...');
  try {
    await runAsync(pythonCmd, ['-m', 'venv', VENV_DIR]);
    sp1.stop('Virtual environment created');
  } catch (e) {
    sp1.fail('Failed to create virtual environment');
    console.error(e.message);
    process.exit(1);
  }

  const sp2 = startSpinner('Installing dependencies (this may take a minute)...');
  try {
    await runAsync(getVenvPip(), ['install', '-q', '-r', join(PYTHON_PKG_DIR, 'requirements.txt')]);
    sp2.stop('Dependencies installed');
  } catch (e) {
    sp2.fail('Failed to install dependencies');
    console.error(e.message);
    process.exit(1);
  }

  console.log('');
}

// Main
async function main() {
  const args = process.argv.slice(2);
  if (args.length === 0 || args[0] === '--help' || args[0] === '-h') {
    console.log(`
  Post Pilot — test your post before you post

  Commands:
    init        Full setup wizard
    configure   Set up LLM and Reddit API credentials
    learn       Scan repo and generate product profile
    serve       Launch web UI (default port 8000)

  Usage:
    npx post-pilot init
    npx post-pilot serve --port 3000
`);
    process.exit(0);
  }

  const python = findPython();
  if (!python) {
    console.error('Python 3.11+ is required. Install from https://python.org');
    process.exit(1);
  }

  await ensureVenv(python);

  const child = spawn(getVenvPython(), ['-m', 'cli', ...args], {
    cwd: PYTHON_PKG_DIR,
    stdio: 'inherit',
    env: { ...process.env, PYTHONPATH: PYTHON_PKG_DIR, POST_PILOT_PROJECT_DIR: process.cwd() },
  });

  child.on('exit', (code) => process.exit(code || 0));
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
