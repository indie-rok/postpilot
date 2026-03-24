from prompts.humanizer import WRITING_RULES

ANALYZE_SYSTEM = "You analyze Reddit community feedback with precision."

ANALYZE = """You are analyzing Reddit comments on a launch post.
These are from a simulation with AI agents playing different community archetypes.

COMMENTS:
{comments_text}

Analyze and produce a structured report:

## What Resonated
- Which claims/numbers/framings got positive reactions? Quote specific phrases.

## What Got Pushback
- Which claims got challenged? What were the specific objections?

## Top Recurring Questions
- What did multiple agents ask about? Rank by frequency.

## Positioning Gaps
- Where did agents say "how is this different from X?" What was missing?

## Pricing Feedback
- What was the sentiment on pricing? Any specific suggestions?

## Strongest Hook
- What single element generated the most engagement?

## Recommendations for V2
- 5 specific, actionable changes to make the post perform better.

Be concrete. Quote the comments. No generic advice."""

REWRITE_SYSTEM = "You write authentic Reddit launch posts.\n\n" + WRITING_RULES

REWRITE = """You are rewriting a Reddit launch post based on community feedback.

ORIGINAL POST:
{original_post}

ANALYSIS OF COMMUNITY FEEDBACK:
{analysis}

Rewrite the post applying the feedback. Specific instructions:
- Keep the same voice and author identity as the original post
- Lead with whatever the analysis identified as the strongest hook
- Address the top objections preemptively (don't wait for comments to raise them)
- Tighten the positioning against competitors mentioned in feedback
- Adjust pricing framing based on feedback (if applicable)
- Cut anything the analysis flagged as weak or ignored
- Keep it Reddit-native — no corporate speak, no hard sell
- Same approximate length as the original
- End with questions that invite the specific feedback you want

Output ONLY the rewritten post, no commentary."""
