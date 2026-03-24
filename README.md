# Post Pilot

**From code to reddit**
**Test your Reddit launch post before you post it.**

Post Pilot simulates a Reddit community reacting to your launch post. It reads your project (features, target personas, problem/solution) and it generates a simulation where AI Personas   (generated with subreddit data) read your post and respond the way real Redditors would. You get feedback, a scorecard, and a rewritten version of your post before anyone real sees it.

[![npm version](https://img.shields.io/npm/v/post-pilot)](https://www.npmjs.com/package/post-pilot)
![Status: Beta](https://img.shields.io/badge/status-beta-orange)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/indie-rok/postpilot/blob/main/LICENSE)
![Python 3.11](https://img.shields.io/badge/python-3.11-blue)

<!-- Replace with your YouTube demo video -->
<!-- [![Post Pilot Demo](docs/assets/video-thumbnail.png)](https://youtube.com/watch?v=YOUR_VIDEO_ID) -->

![Post Pilot demo](docs/assets/demo.gif)

---

## How it works

1. You write a launch post (or Post Pilot generates one from your codebase features)
2. AI personas simulate a full Reddit thread with upvotes, downvotes, comments, skepticism, the works
3. You get a scorecard with sentiment breakdown, engagement numbers, and what landed vs. what needs to be polished
4. Post Pilot rewrites your post using what it learned from the simulation

---

## Quick start

### Prerequisites

- Node.js 18+
- Python 3.11 (exactly 3.11, the simulation engine needs it)
- An LLM API key (any OpenAI-compatible provider. OpenRouter, OpenAI, etc)

### Setup

From your *project directory* (needed to generate an accurate company description), run: 

```bash
npx post-pilot init
```

This walks you through connecting your LLM provider (API key, model, base URL), optionally connecting Reddit for generate real user personas with sub reddit data, and scanning your repo to build a product profile.

### Run

```bash
npx post-pilot serve
```

Open `http://localhost:8000/setup`, to confirm the generate write or generate a post, pick your community personas, and hit simulate.

---

## Commands

| Command | What it does |
|---------|-------------|
| `npx post-pilot init` | Full setup wizard (credentials + product profile) |
| `npx post-pilot configure` | Update LLM or Reddit credentials |
| `npx post-pilot learn` | Re-scan your repo and regenerate the product profile |
| `npx post-pilot serve` | Launch the web UI (default port 8000) |
| `npx post-pilot serve --port 3000` | Launch on a custom port |

---

## Configuration

Post Pilot stores config in `.post-pilot/` in your project directory:

```
.post-pilot/
  .env          # API keys (LLM + Reddit)
  post-pilot.db # Product profile, runs, results
  .venv/        # Python virtual environment (all python simulation libs)
```

The `.post-pilot/` directory is automatically added to your `.gitignore`.

### LLM providers

Any OpenAI-compatible API works. During `init`, you provide your API key, base URL (defaults to `https://openrouter.ai/api/v1`), and model (defaults to `gpt-4o-mini`).

---

## License

[MIT](LICENSE)
