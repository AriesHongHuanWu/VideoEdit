import concurrent.futures as futures
import hashlib
import html
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from urllib.parse import quote, urljoin, urlparse

import requests

REPO = "AriesHongHuanWu/VideoEdit"
TAG = "videoedit-italy-rome"
BRANCH = os.environ["TARGET_BRANCH"]
API = f"https://api.github.com/repos/{REPO}"
HEADERS = {"Authorization": f"Bearer {os.environ['GH_TOKEN']}",
           "Accept": "application/vnd.github+json",
           "X-GitHub-Api-Version": "2022-11-28"}
LIMIT = 2**31 - 1
PART = 1500 * 1024**2
BLOCK = 4 * 1024**2


def api(method, path, **kwargs):
    with requests.request(method, API + path, headers=HEADERS, timeout=(20, 60), **kwargs) as response:
        response.raise_for_status()
        return response.json()


def list_assets(release):
    items = {}
    for page in range(1, 6):
        rows = api("GET", f"/releases/{release['id']}/assets", params={"per_page": 100, "page": page})
        items.update((row["name"], row) for row in rows)
        if len(rows) < 100:
            return items
    raise RuntimeError("Unexpected number of GitHub release assets")


def draft_release():
    for release in api("GET", "/releases", params={"per_page": 100}):
        if release["tag_name"] == TAG:
            return release
    return api("POST", "/releases", json={
        "tag_name": TAG, "target_commitish": BRANCH, "name": "VideoEdit | Italy and Rome",
        "body": "Original camera footage. The videoedit directory contains the file index and SHA-256 checksums.",
        "draft": True, "make_latest": "false",
    })


def layout(record):
    name = record["group"] + "--" + record["name"].replace(" ", "_")
    size = record["size"]
    if size <= LIMIT:
        return [(name, size)]
    return [(f"{name}.part{index + 1:02d}", min(PART, size - offset))
            for index, offset in enumerate(range(0, size, PART))]


def drive_confirmation(body, base):
    form = re.search(r"""<form\b(?=[^>]*\bid=["']download-form["'])[^>]*>(.*?)</form>""", body, re.S | re.I)
    if not form:
        raise RuntimeError("Drive returned HTML without a download confirmation form")
    action = re.search(r"""action=["']([^"']+)""", form.group(0).split(">", 1)[0], re.I)
    target = urljoin(base, html.unescape(action.group(1))) if action else ""
    if urlparse(target).hostname not in {"drive.google.com", "drive.usercontent.google.com"}:
        raise RuntimeError("Unexpected Drive download form")
    params = {}
    for entry in re.findall(r"<input\b[^>]*>", form.group(1), re.I):
        attrs = {key.lower(): html.unescape(value) for key, _, value in re.findall(
            r"""([\w-]+)\s*=\s*(["'])(.*?)\2""", entry)}
        if "name" in attrs and "value" in attrs:
            params[attrs["name"]] = attrs["value"]
    return target, params


def download(record, path, url):
    params = {"id": record["id"], "export": "download", "confirm": "t"}
    with requests.Session() as session:
        session.headers["User-Agent"] = "Mozilla/5.0"
        for _ in range(3):
            with session.get(url, params=params, timeout=(20, 80), stream=True) as response:
                response.raise_for_status()
                if "text/html" in response.headers.get("Content-Type", "").lower():
                    url, params = drive_confirmation(response.text, response.url)
                    continue
                digest, count = hashlib.sha256(), 0
                with path.open("wb") as stream:
                    for chunk in response.iter_content(BLOCK):
                        if not count and (len(chunk) < 8 or chunk[4:8] != b"ftyp"):
                            raise RuntimeError("Drive response is not an original MP4")
                        count += len(chunk)
                        if count > record["size"]:
                            raise RuntimeError("Drive sent more data than the source metadata")
                        stream.write(chunk)
                        digest.update(chunk)
                if count != record["size"]:
                    raise RuntimeError(f"Size mismatch: {count} vs {record['size']}")
                return digest.hexdigest()
    raise RuntimeError("Drive confirmation did not reach the file")


def matches(asset, size, digest=None):
    return (asset and asset["state"] == "uploaded" and asset["size"] == size
            and (asset.get("digest") or "").startswith("sha256:")
            and (digest is None or asset["digest"] == f"sha256:{digest}"))


def upload(release, name, size, path, digest):
    url = release["upload_url"].split("{", 1)[0]
    if urlparse(url).hostname != "uploads.github.com":
        raise RuntimeError("Unexpected GitHub upload host")
    headers = {**HEADERS, "Content-Type": "video/mp4" if name.lower().endswith(".mp4") else "application/octet-stream"}
    error = None
    for attempt in range(4):
        try:
            with path.open("rb") as file:
                with requests.post(url, params={"name": name}, data=file, headers=headers,
                                   timeout=(25, 200)) as response:
                    if response.status_code == 201:
                        asset = response.json()
                        if asset["name"] == name and matches(asset, size, digest):
                            return asset
                        raise RuntimeError("GitHub did not confirm the expected SHA-256")
                    error = f"HTTP {response.status_code}"
                    if response.status_code in (400, 401, 403, 404):
                        raise RuntimeError(f"GitHub refused asset upload ({error})")
        except requests.RequestException as exc:
            error = type(exc).__name__
        asset = list_assets(release).get(name)
        if matches(asset, size, digest):
            return asset
        if asset and asset["state"] == "starter" and asset["size"] == 0:
            with requests.delete(API + f"/releases/assets/{asset['id']}", headers=HEADERS,
                                 timeout=(20, 60)) as abandoned:
                abandoned.raise_for_status()
        time.sleep(2**attempt)
    raise RuntimeError(f"GitHub asset upload not confirmed ({error})")


def transfer(release, existing, item):
    file_layout = layout(item)
    name, size = file_layout[0]
    saved = existing.get(name)
    if len(file_layout) == 1 and matches(saved, size):
        return (item, saved["digest"].split(":")[1], [saved])

    with tempfile.TemporaryDirectory(prefix="videoedit-drive-") as tmp:
        root = Path(tmp)
        original = root / "original.mp4"
        for attempt in range(4):
            url = ("https://drive.usercontent.google.com/download" if attempt % 2 == 0
                   else "https://drive.google.com/uc")
            try:
                digest = download(item, original, url)
                break
            except (requests.RequestException, RuntimeError):
                if attempt == 3:
                    raise
                time.sleep(2**attempt)
        if len(file_layout) == 1:
            return (item, digest, [upload(release, name, size, original, digest)])
        parts = []
        with original.open("rb") as video:
            for name, size in file_layout:
                part = root / name
                h = hashlib.sha256()
                left = size
                with part.open("wb") as out:
                    while left:
                        chunk = video.read(min(BLOCK, left))
                        if not chunk:
                            raise RuntimeError("Unexpected end while splitting the original video")
                        out.write(chunk)
                        h.update(chunk)
                        left -= len(chunk)
                current = existing.get(name)
                parts.append(current if matches(current, size, h.hexdigest())
                             else upload(release, name, size, part, h.hexdigest()))
                part.unlink()
        return (item, digest, parts)


def git(*args):
    subprocess.run(["git", *args], check=True)


def commit_index(records):
    git("fetch", "origin", BRANCH)
    git("switch", "--detach", "FETCH_HEAD")
    root = Path("videoedit")
    index = {"release_tag": TAG, "files": []}
    if root.exists():
        prev = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        if prev["release_tag"] == TAG and len(prev["files"]) == len(records):
            return
        raise RuntimeError("The target videoedit directory already exists")
    root.mkdir()
    raw_release = f"https://github.com/{REPO}/releases/tag/{TAG}"
    (root / "README.md").write_text(
        "# VideoEdit\n\n"
        f"The [GitHub release]({raw_release}) stores the original MP4 bytes.\n\n"
        "- [Italy — 217 originals](Italy/README.md)\n"
        "- [Rome — 35 originals](Rome/README.md)\n"
        "- [Byte counts, hashes and asset URLs](manifest.json)\n\n"
        "Two Italy files use two numbered parts. In a cloud Linux shell, combine them in part order. "
        "For example:\n\n"
        "    cat Italy--DJI_0141.MP4.part01 Italy--DJI_0141.MP4.part02 > DJI_0141.MP4\n\n"
        "Compare the restored file's SHA-256 with the manifest.\n",
        encoding="utf-8",
    )
    for group in ("Italy", "Rome"):
        folder = root / group
        folder.mkdir()
        rows = [f"# {group}", "", "| Original video | Bytes | GitHub assets |", "| --- | ---: | --- |"]
        for item, digest, stored in records:
            if item["group"] != group:
                continue
            raw = {k: item[k] for k in ("group", "name", "size")}
            raw["sha256"] = digest
            raw["assets"] = []
            links = []
            for number, asset in enumerate(stored, 1):
                name = asset["name"]
                url = f"https://github.com/{REPO}/releases/download/{TAG}/{quote(name)}"
                label = "Download" if len(stored) == 1 else f"Part {number}"
                links.append(f"[{label}]({url})")
                raw["assets"].append({**{k: asset[k] for k in ("name", "size", "digest")}, "url": url})
            index["files"].append(raw)
            rows.append(f"| {item['name']} | {item['size']:,} | {' · '.join(links)} |")
        (folder / "README.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    (root / "manifest.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    git("add", "--", "videoedit")
    git("-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
        "commit", "-m", "Index Italy and Rome original footage")
    git("push", "origin", f"HEAD:refs/heads/{BRANCH}")


def main():
    source = [item for path in sorted(Path(".github/drive-video-import").glob("sources-*.json"))
              for item in json.loads(path.read_text(encoding="utf-8"))]
    assert len(source) == 252 and sum(r["size"] for r in source) == 64666279928
    assert all(r["group"] in ("Italy", "Rome") and re.fullmatch(r"DJI_\d{4}(?: \d+)?\.MP4", r["name"], re.I)
               and re.fullmatch(r"[-\w]+", r["id"]) and r["size"] > 0 for r in source)
    wanted = dict(asset for r in source for asset in layout(r))
    assert len(wanted) == 254
    release = draft_release()
    existing = list_assets(release)
    if existing.keys() - wanted.keys():
        raise RuntimeError("Unexpected assets already exist")
    if not release["draft"]:
        if {n: a["size"] for n, a in existing.items()} != wanted:
            raise RuntimeError("Published release asset sizes do not match")
        print("Already completed and verified", flush=True)
        return
    completed, failures = [], []
    samples = [min((r for r in source if r["group"] == group), key=lambda r: r["size"])
               for group in ("Italy", "Rome")]
    for r in samples:
        completed.append(transfer(release, existing, r))
        print(f"Cloud transfer verified for {r['group']}", flush=True)
    standard = [r for r in source if r not in samples and r["size"] <= LIMIT]
    standard.sort(key=lambda r: r["size"], reverse=True)
    with futures.ThreadPoolExecutor(max_workers=5) as pool:
        jobs = {pool.submit(transfer, release, existing, r): r for r in standard}
        for job in futures.as_completed(jobs):
            try:
                completed.append(job.result())
            except Exception as error:
                name = jobs[job]["name"]
                message = str(error).split("?")[0]
                print(f"Retry needed for {name}: {message}", flush=True)
                failures.append(name)
            else:
                if len(completed) % 10 == 0:
                    print(f"Verified {len(completed)}/252 original files", flush=True)
    for r in (r for r in source if r["size"] > LIMIT):
        completed.append(transfer(release, existing, r))
        print(f"Verified split original {r['name']}", flush=True)
    if failures:
        raise RuntimeError(f"Rerun to resume. Failed transfers: {failures}")
    checked = list_assets(release)
    if len(completed) != 252 or {n: a["size"] for n, a in checked.items()} != wanted:
        raise RuntimeError("Final GitHub asset inventory mismatch")
    if not all(matches(a, a["size"]) for a in checked.values()):
        raise RuntimeError("GitHub asset verification incomplete")
    completed.sort(key=lambda row: (row[0]["group"], row[0]["name"]))
    commit_index(completed)
    result = api("PATCH", f"/releases/{release['id']}", json={"draft": False, "make_latest": "false"})
    assert not result["draft"]
    print(f"Published {len(completed)} originals as {len(checked)} verified assets", flush=True)


if __name__ == "__main__":
    main()
