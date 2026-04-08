from pathlib import Path
import json

DATA = Path("/instance")
DATA.mkdir(exist_ok=True)
(DATA / "stories").mkdir(exist_ok=True)

stories_path = DATA / "stories.json"
if not stories_path.exists():
    stories_path.write_text("[]")
