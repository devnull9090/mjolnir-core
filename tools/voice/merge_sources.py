"""Pool one voice's clips from several games into one folder for make_dataset.py.

  python merge_sources.py --out <dir> <source> [<source> ...]

A source is a clip folder that has transcripts.tsv (transcribe.py), as
  name=<dir>                     every clip in it
  name=<dir>@<scores.tsv>:<min>  only clips scoring at least <min> there
                                 (speaker_filter.py's scores)
Clips are copied as <name>_<file> and their transcript rows merged into
<out>/transcripts.tsv, so the dataset step sees one folder.
"""
import argparse
import os
import shutil


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("sources", nargs="+")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    merged = ["file\tseconds\ttext\tavg_logprob\tno_speech_prob"]
    for spec in a.sources:
        name, rest = spec.split("=", 1)
        allowed = None
        if "@" in rest:
            folder, gate = rest.split("@", 1)
            scores, least = gate.rsplit(":", 1)
            allowed = set()
            for row in open(scores, encoding="utf-8").read().splitlines()[1:]:
                s, f = row.split("\t")
                if float(s) >= float(least):
                    allowed.add(f.strip())
        else:
            folder = rest
        n = seconds = 0
        for row in open(os.path.join(folder, "transcripts.tsv"), encoding="utf-8").read().splitlines()[1:]:
            cols = row.split("\t")
            if allowed is not None and cols[0] not in allowed:
                continue
            dest = f"{name}_{cols[0]}"
            if not os.path.exists(os.path.join(a.out, dest)):
                shutil.copy(os.path.join(folder, cols[0]), os.path.join(a.out, dest))
            merged.append("\t".join([dest] + cols[1:]))
            n += 1
            seconds += float(cols[1])
        print(f"{name}: {n} clips, {seconds / 60:.1f} min")
    with open(os.path.join(a.out, "transcripts.tsv"), "w", encoding="utf-8") as f:
        f.write("\n".join(merged) + "\n")


if __name__ == "__main__":
    main()
