#!/usr/bin/env python3
"""Diff harvested surface tags against the frozen ontology.

Keeps only genuinely-new candidates:
  1. normalize + basic quality filter
  2. drop tags already present by name or alias
  3. drop tags whose embedding is >= SIM_MAX similar to an existing canonical
     entry (near-duplicates), and mark 0.85..SIM_MAX as "borderline" for review

Usage:
    python diff_candidates.py --harvested harvested_tags.json \
        --ontology ../exports/ontology_export_v1_0_0.json \
        --retrieval ../exports/retrieval_index.json \
        --faiss ../exports/retrieval_faiss.index --ids ../exports/retrieval_ids.json
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

HERE = Path(__file__).parent
MODEL = "D:/model/bge-m3/BAAI/bge-m3"
SIM_MAX = 0.90          # >= drop as duplicate
SIM_REVIEW = 0.72       # >= route to alias-review bucket (Chinese synonyms score low)
SIM_FLOOR = 0.62        # annotation only

_BLACKLIST = {
    "中文", "中国语", "中国語", "中文翻訳", "中国語翻訳", "漢化", "汉化", "翻譯", "翻译",
    "小説", "小说", "小説版", "漫画版", "漫画", "イラスト", "男性向け", "女性向け",
    "腐向け", "一般向け", "二次創作", "同人", "原创", "オリジナル", "パロディ",
    "R18", "R-18", "R18G", "R-18G", "R15", "R-15", "AI", "AI生成",
    "タグ", "複数タグ", "単タグ", "其他", "その他", "短編", "連載", "完結",
    "系列", "シリーズ", "短篇", "长篇", "连载", "完结", "合集", "番外",
    "梦小说", "原创小说", "同人小说", "色情小说", "黄色小说",
}

try:
    from zhconv import convert as _zh_convert
except Exception:  # pragma: no cover
    _zh_convert = None

# Editorial / solicitation / platform / language junk that is never a content tag
_JUNK_RE = re.compile(
    r"(接稿|约稿|求稿|征稿|私人订制|接受定制|有偿|付费|稿费|约文|定制文|"
    r"QQ|qq群|微信|加群|联系方式|催更|求评|求收藏|求关注|三连|"
    r"pixiv|P站|p站|推特|twitter|微博|爱丽丝|alice|"
    r"中文|中国语|中國語|汉语|简体|繁体|漢字|"
    r"一次創作|創作|文笔|文筆|"
    r"^高h$|^高H$|^h$|^H$|^r18|^R18|^18\+?$)"
)


def norm(t: str) -> str:
    t = unicodedata.normalize("NFKC", t).strip()
    if _zh_convert is not None:
        t = _zh_convert(t, "zh-cn")  # traditional -> simplified
    return t


def _has_kana(s: str) -> bool:
    return any("\u3040" <= c <= "\u30ff" for c in s)


def _has_han(s: str) -> bool:
    return any("\u4e00" <= c <= "\u9fff" for c in s)


# valid rare Chinese chars that fall outside GB2312 and must not be treated as JP
_GB2312_ALLOW = set("屄")


def _is_japanese(t: str) -> bool:
    """JP kanji (shinjitai) are outside GB2312 after traditional->simplified."""
    for c in t:
        try:
            c.encode("gb2312")
        except UnicodeEncodeError:
            if c not in _GB2312_ALLOW:
                return True
    return False


def keep(t: str) -> bool:
    """Target vocabulary is Chinese: Han-bearing, non-kana, non-JP, non-junk."""
    if not t or len(t) > 30 or len(t) < 2:
        return False
    if t in _BLACKLIST:
        return False
    if t.isdigit():
        return False
    if _has_kana(t):
        return False
    if not _has_han(t):
        return False
    if _is_japanese(t):
        return False
    if _JUNK_RE.search(t):
        return False
    return True


_DELIM = re.compile(r"[/／|｜,，、;；:：#＃\s]+")


def expand(counts: dict[str, int]) -> dict[str, int]:
    """Split composite tags (e.g. '调教/榨精/激烈性爱') into parts."""
    out: dict[str, int] = {}
    for raw, c in counts.items():
        for part in _DELIM.split(norm(raw)):
            part = part.strip()
            if keep(part):
                out[part] = out.get(part, 0) + c
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--harvested", default=str(HERE / "harvested_tags.json"))
    # NOTE: run this from ontology_factory/ and keep these relative — faiss on
    # Windows cannot open an absolute path containing non-ASCII (Chinese) chars.
    ap.add_argument("--ontology", default="exports/ontology_export_v1_0_0.json")
    ap.add_argument("--retrieval", default="exports/retrieval_index.json")
    ap.add_argument("--faiss", default="exports/retrieval_faiss.index")
    ap.add_argument("--ids", default="exports/retrieval_ids.json")
    ap.add_argument("--out", default=str(HERE / "candidates.json"))
    args = ap.parse_args()

    counts: dict[str, int] = json.loads(Path(args.harvested).read_text(encoding="utf-8"))
    onto = json.loads(Path(args.ontology).read_text(encoding="utf-8"))
    known = set()
    for e in onto["entries"]:
        known.add(norm(e["original_name"]))
        for a in e.get("aliases", []) or []:
            known.add(norm(a))
    print(f"[diff] harvested={len(counts)}  known names+aliases={len(known)}")

    normalized = expand(counts)
    print(f"[diff] after expand/normalize/filter (Chinese only): {len(normalized)}")

    fresh = {t: c for t, c in normalized.items() if t not in known}
    print(f"[diff] not already known by name/alias: {len(fresh)}")

    ids = json.loads(Path(args.ids).read_text(encoding="utf-8"))
    index = faiss.read_index(str(Path(args.faiss)))
    V = index.reconstruct_n(0, index.ntotal)
    V = V / np.linalg.norm(V, axis=1, keepdims=True)

    model = SentenceTransformer(MODEL)
    cands = sorted(fresh.items(), key=lambda kv: kv[1], reverse=True)
    texts = [t for t, _ in cands]
    emb = model.encode(texts, batch_size=64, normalize_embeddings=True,
                       show_progress_bar=False)
    emb = np.asarray(emb, dtype="float32")
    sims = emb @ V.T  # (n_candidates, n_existing)
    best = sims.max(axis=1)
    best_i = sims.argmax(axis=1)

    new, borderline = [], []
    for (t, c), s, bi in zip(cands, best, best_i):
        rec = {"tag": t, "count": c, "max_sim": round(float(s), 3),
               "nearest": ids[int(bi)]}
        if s >= SIM_MAX:
            continue
        if s >= SIM_REVIEW:
            borderline.append(rec)
        else:
            new.append(rec)

    Path(args.out).write_text(json.dumps(
        {"new": new, "borderline": borderline}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"[diff] NEW candidates: {len(new)} | borderline({SIM_REVIEW}-{SIM_MAX}): "
          f"{len(borderline)} -> {args.out}")


if __name__ == "__main__":
    main()
