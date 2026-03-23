"""Generate a Reddit-style HTML thread view from a simulation DB."""

import argparse
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from db import get_results_for_run


def extract_data(app_db_path: str, run_id: int) -> dict[str, Any]:
    return get_results_for_run(app_db_path, run_id)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>r/SaaS — Simulation Results</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { background: #1a1a1b; color: #d7dadc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; }
        .container { max-width: 740px; margin: 0 auto; padding: 16px; }
        .stats-banner { background: #272729; border: 1px solid #343536; border-radius: 4px; padding: 10px 16px; margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: #818384; }
        .post-card { background: #272729; border: 1px solid #343536; border-radius: 4px; padding: 0; margin-bottom: 16px; }
        .post-header { display: flex; align-items: center; gap: 8px; }
        .post-inner { display: flex; }
        .vote-column { display: flex; flex-direction: column; align-items: center; padding: 8px 12px; gap: 4px; }
        .vote-arrow { cursor: pointer; font-size: 16px; color: #818384; }
        .vote-arrow.up:hover { color: #ff4500; }
        .vote-arrow.down:hover { color: #7193ff; }
        .vote-score { font-weight: 700; font-size: 12px; }
        .post-content { padding: 8px 8px 8px 0; flex: 1; }
        .post-meta { font-size: 12px; color: #818384; margin-bottom: 8px; }
        .post-meta .subreddit { color: #d7dadc; font-weight: 700; }
        .post-title { font-size: 18px; font-weight: 600; margin-bottom: 12px; line-height: 1.3; }
        .post-body { line-height: 1.5; }
        .post-body p { margin-bottom: 10px; }
        .post-actions { display: flex; gap: 8px; padding: 4px 0 8px 0; font-size: 12px; color: #818384; font-weight: 700; }
        .action-btn { padding: 4px 8px; border-radius: 2px; }
        .action-btn:hover { background: #343536; }
        .comments-section { margin-top: 8px; }
        .comment { display: flex; margin-bottom: 2px; padding: 8px 0 4px 8px; }
        .comment-collapse { display: flex; flex-direction: column; align-items: center; margin-right: 8px; min-width: 20px; }
        .comment-collapse-btn { font-size: 12px; color: #818384; cursor: pointer; }
        .collapse-line { width: 2px; flex: 1; background: #343536; margin-top: 4px; cursor: pointer; }
        .collapse-line:hover { background: #d7dadc; }
        .comment-content { flex: 1; }
        .comment-meta { font-size: 12px; margin-bottom: 6px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
        .comment-author { font-weight: 600; color: #d7dadc; position: relative; cursor: pointer; }
        .comment-flair { font-size: 10px; padding: 1px 6px; border-radius: 10px; color: #fff; font-weight: 600; }
        .comment-time { color: #818384; }
        .comment-body { line-height: 1.5; margin-bottom: 6px; }
        .comment-body p { margin-bottom: 8px; }
        .comment-actions { display: flex; gap: 4px; font-size: 12px; color: #818384; font-weight: 700; }
        .comment-action-btn { padding: 2px 4px; cursor: pointer; }
        .bio-tooltip { display: none; position: absolute; bottom: 100%; left: 0; background: #343536; color: #d7dadc; padding: 8px; border-radius: 4px; font-size: 12px; font-weight: 400; width: 280px; z-index: 10; box-shadow: 0 2px 8px rgba(0,0,0,0.5); }
        .comment-author:hover .bio-tooltip { display: block; }
        @media (max-width: 600px) { .container { padding: 8px; } .post-title { font-size: 16px; } }
    </style>
</head>
<body>
    <div class="container" id="app"></div>
    <script id="sim-data" type="application/json">__DATA__</script>
    <script>
        const data = JSON.parse(document.getElementById('sim-data').textContent);

        const flairColors = {
            'Early Founder': '#4CAF50', 'Scaled Founder': '#2196F3',
            'Skeptical PM': '#f44336', 'Indie Hacker': '#FF9800',
            'HR/People Ops': '#9C27B0', 'Community Regular': '#795548',
            'VC/Growth': '#00BCD4', 'Lurker': '#9E9E9E', 'Unknown': '#616161',
        };

        function timeAgo(dateStr) {
            const diff = Date.now() - new Date(dateStr).getTime();
            const hours = Math.floor(diff / 3600000);
            if (hours < 1) return 'just now';
            if (hours < 24) return hours + ' hours ago';
            return Math.floor(hours / 24) + ' days ago';
        }

        function formatText(text) {
            return text.split('\n\n').map(p =>
                '<p>' + p.replace(/\n/g, '<br>').replace(/\*([^*]+)\*/g, '<em>$1</em>') + '</p>'
            ).join('');
        }

        function findProfile(author) {
            const lower = (author || '').toLowerCase();
            for (const [key, val] of Object.entries(data.profiles)) {
                if (lower.includes(key) || lower === val.username) return val;
                if (val.username && lower.includes(val.username)) return val;
            }
            for (const [key, val] of Object.entries(data.profiles)) {
                const parts = val.username.split('_');
                if (parts.some(p => p.length > 2 && lower.includes(p))) return val;
            }
            return { username: author, archetype: 'Unknown', bio: '' };
        }

        function renderStatsBanner() {
            return '<div class="stats-banner">' +
                '  <div>Simulated with ' + data.stats.total_agents + ' AI agents via OASIS + GPT-5.4-nano</div>' +
                '  <div>Score: +' + data.stats.score + ' | Comments: ' + data.stats.total_comments + ' | Engagement: ' + data.stats.commenting_agents + '/' + data.stats.total_agents + ' agents</div>' +
                '</div>';
        }

        function renderPost() {
            const lines = data.post.content.split('\n');
            const title = lines[0];
            const body = lines.slice(1).join('\n').trim();
            const score = data.post.likes - data.post.dislikes;
            return '<div class="post-card"><div class="post-inner">' +
                '<div class="vote-column">' +
                '  <span class="vote-arrow up">▲</span>' +
                '  <span class="vote-score">' + score + '</span>' +
                '  <span class="vote-arrow down">▼</span>' +
                '</div>' +
                '<div class="post-content">' +
                '  <div class="post-meta"><span class="subreddit">r/SaaS</span> · Posted by u/maya_flowpulse · ' + timeAgo(data.post.created_at) + '</div>' +
                '  <div class="post-title">' + title + '</div>' +
                '  <div class="post-body">' + formatText(body) + '</div>' +
                '  <div class="post-actions">' +
                '    <div class="action-btn">💬 ' + data.stats.total_comments + ' Comments</div>' +
                '    <div class="action-btn">↗ Share</div>' +
                '    <div class="action-btn">⭐ Save</div>' +
                '  </div>' +
                '</div></div></div>';
        }

        function renderCommentNode(comment) {
            const profile = findProfile(comment.author);
            const flairColor = flairColors[profile.archetype] || '#9E9E9E';
            const score = comment.likes - comment.dislikes;
            const scoreDisplay = score > 0 ? '+' + score : score;

            return '<div class="comment">' +
                '  <div class="comment-collapse">' +
                '      <div class="comment-collapse-btn">[–]</div>' +
                '      <div class="collapse-line"></div>' +
                '  </div>' +
                '  <div class="comment-content">' +
                '      <div class="comment-meta">' +
                '          <span class="comment-author">' +
                '              ' + comment.author +
                '              <span class="bio-tooltip">' + profile.bio + '</span>' +
                '          </span>' +
                '          <span class="comment-flair" style="background-color: ' + flairColor + '">' + profile.archetype + '</span>' +
                '          <span class="comment-time">' + scoreDisplay + ' points · ' + timeAgo(comment.created_at) + '</span>' +
                '      </div>' +
                '      <div class="comment-body">' + formatText(comment.content) + '</div>' +
                '      <div class="comment-actions">' +
                '          <span class="vote-arrow up">▲</span>' +
                '          <span class="comment-action-btn">Reply</span>' +
                '          <span class="vote-arrow down">▼</span>' +
                '          <span class="comment-action-btn">Share</span>' +
                '          <span class="comment-action-btn">Report</span>' +
                '      </div>' +
                '  </div>' +
                '</div>';
        }

        function renderComments() {
            const sortedComments = [...data.comments].sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
            const flatComments = sortedComments
                .map(comment => renderCommentNode(comment))
                .join('');
            return '<div class="comments-section">' + flatComments + '</div>';
        }

        function init() {
            const app = document.getElementById('app');
            app.innerHTML = renderStatsBanner() + renderPost() + renderComments();
        }

        init();
    </script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(
        description="Generate Reddit-style HTML thread from simulation DB"
    )
    parser.add_argument("db", help="Path to app SQLite DB")
    parser.add_argument(
        "--run-id", type=int, required=True, help="Run ID to generate HTML for"
    )
    parser.add_argument(
        "--output", help="Output HTML path (default: results/<run-id>-thread.html)"
    )
    args = parser.parse_args()

    if not args.output:
        results_dir = os.path.dirname(args.db) or "results"
        args.output = os.path.join(results_dir, f"{args.run_id}-thread.html")

    data = extract_data(args.db, args.run_id)
    data_json = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    html = TEMPLATE.replace("__DATA__", data_json)

    with open(args.output, "w") as f:
        f.write(html)

    print(f"Generated {args.output}")
    print(f"  Score: +{data['stats']['score']}")
    print(f"  Comments: {data['stats']['total_comments']}")
    print(
        f"  Agents who commented: {data['stats']['commenting_agents']}/{data['stats']['total_agents']}"
    )


if __name__ == "__main__":
    main()
