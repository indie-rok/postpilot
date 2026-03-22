const fs = require('fs');

const dataRaw = fs.readFileSync('simulation/results/v1-data.json', 'utf8');

const htmlTop = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>r/SaaS - FlowPulse Launch</title>
    <style>
        :root {
            --bg-color: #1a1a1b;
            --card-bg: #272729;
            --text-main: #d7dadc;
            --text-muted: #818384;
            --accent-up: #ff4500;
            --accent-down: #7193ff;
            --border-color: #343536;
            --hover-bg: #2d2d2f;
            --link-color: #4fbcff;
        }

        body {
            margin: 0;
            padding: 0;
            background-color: var(--bg-color);
            color: var(--text-main);
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.5;
        }

        .container {
            max-width: 740px;
            margin: 0 auto;
            padding: 20px 10px;
        }

        /* Banner */
        .stats-banner {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 4px;
            padding: 12px 16px;
            margin-bottom: 24px;
            font-size: 13px;
            color: var(--text-muted);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        /* Post Card */
        .post-card {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 4px;
            display: flex;
            margin-bottom: 24px;
        }

        .vote-sidebar {
            width: 40px;
            background-color: rgba(0,0,0,0.1);
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 8px 4px;
            border-radius: 4px 0 0 4px;
            border-right: 1px solid var(--border-color);
        }

        .vote-arrow {
            width: 24px;
            height: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 16px;
            font-weight: bold;
            color: var(--text-muted);
            cursor: pointer;
            user-select: none;
        }
        
        .vote-arrow:hover {
            background-color: var(--hover-bg);
            border-radius: 2px;
        }

        .vote-arrow.up:hover { color: var(--accent-up); }
        .vote-arrow.down:hover { color: var(--accent-down); }

        .vote-score {
            font-size: 12px;
            font-weight: 700;
            margin: 4px 0;
            color: var(--text-main);
        }

        .post-content {
            padding: 8px 16px 16px 16px;
            flex-grow: 1;
        }

        .post-meta {
            font-size: 12px;
            color: var(--text-muted);
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .subreddit {
            font-weight: bold;
            color: var(--text-main);
        }

        .author {
            color: var(--text-muted);
        }

        .post-title {
            font-size: 20px;
            font-weight: 500;
            margin: 0 0 12px 0;
            color: #fff;
            line-height: 1.3;
        }

        .post-body {
            font-size: 14px;
            margin-bottom: 16px;
            word-wrap: break-word;
        }

        .post-body p, .comment-body p {
            margin: 0 0 10px 0;
        }

        .post-actions {
            display: flex;
            gap: 12px;
            font-size: 12px;
            font-weight: bold;
            color: var(--text-muted);
        }

        .action-btn {
            display: flex;
            align-items: center;
            gap: 6px;
            padding: 6px 8px;
            border-radius: 4px;
            cursor: pointer;
        }

        .action-btn:hover {
            background-color: var(--hover-bg);
        }

        /* Comments */
        .comments-section {
            background-color: transparent;
        }
        
        .comment-area-header {
            color: var(--text-main);
            font-size: 16px;
            margin-bottom: 16px;
            padding-bottom: 8px;
            border-bottom: 1px solid var(--border-color);
        }

        .comment {
            display: flex;
            margin-top: 16px;
            position: relative;
        }

        .comment-collapse {
            width: 24px;
            display: flex;
            flex-direction: column;
            align-items: center;
            margin-right: 8px;
            cursor: pointer;
        }
        
        .comment-collapse-btn {
            color: var(--text-muted);
            font-size: 12px;
            line-height: 24px;
        }

        .collapse-line {
            width: 2px;
            flex-grow: 1;
            background-color: var(--border-color);
            margin-top: 4px;
            transition: background-color 0.2s;
        }
        
        .comment-collapse:hover .collapse-line {
            background-color: var(--text-main);
        }

        .comment-content {
            flex-grow: 1;
            min-width: 0;
        }

        .comment-meta {
            font-size: 12px;
            margin-bottom: 4px;
            display: flex;
            align-items: center;
            flex-wrap: wrap;
            gap: 6px;
        }

        .comment-author {
            font-weight: bold;
            color: var(--text-main);
            cursor: pointer;
            position: relative;
        }

        /* Tooltip */
        .bio-tooltip {
            visibility: hidden;
            background-color: var(--text-main);
            color: var(--bg-color);
            text-align: center;
            border-radius: 4px;
            padding: 8px 12px;
            position: absolute;
            z-index: 10;
            bottom: 125%;
            left: 50%;
            transform: translateX(-50%);
            width: max-content;
            max-width: 250px;
            font-weight: normal;
            font-size: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
            opacity: 0;
            transition: opacity 0.2s;
        }
        
        .bio-tooltip::after {
            content: "";
            position: absolute;
            top: 100%;
            left: 50%;
            margin-left: -5px;
            border-width: 5px;
            border-style: solid;
            border-color: var(--text-main) transparent transparent transparent;
        }

        .comment-author:hover .bio-tooltip {
            visibility: visible;
            opacity: 1;
        }

        .comment-flair {
            padding: 2px 6px;
            border-radius: 12px;
            font-size: 10px;
            font-weight: bold;
            color: #fff;
        }

        .comment-time {
            color: var(--text-muted);
        }

        .comment-body {
            font-size: 14px;
            margin-bottom: 8px;
        }

        .comment-actions {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 12px;
            font-weight: bold;
            color: var(--text-muted);
        }

        .comment-actions .vote-arrow {
            width: 16px;
            height: 16px;
            font-size: 12px;
        }
        
        .comment-vote-score {
            color: var(--text-main);
            font-weight: bold;
        }
        
        .comment-action-btn {
            padding: 4px;
            border-radius: 4px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        
        .comment-action-btn:hover {
            background-color: var(--hover-bg);
        }

        @media (max-width: 600px) {
            .container {
                padding: 10px 0;
            }
            .post-card, .comments-section, .stats-banner {
                border-radius: 0;
                border-left: none;
                border-right: none;
            }
        }
    </style>
</head>
<body>
    <div class="container" id="app"></div>

    <script id="sim-data" type="application/json">`;

const htmlBottom = `</script>

    <script>
        const data = JSON.parse(document.getElementById('sim-data').textContent);
        
        const flairColors = {
            'Early Founder': '#4CAF50',
            'Scaled Founder': '#2196F3',
            'Skeptical PM': '#f44336',
            'Indie Hacker': '#FF9800',
            'HR/People Ops': '#9C27B0',
            'Community Regular': '#795548',
            'VC/Growth': '#00BCD4',
            'Lurker': '#9E9E9E'
        };

        function timeAgo(dateString) {
            const date = new Date(dateString);
            const now = new Date('2026-03-22T08:00:00Z'); 
            const seconds = Math.floor((now - date) / 1000); 
            
            let interval = seconds / 31536000;
            if (interval > 1) return Math.floor(interval) + " years ago";
            interval = seconds / 2592000;
            if (interval > 1) return Math.floor(interval) + " months ago";
            interval = seconds / 86400;
            if (interval > 1) return Math.floor(interval) + " days ago";
            interval = seconds / 3600;
            if (interval > 1) return Math.floor(interval) + " hours ago";
            interval = seconds / 60;
            if (interval > 1) return Math.floor(interval) + " minutes ago";
            return "just now";
        }

        function formatText(text) {
            if (!text) return '';
            return text.split('\\n\\n').map(p => '<p>' + p.replace(/\\n/g, '<br>') + '</p>').join('');
        }

        function findProfile(authorId) {
            for (const [key, profile] of Object.entries(data.profiles)) {
                if (profile.username === authorId) return profile;
            }
            for (const [key, profile] of Object.entries(data.profiles)) {
                if (authorId.toLowerCase().includes(key.toLowerCase().replace(' ', '_'))) return profile;
            }
            return { archetype: 'Lurker', bio: 'Unknown user', username: authorId };
        }

        function renderStatsBanner() {
            return '<div class="stats-banner">' +
                   '  <div><strong>Simulated with 18 AI agents via OASIS + GPT-5.4-nano</strong></div>' +
                   '  <div>Score: +' + data.stats.score + ' | Comments: ' + data.stats.total_comments + ' | Engagement: ' + data.stats.commenting_agents + '/' + data.stats.total_agents + ' agents</div>' +
                   '</div>';
        }

        function renderPost() {
            const lines = data.post.content.split('\\n');
            const title = lines[0];
            const body = lines.slice(1).join('\\n').trim();
            const score = data.post.likes - data.post.dislikes;
            const scoreDisplay = score;

            return '<div class="post-card">' +
                   '  <div class="vote-sidebar">' +
                   '      <div class="vote-arrow up">▲</div>' +
                   '      <div class="vote-score">' + scoreDisplay + '</div>' +
                   '      <div class="vote-arrow down">▼</div>' +
                   '  </div>' +
                   '  <div class="post-content">' +
                   '      <div class="post-meta">' +
                   '          <span class="subreddit">r/SaaS</span>' +
                   '          <span class="author">• Posted by u/maya_flowpulse</span>' +
                   '          <span>' + timeAgo(data.post.created_at) + '</span>' +
                   '      </div>' +
                   '      <h1 class="post-title">' + title + '</h1>' +
                   '      <div class="post-body">' + formatText(body) + '</div>' +
                   '      <div class="post-actions">' +
                   '          <div class="action-btn">💬 ' + data.stats.total_comments + ' Comments</div>' +
                   '          <div class="action-btn">↪ Share</div>' +
                   '          <div class="action-btn">💾 Save</div>' +
                   '      </div>' +
                   '  </div>' +
                   '</div>';
        }

        function renderComments() {
            const sortedComments = [...data.comments].sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
            
            let html = '<div class="comments-section">';
            
            sortedComments.forEach(comment => {
                const profile = findProfile(comment.author);
                const flairColor = flairColors[profile.archetype] || '#9E9E9E';
                const score = comment.likes - comment.dislikes;
                const scoreDisplay = score > 0 ? '+' + score : score;
                
                html += '<div class="comment">' +
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
                        '          <span class="comment-time">' + scoreDisplay + ' points • ' + timeAgo(comment.created_at) + '</span>' +
                        '      </div>' +
                        '      <div class="comment-body">' + formatText(comment.content) + '</div>' +
                        '      <div class="comment-actions">' +
                        '          <span class="vote-arrow up">▲</span>' +
                        '          <span class="comment-vote-score">Reply</span>' +
                        '          <span class="vote-arrow down">▼</span>' +
                        '          <span class="comment-action-btn">Share</span>' +
                        '          <span class="comment-action-btn">Report</span>' +
                        '      </div>' +
                        '  </div>' +
                        '</div>';
            });
            
            html += '</div>';
            return html;
        }

        function init() {
            const app = document.getElementById('app');
            app.innerHTML = renderStatsBanner() + renderPost() + renderComments();
        }

        init();
    </script>
</body>
</html>`;

fs.writeFileSync('simulation/results/v1-thread.html', htmlTop + '\n' + dataRaw + '\n' + htmlBottom);
console.log('HTML generated successfully');
