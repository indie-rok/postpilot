SYSTEM = "You classify Reddit comments. Return ONLY valid JSON."

COMMENT_CLASSIFICATION = """Classify each Reddit comment. Return ONLY valid JSON:

{{
  "comments": [
    {{
      "comment_id": <int>,
      "sentiment": "positive" | "negative" | "neutral",
      "topics": ["<descriptive 3-6 word phrase>"],
      "is_objection": true | false,
      "is_feature_request": true | false,
      "feature_requested": "<feature name>" | null,
      "objection_type": "trust" | "value" | "technical" | "pricing" | null,
      "would_click_link": "yes" | "likely" | "unlikely" | "no",
      "would_signup": "yes" | "likely" | "unlikely" | "no",
      "understands_product": "yes" | "partially" | "no",
      "would_recommend": "yes" | "maybe" | "no",
      "is_question": true | false,
      "mentions_competitor": true | false,
      "competitor_name": "<name>" | null,
      "mentions_pricing": true | false
    }}
  ]
}}

IMPORTANT: topics must be descriptive phrases, NOT single words.
Good: "burnout radar approach praised", "pricing too high for startups"
Bad: "pricing", "burnout", "privacy"

Field guidance:
- objection_type: categorize the objection (trust=credibility/data concerns, value=why not use X, technical=integration/architecture, pricing=cost). null if not an objection.
- would_click_link: based on tone and interest level, would this person click a link to try the app?
- would_signup: would they actually create an account? (stricter than clicking)
- understands_product: does the comment show they grasp what the product does?
- would_recommend: would they tell a colleague about this?
- is_question: is the comment primarily asking a question?
- mentions_competitor: does the comment name a competing product?
- mentions_pricing: does the comment discuss pricing, cost, or budget?

Comments:
{comment_block}"""

INTERVIEW_CLARITY = """Rate each person's understanding of the product AND their intent to engage.

The product: {post_summary}

Return ONLY valid JSON:
{{
  "ratings": [
    {{
      "index": 1,
      "clarity": "accurate" | "partial" | "wrong",
      "would_click": "yes" | "likely" | "unlikely" | "no",
      "would_signup": "yes" | "likely" | "unlikely" | "no"
    }}
  ]
}}

- clarity: "accurate" = correctly identifies product + audience, "partial" = gets some right, "wrong" = misunderstands
- would_click: based on their response, would they visit the link? Look for expressed curiosity or interest.
- would_signup: stricter — would they actually create an account? Look for explicit intent or strong enthusiasm.

Responses:
{response_block}"""
