curl -s https://generativelanguage.googleapis.com/v1beta/decisions \
  -H "x-goog-api-key: $GEMINI_API_KEY" -H 'Content-Type: application/json' \
  -d '{
    "model": "gemini-decision-1",
    "input": "My card was charged twice for the same order.",
    "questions": {
      "dept":    {"type": "choice", "instructions": "Which team should handle this ticket?",
                  "criteria": {"billing": "Payments, invoices, refunds.", "shipping": "Delivery and tracking.", "other": ""}},
      "angry":   {"type": "noul",   "instructions": "Is the customer upset?"},
      "urgency": {"type": "score",  "instructions": "How urgent is this?", "criteria": ["low", "medium", "high"]}
    }
  }'
