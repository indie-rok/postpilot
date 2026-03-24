SYSTEM = "You generate realistic Reddit user personas based on community data. Return ONLY valid JSON."

PERSONA_GENERATION = """Based on the following subreddit community data, generate {count} diverse user personas that represent the typical members of this community.

SUBREDDIT: {subreddit}
DESCRIPTION: {description}
SUBSCRIBERS: {subscribers}
LINK FLAIRS: {flairs}

TOP POSTS (titles + engagement):
{posts_summary}

SAMPLE COMMENTS (showing community voice/tone):
{comments_summary}

MOST ACTIVE USERS:
{authors_summary}

---

Generate exactly {count} personas. Each persona should represent a DIFFERENT archetype of community member — vary their engagement style, expertise level, sentiment tendency, and background.

For each persona, return a JSON object with these fields:
- "username": a realistic Reddit-style username (lowercase, underscores ok)
- "realname": a realistic full name
- "archetype": a short label for this persona type (e.g. "Power User", "Skeptic", "Lurker", "Industry Expert", "Newbie", "Enthusiast")
- "bio": one sentence about who they are
- "persona": a detailed behavioral description (150-250 words) explaining how this person engages in {subreddit} — their posting style, what they upvote/downvote, typical reactions, knowledge level, biases, and tone. This is the most important field — it drives the simulation.
- "age": realistic age (18-65)
- "gender": "male" or "female"
- "mbti": a realistic MBTI type
- "country": country of residence
- "profession": their job title/profession
- "interested_topics": list of 3-5 topics they follow

Return ONLY a JSON array of {count} objects. No explanation, no markdown formatting outside the JSON."""
