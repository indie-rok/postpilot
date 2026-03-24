# Post Pilot

**Test your Reddit launch post before you post it.**

Post Pilot simulates a Reddit community reacting to your launch post. A handful of AI personas (the skeptic, the early adopter, the lurker, the competitor...) read your post and respond the way real Redditors would. You get feedback, a scorecard, and a rewritten version of your post before anyone real sees it.

[![npm version](https://img.shields.io/npm/v/post-pilot)](https://www.npmjs.com/package/post-pilot)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/indie-rok/postpilot/blob/main/LICENSE)
![Python 3.11](https://img.shields.io/badge/python-3.11-blue)

<!-- Replace with your YouTube demo video -->
<!-- [![Post Pilot Demo](docs/assets/video-thumbnail.png)](https://youtube.com/watch?v=YOUR_VIDEO_ID) -->

![Post Pilot demo](docs/assets/demo.gif)

---

## How it works

1. You write a launch post (or Post Pilot generates one from your repo)
2. AI personas simulate a full Reddit thread with upvotes, downvotes, comments, skepticism, the works
3. You get a scorecard with sentiment breakdown, engagement numbers, and what landed vs. what flopped
4. Post Pilot rewrites your post using what it learned from the simulation

All generated text goes through a humanizer that strips out AI writing patterns, so the comments actually read like people wrote them.

---

## Quick start

### Prerequisites

- Node.js 18+
- Python 3.11 (exactly 3.11, the simulation engine needs it)
- An LLM API key (OpenRouter, OpenAI, or any OpenAI-compatible provider)

### Setup

```bash
npx post-pilot init
```

This walks you through connecting your LLM provider (API key, model, base URL), optionally connecting Reddit for posting later, and scanning your repo to build a product profile.

### Run

```bash
npx post-pilot serve
```

Open `http://localhost:8000`, write or generate a post, pick your community personas, and hit simulate.

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

## What you get

A full Reddit-style comment thread with 8 persona archetypes reacting to your post: early adopters, skeptics, tech leads, budget-conscious buyers, lurkers, competitors, power users, and community moderators.

A scorecard covering engagement metrics (upvotes, comments, engagement rate), sentiment distribution, and per-comment classification.

An analysis section that breaks down what resonated, what got pushback, recurring questions, positioning gaps, and the strongest hook in your post.

A rewritten version of your post that addresses the feedback and leads with whatever worked best.

---

## How the simulation works

Post Pilot uses [OASIS](https://github.com/camel-ai/oasis) (Open Agent Social Interaction Simulations) to run a multi-agent simulation. Each agent has a persona with demographics, interests, personality type, and a specific archetype that shapes how they react.

The simulation runs in rounds. Agents see the post, decide whether to engage, write comments, and react to each other's comments. Afterward, a humanizer pass rewrites all generated text to strip out AI writing patterns (em dashes, "delve", "pivotal", sycophantic tone, etc.).

---

## Configuration

Post Pilot stores config in `.post-pilot/` in your project directory:

```
.post-pilot/
  .env          # API keys (LLM + Reddit)
  post-pilot.db # Product profile, runs, results
  .venv/        # Python virtual environment (auto-created)
```

The `.post-pilot/` directory is automatically added to your `.gitignore`.

### LLM providers

Any OpenAI-compatible API works. During `init`, you provide your API key, base URL (defaults to `https://openrouter.ai/api/v1`), and model (defaults to `gpt-4o-mini`).

Tested with: OpenRouter, OpenAI, Anthropic (via OpenRouter), Groq, Together AI.

---

## License

[MIT](LICENSE)
