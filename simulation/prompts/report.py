SYSTEM = "You are an expert analyst reviewing Reddit simulation data."

SENTIMENT = (
    "Classify each comment below as exactly one of: supportive, neutral, skeptical.\n"
    "Return ONLY valid JSON: a list of objects with keys 'user_name', 'sentiment'.\n\n"
    "Comments:\n{comment_texts}"
)

THEMES = (
    "Extract the top 3-5 recurring themes from these Reddit comments.\n"
    "Return ONLY a JSON list of short theme strings.\n\n"
    "Comments:\n{comment_texts}"
)

INSIGHTS = (
    "Based on this Reddit simulation data, provide 3-5 actionable recommendations "
    "for the product team.\n\n"
    "Engagement score: {score}\n"
    "Likes: {num_likes}, Dislikes: {num_dislikes}\n"
    "Comments: {comment_count}\n"
    "Top themes: {themes}\n\n"
    "Sample comments:\n{comment_texts}\n\n"
    "Return ONLY a JSON list of recommendation strings."
)
