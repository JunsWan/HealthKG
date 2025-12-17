import json
import time
import cloudscraper
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# ====================================================
# 参数配置
# ====================================================
BASE_URL = "https://exrx.net"
BODY_PARTS = [
    "Neck", "Should", "Arm", "ForeArm",
    "Back", "Chest", "Waist", "Hips", "Thigh", "Calf"
]
OUTPUT_JSON = "../data/exrx_full_dataset.json"

# 初始化 Scraper（模拟真实浏览器）
scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "mobile": False}
)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.google.com/",
    "Accept-Language": "en-US,en;q=0.9",
}

# ====================================================
# 工具函数
# ====================================================
def safe_get(url, retries=3, delay=3):
    """安全请求，带重试机制"""
    for i in range(retries):
        try:
            r = scraper.get(url, headers=HEADERS, timeout=25)
            if r.status_code == 200:
                return r.text
            print(f"⚠️ 状态码 {r.status_code}，重试中 ({i+1}/{retries})...")
        except Exception as e:
            print(f"❌ 请求异常 {i+1}/{retries}: {e}")
        time.sleep(delay)
    return None


def normalize_exercise_url(href):
    """标准化 URL"""
    href = href.strip()
    if href.startswith("http"):
        return href
    if href.startswith("../../"):
        href = href.replace("../../", "")
    return urljoin(BASE_URL + "/", href)


# ====================================================
# 动作详情页解析
# ====================================================
def parse_exercise_detail(url):
    """解析单个动作详情页"""
    print(f"   🔍 解析动作页面: {url}")
    html = safe_get(url)
    data = {"exercise_url": url}
    if not html:
        print("   ⚠️ 页面访问失败")
        return data

    soup = BeautifulSoup(html, "html.parser")

    # ---------- Classification ----------
    cls = soup.find("h2", string=lambda s: s and "Classification" in s)
    if cls:
        table = cls.find_next("table")
        if table:
            for tr in table.find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) == 2:
                    key = tds[0].get_text(strip=True).replace(":", "")
                    val = tds[1].get_text(" ", strip=True)
                    data[key] = val

    # ---------- Instructions ----------
    instr = soup.find("h2", string=lambda s: s and "Instructions" in s)
    if instr:
        ps = []
        for p in instr.find_all_next("p"):
            if p.find_previous_sibling("h2") == instr:
                ps.append(p.get_text(" ", strip=True))
            elif p.find_previous("h2") != instr:
                break
        data["Instructions"] = " ".join(ps)

    # ---------- Comments ----------
    comments = soup.find("h2", string=lambda s: s and "Comments" in s)
    if comments:
        ps = []
        for p in comments.find_all_next("p"):
            if p.find_previous_sibling("h2") == comments:
                ps.append(p.get_text(" ", strip=True))
            elif p.find_previous("h2") != comments:
                break
        data["Comments"] = " ".join(ps)

    # ---------- Muscles ----------
    muscles_section = soup.find("h2", string=lambda s: s and "Muscles" in s)
    if muscles_section:
        muscles = {}
        cur_cat = None
        for tag in muscles_section.find_all_next():
            if tag.name == "p":
                strong = tag.find("strong")
                if strong:
                    cur_cat = strong.get_text(strip=True)
                    muscles[cur_cat] = []
            elif tag.name == "ul" and cur_cat:
                muscles[cur_cat].extend(
                    [li.get_text(" ", strip=True) for li in tag.find_all("li")]
                )
            elif tag.name == "h2":
                break
        data["Muscles"] = muscles

    return data


# ====================================================
# 部位页面解析
# ====================================================
def parse_bodypart_page(body_part):
    """解析某个部位页面的所有动作"""
    part_url = f"{BASE_URL}/Lists/ExList/{body_part}Wt"
    print(f"\n🦾 抓取部位页面: {part_url}")
    html = safe_get(part_url)
    if not html:
        print(f"❌ 无法访问 {body_part} 页面，跳过")
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = []

    for h2 in soup.find_all("h2"):
        a_tag = h2.find("a", href=True)
        if not a_tag:
            continue
        muscle = a_tag.text.strip()
        if not muscle:
            continue

        # 收集到下一个 h2 为止的所有 HTML 块
        section_tags = []
        for sibling in h2.find_all_next():
            if sibling.name == "h2":
                break
            section_tags.append(sibling)

        section_html = BeautifulSoup("".join(str(t) for t in section_tags), "html.parser")

        # 遍历 li（训练方式）
        for li in section_html.find_all("li", recursive=False):
            training_type = li.find(text=True, recursive=False)
            if not training_type:
                continue
            training_type = training_type.strip()
            sub_ul = li.find("ul")
            if sub_ul:
                for a in sub_ul.find_all("a", href=True):
                    href = a["href"]
                    full_url = normalize_exercise_url(href)
                    exercise_name = a.text.strip()
                    results.append({
                        "body_part": body_part,
                        "muscle": muscle,
                        "training_type": training_type,
                        "exercise_name": exercise_name,
                        "exercise_url": full_url
                    })
    return results


# ====================================================
# 主流程
# ====================================================
def crawl_all_bodyparts():
    all_data = []

    for part in BODY_PARTS:
        exercises = parse_bodypart_page(part)
        print(f"✅ {part}: 找到 {len(exercises)} 个动作")
        for ex in exercises:
            print(f"\n 动作: {ex['exercise_name']} ({ex['training_type']})")
            detail = parse_exercise_detail(ex["exercise_url"])
            combined = {**ex, **detail}
            all_data.append(combined)
            time.sleep(0.5)  # 控制速率，防止封禁

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    print(f"\n 全部完成，共收集 {len(all_data)} 条动作记录 → {OUTPUT_JSON}")


# ====================================================
# 执行入口
# ====================================================
if __name__ == "__main__":
    crawl_all_bodyparts()
