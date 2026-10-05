---
model_alias: writing-default
default_model: gpt-example
response_format: json_object
max_completion_tokens: 1200
style:
  label: Warm editorial
  order: 3
  colors:
    primary: "#284b63"
    accent: "#d98e32"
  chart_style:
    grid: light
    palette: [blue, orange, gray]
tones:
  - label: Direct
    slot: linkedin
---

# system
Write about {{ topic }}.

# user
Audience: {{ audience }}
