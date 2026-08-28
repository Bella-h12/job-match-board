# -*- coding: utf-8 -*-
"""给某个人打分出榜：python3 core/run.py people/<名字> [JD缓存目录]"""
import glob, io, json, os, re, sys, unicodedata, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import facts as F
import score
spec = importlib.util.spec_from_file_location("er", HERE + "/extract_reqs.py")
er = importlib.util.module_from_spec(spec); spec.loader.exec_module(er)


def load_jds(cache_dir):
    jd = {}
    for f in glob.glob(os.path.join(cache_dir, "*-out.json")):
        try:
            d = json.load(io.open(f, encoding="utf-8"))
        except Exception:
            continue
        for it in (d if isinstance(d, list) else []):
            try:
                jid = it["call"]["args"]["job_id"]
                t = json.loads(it["result"]).get("sections", {}).get("job_posting", "")
                if t and len(t) > len(jd.get(jid, "")):
                    jd[jid] = t
            except Exception:
                pass
    return jd


def main():
    person = sys.argv[1].rstrip("/")
    cache = sys.argv[2] if len(sys.argv) > 2 else os.path.join(person, "jd-cache")
    judge = F.load(person)                      # confirmed=false 会在这里退出
    jd = load_jds(cache)
    rows = []
    for jid, t in jd.items():
        tn = unicodedata.normalize("NFKC", t)
        closed = bool(re.search(r"No longer accepting applications", tn, re.I))
        e = er.extract(tn)
        must = [(x, judge.judge(x)[0]) for x in e["must"] if not F.is_header(x)]
        nice = [(x, judge.judge(x)[0]) for x in e["nice"] if not F.is_header(x)]
        v, hit, tot, adj, kind = score.fit_of(dict(reqs=dict(must=must, nice=nice)))
        head = [l.strip() for l in tn.split("\n") if l.strip()][:3]
        rows.append(dict(id=jid, co=head[0] if head else "", role=head[1] if len(head) > 1 else "",
                         meta=head[2] if len(head) > 2 else "", closed=closed,
                         fit=v, hit=hit, tot=tot, kind=kind,
                         must=[[x, h, judge.judge(x)[1]] for x, h in must],
                         nice=[[x, h] for x, h in nice]))
    json.dump(rows, io.open(person + "/scored.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    live = sorted([r for r in rows if not r["closed"] and r["kind"] == "scored"],
                  key=lambda r: -r["fit"])
    print("%s：JD %d 份 · 在招且可打分 %d 个 · 无硬门槛 %d · 未核 %d"
          % (os.path.basename(person), len(rows), len(live),
             sum(1 for r in rows if r["kind"] == "无硬门槛"),
             sum(1 for r in rows if r["kind"] == "未核")))
    print()
    for i, r in enumerate(live[:10], 1):
        print("%2d  %3d  %-26s %-46s %g/%d" % (i, r["fit"], r["co"][:25], r["role"][:45], r["hit"], r["tot"]))
    print("\n逐条判据落在 %s/scored.json（每条要求带原文 + 为什么算命中）" % person)


if __name__ == "__main__":
    main()
