#!/usr/bin/env bash
set -e
cd ~/threes-ai
go build -o bin/bench ./cmd/bench
for d in 3 4 5; do
  ./bin/bench -agent ntuple-search -model models/ntuple_big.gob \
    -deckaware -depthcap $d -n 1000 -seqsearch -workers $(nproc) \
    -label ntsearch-big-d$d -log docs/runs/ntsearch_big.jsonl
  ./bin/bench -agent expectimax \
    -deckaware -depthcap $d -n 1000 -seqsearch -workers $(nproc) \
    -label expectimax-d$d   -log docs/runs/ntsearch_big.jsonl
done
echo "ALL DONE"   # 跑完的标志，方便 grep
