"""下载 Issue 正文和评论里的图片，供 Claude 读取。

GitHub 评论里粘贴的图片是私有链接，直接访问会被拒绝。
这里通过 API 取回带签名的地址（body_html 里的 img src），再下载到本地。
用法: python3 fetch_images.py <owner/repo> <issue编号> <输出目录>
需要环境变量 GH_TOKEN。
"""
import json
import os
import re
import sys
import urllib.request

repo, number, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
token = os.environ["GH_TOKEN"]
os.makedirs(out_dir, exist_ok=True)

API = "https://api.github.com"
IMG_SRC = re.compile(r'<img[^>]+src="([^"]+)"', re.I)
MAX_BYTES = 10 * 1024 * 1024


def api_get(path):
    req = urllib.request.Request(
        API + path,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.full+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def ext_for(data):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None  # 不是图片就跳过


def download(url):
    req = urllib.request.Request(url, headers={"User-Agent": "claude-trial"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read(MAX_BYTES + 1)


issue = api_get(f"/repos/{repo}/issues/{number}")
sources = [("issue-body", issue.get("user", {}).get("login"), issue.get("body_html") or "")]
page = 1
while True:
    comments = api_get(f"/repos/{repo}/issues/{number}/comments?per_page=100&page={page}")
    if not comments:
        break
    for c in comments:
        sources.append((f"comment-{c['id']}", c["user"]["login"], c.get("body_html") or ""))
    page += 1

index = []
for label, author, html in sources:
    for i, url in enumerate(dict.fromkeys(IMG_SRC.findall(html)), 1):
        # 只下载用户上传的图片，跳过徽章、外链等
        if not re.match(r"https://(private-user-images|user-images)\.githubusercontent\.com/|https://github\.com/user-attachments/", url):
            continue
        try:
            data = download(url)
        except Exception as e:  # noqa: BLE001
            print(f"下载失败 {label} #{i}: {e}")
            continue
        ext = ext_for(data)
        if len(data) > MAX_BYTES or not ext:
            print(f"跳过 {label} #{i}（不是图片或超过 10MB）")
            continue
        name = f"{label}-{i}{ext}"
        with open(os.path.join(out_dir, name), "wb") as f:
            f.write(data)
        index.append(f"{name}\t来自 {label}（作者 {author}）")
        print(f"已保存 {name}")

with open(os.path.join(out_dir, "index.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(index) + ("\n" if index else "（没有图片）\n"))
print(f"共 {len(index)} 张图片")
