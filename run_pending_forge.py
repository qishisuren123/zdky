"""
补跑脚本：对 pending_forge_seeds.json 里的种子运行 Idea Forge
在免费窗口（北京时间 00:00-08:00）内运行，优先使用灵活 Claude
"""
import sys
import json
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent / "src" / "collectors"))

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

PENDING_FILE = Path(__file__).parent / "data" / "pending_forge_seeds.json"


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_DIR / f"pending_forge_{datetime.now().strftime('%Y%m%d')}.log", "a") as f:
        f.write(line + "\n")


def main():
    if not PENDING_FILE.exists():
        log("无 pending_forge_seeds.json，退出")
        return

    with open(PENDING_FILE) as f:
        seeds = json.load(f)

    # 兼容两种格式：直接是 list，或带壳 {"seeds": [...], "count": N}
    if isinstance(seeds, dict):
        seeds = seeds.get("seeds") or seeds.get("candidates") or seeds.get("final_candidates") or []

    if not seeds:
        log("pending_forge_seeds.json 为空，退出")
        return

    log(f"读取到 {len(seeds)} 个待补跑种子")

    from idea_forge.forge import run_idea_forge
    from idea_forge.b_library import get_b_library

    b_ids = [b["id"] for b in get_b_library()]
    try:
        result = run_idea_forge(seeds, b_ids=b_ids)
        s = result.get("summary", {})
        log(f"Forge 完成: ideas={s.get('total_ideas')} validated={s.get('total_validated')} plans={s.get('total_plans')}")
    except Exception as e:
        log(f"Forge 失败: {e}")
        return

    # 清空 pending 文件（保留与读入时一致的壳结构）
    with open(PENDING_FILE, "w") as f:
        json.dump({"seeds": [], "count": 0}, f, ensure_ascii=False, indent=2)
    log("pending_forge_seeds.json 已清空")

    # 更新网页
    try:
        from generate_dashboard import generate_html
        generate_html()
        log("主页已更新")
    except Exception as e:
        log(f"主页更新失败: {e}")

    try:
        from generate_idea_page import generate as gen_idea
        gen_idea()
        log("Idea 页面已更新")
    except Exception as e:
        log(f"Idea 页面更新失败: {e}")

    # 推送
    import subprocess
    try:
        subprocess.run(["git", "add", "index.html", "ideas.html"],
                       cwd=str(Path(__file__).parent), capture_output=True)
        subprocess.run(["git", "commit", "-m", f"Pending forge: {datetime.now().strftime('%Y-%m-%d')}"],
                       cwd=str(Path(__file__).parent), capture_output=True)
        subprocess.run(["git", "push", "origin", "gh-pages"],
                       cwd=str(Path(__file__).parent), capture_output=True)
        log("Git push 完成")
    except Exception as e:
        log(f"Git push 失败: {e}")


if __name__ == "__main__":
    main()
