"""
Generate NitiBench-compatible tax_response.json by querying a LightRAG server.

Usage:
  python lightrag_response.py \
    --dataset /path/to/hf_tax.csv \
    --output  /path/to/results/tax_response.json \
    --url     http://localhost:9621 \
    --mode    hybrid \
    --concurrency 3
"""
import argparse
import asyncio
import json
import os
import sys
import time

import httpx
import pandas as pd
from tqdm.asyncio import tqdm as atqdm


async def query_lightrag(
    client: httpx.AsyncClient, question: str, mode: str, sem: asyncio.Semaphore
) -> str:
    async with sem:
        resp = await client.post(
            "/query",
            json={"query": question, "mode": mode},
            timeout=120.0,
        )
        resp.raise_for_status()
        return resp.json().get("response", "")


async def main(args):
    df = pd.read_csv(args.dataset, encoding="utf-8-sig")

    q_col = next(
        (c for c in ["question", "ข้อหารือ"] if c in df.columns), df.columns[0]
    )
    print(f"Using question column: '{q_col}' — {len(df)} questions")

    df["idx"] = [f"{i:04d}" for i in range(len(df))]

    if args.limit and args.limit > 0:
        df_query = df.head(args.limit)
        df_skip = df.iloc[args.limit:]
        print(f"Limiting queries to first {args.limit} / {len(df)} questions")
    else:
        df_query = df
        df_skip = df.iloc[0:0]

    sem = asyncio.Semaphore(args.concurrency)

    async with httpx.AsyncClient(base_url=args.url, timeout=120.0) as client:
        try:
            health = await client.get("/health")
            health.raise_for_status()
            cfg = health.json().get("configuration", {})
            print(
                f"LightRAG healthy — llm: {cfg.get('llm_model')}, "
                f"embedding: {cfg.get('embedding_model')}"
            )
        except Exception as e:
            print(f"Health check failed: {e}")
            sys.exit(1)

        async def run_one(idx: str, question: str) -> dict:
            start = time.time()
            try:
                answer = await query_lightrag(client, question, args.mode, sem)
                return {
                    "idx": idx,
                    "content": {"answer": answer, "citations": []},
                    "retrieved_ids": [],
                    "usage": {"elapsed_seconds": round(time.time() - start, 2)},
                    "tries": 1,
                }
            except Exception as e:
                print(f"  [idx={idx}] ERROR: {e}")
                return {
                    "idx": idx,
                    "content": {"answer": "", "citations": []},
                    "retrieved_ids": [],
                    "usage": {"error": str(e)},
                    "tries": 1,
                }

        tasks = [run_one(row["idx"], row[q_col]) for _, row in df_query.iterrows()]
        results = await atqdm.gather(*tasks, desc="Querying LightRAG")

    # Pad skipped rows with empty answers so metric_e2e gets a full-length file
    skipped = [
        {"idx": row["idx"], "content": {"answer": "", "citations": []}, "retrieved_ids": [], "usage": {"skipped": True}, "tries": 0}
        for _, row in df_skip.iterrows()
    ]
    results = list(results) + skipped

    results.sort(key=lambda x: x["idx"])

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    errors = sum(1 for r in results if "error" in r["usage"])
    print(f"\nDone — {len(results) - errors}/{len(results)} succeeded → {args.output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="/app/test_data/hf_tax.csv")
    parser.add_argument("--output", default="/app/results/tax_response.json")
    parser.add_argument(
        "--url", default=os.environ.get("LIGHTRAG_URL", "http://localhost:9621")
    )
    parser.add_argument(
        "--mode",
        default="hybrid",
        choices=["local", "global", "hybrid", "naive", "mix"],
    )
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--limit", type=int, default=0, help="cap number of questions (0 = all)")
    args = parser.parse_args()
    asyncio.run(main(args))
