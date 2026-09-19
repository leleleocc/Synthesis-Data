from pathlib import Path
import rewardkit as rk
from rewardkit import criterion


# FIXED: shared criteria require an explicit rk registration call with the weight below.
@criterion(shared=True)
def answer_is_ready(workspace: Path) -> bool:
    path = workspace / "answer.txt"
    return path.is_file() and path.read_text(encoding="utf-8") == "ready\n"


# FIXED: keep weight on the registration call, not on @criterion.
rk.answer_is_ready(weight=1)
