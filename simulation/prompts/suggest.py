SYSTEM = "You write authentic Reddit launch posts."

SUGGEST_POST = """Write a compelling Reddit launch post for the subreddit {subreddit}.

PRODUCT INFO:
{product_info}

COMMUNITY PERSONAS ({persona_count} members):
Archetypes: {archetypes}

Write the post as if you are the founder/maker posting in {subreddit}. Make it:
- Authentic and conversational (not salesy)
- Include specific metrics, numbers, or learnings if available from the product info
- Ask 2-3 genuine questions to spark discussion
- Match the tone of {subreddit}
- Address concerns that the community archetypes would likely raise
- Keep it under 500 words

Return ONLY the post text, no title prefix, no markdown formatting."""
