SYSTEM = ""

PRODUCT_PROFILE = """You are analyzing a software project. Based on the files below, generate a product profile.

Return ONLY valid JSON with exactly these 4 fields:
{{
  "name": "Product name",
  "problem": "One condensed paragraph about the problem it solves. No marketing language.",
  "features": "3-6 bullet points, each under 10 words. Separated by newlines.",
  "audience": "One sentence: who is this for?"
}}

Be extremely concise. No filler. Write like a developer explaining their product to a friend.

---
PROJECT FILES:
"""
