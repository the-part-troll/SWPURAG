"""Local Chinese embeddings and rank fusion for the retrieval experiment."""

import hashlib
import json


MODEL = "shibing624/text2vec-base-chinese"
REVISION = "183bb99aa7af74355fb58d16edf8c13ae7c5433e"
MAX_TOKENS = 128
DIMENSIONS = 768
RRF_K = 60
RRF_DEPTH = 20


def model_dir(path):
    # 只使用已下载的固定快照；编码时不访问模型站点。
    if path.name != REVISION or not (path / "model.safetensors").is_file():
        raise ValueError("Use the local model snapshot directory named " + REVISION)
    return path


def digest_file(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def corpus_signature(rows):
    digest = hashlib.sha256()
    for row in rows:
        payload = [row[key] for key in ("chunk_id", "raw_sha256", "ordinal", "text")]
        digest.update(json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n")
    return digest.hexdigest()


class Encoder:
    def __init__(self, path):
        import torch
        from transformers import AutoModel, AutoTokenizer

        self.torch = torch
        torch.set_num_threads(4)
        path = model_dir(path)
        self.model = AutoModel.from_pretrained(path, local_files_only=True, use_safetensors=True).eval()
        self.tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)

    def encode(self, texts):
        tokens = self.tokenizer(texts, padding=True, truncation=True, max_length=MAX_TOKENS,
                                return_tensors="pt")
        torch = self.torch
        with torch.inference_mode():
            # 按快照配置对有效 token 做均值池化，再归一化用于余弦相似度。
            hidden = self.model(**tokens).last_hidden_state
            mask = tokens["attention_mask"].unsqueeze(-1)
            pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp_min(1)
            return torch.nn.functional.normalize(pooled, dim=1).numpy()


def build_index(rows, path, output):
    import numpy as np

    encoder = Encoder(path)
    vectors = np.concatenate([encoder.encode([row["text"] for row in rows[i:i + 16]])
                              for i in range(0, len(rows), 16)])
    metadata = {"model": MODEL, "revision": REVISION, "max_tokens": MAX_TOKENS,
                "corpus_sha256": corpus_signature(rows),
                "weights_sha256": digest_file(path / "model.safetensors")}
    # 独占写入，旧索引保留；与语料签名不匹配时必须重建。
    with output.open("xb") as target:
        np.savez_compressed(target, ids=[row["chunk_id"] for row in rows], vectors=vectors,
                            metadata=json.dumps(metadata, sort_keys=True))
    return metadata


class VectorIndex:
    def __init__(self, rows, path, index):
        import numpy as np

        with np.load(index, allow_pickle=False) as data:
            self.metadata = json.loads(str(data["metadata"]))
            ids, self.vectors = data["ids"].tolist(), data["vectors"]
        expected = {"model": MODEL, "revision": REVISION, "max_tokens": MAX_TOKENS,
                    "corpus_sha256": corpus_signature(rows),
                    "weights_sha256": digest_file(model_dir(path) / "model.safetensors")}
        if self.metadata != expected or ids != [row["chunk_id"] for row in rows]:
            raise ValueError("Index does not match the current corpus and model; rebuild it")
        if (self.vectors.shape != (len(ids), DIMENSIONS)
                or self.vectors.dtype != np.float32 or not np.isfinite(self.vectors).all()):
            raise ValueError("Invalid embedding index")
        self.positions = {chunk_id: i for i, chunk_id in enumerate(ids)}
        self.encoder = Encoder(path)

    def scorer(self):
        # 每道题单独计时、缓存；同一子问在多个预留批次出现时只编码一次。
        encoded = {}

        def rank(query, candidates, limit):
            if len(candidates) <= 1:
                return list(candidates)
            if query not in encoded:
                encoded[query] = self.encoder.encode([query])[0]
            scores = self.vectors[[self.positions[row["chunk_id"]] for row in candidates]] @ encoded[query]
            ordered = sorted(zip(candidates, scores), key=lambda entry: (-entry[1], entry[0]["chunk_id"]))
            return [dict(row, vector_score=float(score)) for row, score in ordered[:limit]]

        return rank


def fuse(lexical, vector, limit, k=RRF_K):
    rows, scores, first, lex_ranks = {}, {}, {}, {}
    for lane in (lexical, vector):
        for rank, row in enumerate(lane, 1):
            key = row["chunk_id"]
            rows.setdefault(key, row)
            scores[key] = scores.get(key, 0) + 1 / (k + rank)
            first[key] = min(rank, first.get(key, rank))
            if lane is lexical:
                lex_ranks[key] = rank
    order = sorted(scores, key=lambda key: (-scores[key], first[key], lex_ranks.get(key, float("inf")), key))
    return [dict(rows[key], rrf_score=scores[key]) for key in order[:limit]]
