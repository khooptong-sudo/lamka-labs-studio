from app.cineprompt import build_prompt

print(build_prompt({"mode": "single", "model": "veo", "fields": {
    "media_type": "cinematic", "genre": ["thriller"],
    "char_label": "a woman", "age_range": "in their 30s",
    "shot_type": "wide shot", "movement": "pan",
    "camera_body": "shot on ARRI Alexa 65",
    "color_science": "ARRI LogC4 flat log footage, ungraded",
    "setting": "a cramped office", "env_time": "dawn, first light",
}})[0])
