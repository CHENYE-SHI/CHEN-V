# -*- coding: utf-8 -*-
"""把本地仓库内容同步到 GitHub（绕过 git push 被代理拦截的问题）。

做法：取远端 main 的完整文件树，与本地 git 追踪的文件逐个比对 blob 哈希，
只提交真正有变化的文件，最终生成一个提交并更新 main。

依赖已登录的 gh CLI（自动带鉴权与代理）。
"""
import base64
import hashlib
import json
import os
import subprocess
import sys

GH = r"C:\Program Files\GitHub CLI\gh.exe"
OWNER = "CHENYE-SHI"
REPO = "CHEN-V"
BRANCH = "main"
CWD = r"G:\CHEN-V主体"


def gh(args, stdin_data=None):
    p = subprocess.run([GH] + args, cwd=CWD, input=stdin_data,
                       capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        raise RuntimeError("gh 失败: %s\n%s\n%s" % (args[:3], p.stdout, p.stderr))
    return p.stdout


def gh_json(args, payload=None):
    if payload is None:
        return json.loads(gh(args))
    return json.loads(gh(args, json.dumps(payload)))


def blob_sha1(data):
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


def main():
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=CWD,
                          capture_output=True, text=True).stdout.strip()
    ref = gh_json(["api", "repos/%s/%s/git/ref/heads/%s" % (OWNER, REPO, BRANCH)])
    base_sha = ref["object"]["sha"]
    base_commit = gh_json(["api", "repos/%s/%s/git/commits/%s" % (OWNER, REPO, base_sha)])
    base_tree = base_commit["tree"]["sha"]
    print("远端 main: %s" % base_sha[:10])
    print("本地 HEAD: %s" % head[:10])

    remote_tree = gh_json(["api",
        "repos/%s/%s/git/trees/%s?recursive=1" % (OWNER, REPO, base_tree)])
    remote = {e["path"]: e["sha"] for e in remote_tree.get("tree", []) if e["type"] == "blob"}
    print("远端文件数: %d" % len(remote))

    # 本地 git 追踪的文件（-z 避免中文名被转义）
    raw = subprocess.run(["git", "-c", "core.quotepath=false", "ls-files", "-z"],
                         cwd=CWD, capture_output=True).stdout.decode("utf-8", "replace")
    files = [x for x in raw.split("\0") if x]
    local = {}
    for rel in files:
        full = os.path.join(CWD, rel.replace("/", os.sep))
        if not os.path.isfile(full):
            continue
        with open(full, "rb") as f:
            local[rel] = (blob_sha1(f.read()), full)

    adds, dels = [], []
    for rel, (sha, full) in local.items():
        if remote.get(rel) != sha:
            adds.append((rel, full))
    for rel in remote:
        if rel not in local:
            dels.append(rel)

    print("需要更新: %d 个，删除: %d 个" % (len(adds), len(dels)))
    if not adds and not dels:
        print("远端已是最新，无需提交。")
        return 0

    tree_items = []
    for rel, full in adds:
        with open(full, "rb") as f:
            data = f.read()
        blob = gh_json(["api", "repos/%s/%s/git/blobs" % (OWNER, REPO), "--input", "-"],
                       {"content": base64.b64encode(data).decode("ascii"),
                        "encoding": "base64"})
        tree_items.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        print("  + %-50s %8d" % (rel, len(data)))
    for rel in dels:
        tree_items.append({"path": rel, "mode": "100644", "type": "blob", "sha": None})
        print("  - %s" % rel)

    tree = gh_json(["api", "repos/%s/%s/git/trees" % (OWNER, REPO), "--input", "-"],
                   {"base_tree": base_tree, "tree": tree_items})

    msg = subprocess.run(["git", "log", "-1", "--pretty=%B"], cwd=CWD,
                         capture_output=True, text=True, encoding="utf-8").stdout.strip()
    commit = gh_json(["api", "repos/%s/%s/git/commits" % (OWNER, REPO), "--input", "-"],
                     {"message": msg, "tree": tree["sha"], "parents": [base_sha]})
    print("新提交: %s" % commit["sha"])

    gh_json(["api", "-X", "PATCH",
             "repos/%s/%s/git/refs/heads/%s" % (OWNER, REPO, BRANCH), "--input", "-"],
            {"sha": commit["sha"], "force": False})
    print("已更新 %s" % BRANCH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
