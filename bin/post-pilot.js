#!/usr/bin/env node

const { execSync, spawn } = require('child_process');
const { existsSync, mkdirSync } = require('fs');
const { join } = require('path');

const PROJECT_DIR = join(process.cwd(), '.post-pilot');
const VENV_DIR = join(PROJECT_DIR, '.venv');
const PYTHON_PKG_DIR = join(__dirname, '..', 'simulation');

const isWin = process.platform === 'win32';
const VENV_PYTHON = isWin
  ? join(VENV_DIR, 'Scripts', 'python.exe')
  : join(VENV_DIR, 'bin', 'python');
const VENV_PIP = isWin
  ? join(VENV_DIR, 'Scripts', 'pip')
  : join(VENV_DIR, 'bin', 'pip');

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

function ensureVenv(pythonCmd) {
  if (!existsSync(VENV_PYTHON)) {
    console.log('  Setting up Python environment...');
    mkdirSync(PROJECT_DIR, { recursive: true });
    execSync(`${pythonCmd} -m venv "${VENV_DIR}"`, { stdio: 'inherit' });
    execSync(`"${VENV_PIP}" install -q -r "${join(PYTHON_PKG_DIR, 'requirements.txt')}"`, { stdio: 'inherit' });
    console.log('  ✓ Python environment ready\n');
  }
}

// Main
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

ensureVenv(python);

const child = spawn(VENV_PYTHON, ['-m', 'cli', ...args], {
  cwd: PYTHON_PKG_DIR,
  stdio: 'inherit',
  env: { ...process.env, PYTHONPATH: PYTHON_PKG_DIR },
});

child.on('exit', (code) => process.exit(code || 0));
