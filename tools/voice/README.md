# Voice pipeline (Pelican Warfare's Cortana and announcer)

Local voice models trained on the games' own dialogue, used to speak lines the
games never recorded. **Generated audio, training data and model weights never
go in the repository or a release without the owner's say-so.** The scripts
here are tooling only. Everything they produce stays under `D:/hce-voice`, the
local voice workspace, or under `out/` (gitignored).

## 1. Collect a voice

| Source | Tool | Notes |
|---|---|---|
| Campaign Evolved | `apps/tag-editor/src-tauri/examples/export_tag_audio.rs` | sound tags by name (`_cortana-sound`); picks the English(US) media |
| MCC Halo 3 / Reach | `fsb_clips.py extract <bank.fsb> --match <regex>` | the `.info` beside the bank names every clip |
| MCC Halo 1 | `fsb_clips.py` (FSB5 name table) | Cortana is `*_Cortana` and `cor*` |
| MCC Halo 4 | `akpk_wems.py <english(us)/soundstream.pck>` | no names: find the speaker with `speaker_filter.py` |
| Any unnamed pile | `speaker_filter.py <pile> --known <clips>` | score histogram first, then `--threshold` |

Then:
- transcribe: `transcribe.py <dir>` (faster-whisper large-v3);
- pool sources: `merge_sources.py`;
- build the training set: `make_dataset.py`.

## 2. Train

Qwen3-TTS 1.7B Base, fine-tuned with `D:/hce-voice/train/qwen3/run_voice.sh
<dataset> <out> <speaker> <epochs>`. That folder's `sft_12hz.py` is upstream's
`finetuning/sft_12hz.py` (Qwen3-TTS 022e286) with `qwen3_sft_fixes.patch`
applied. The patch fixes four layout bugs in the upstream recipe:
- the text projection;
- two double-shifted losses;
- the sub-talker's hidden-state position.

Render with language `Auto` (`say_qwen3.py` does), or the speaker slot moves.

Check a model before trusting it:
- **words:** `transcribe.py` on its renders;
- **likeness:** `similarity.py` against held-out real clips.

The first checkpoint is often the best one. Pooling Cortana's four eras made
her worse; the announcer's three games pooled well.

## 3. Render the lines

`warfare_lines.txt` holds `voice <TAB> name <TAB> text [<TAB> delivery]`.
Names end in a letter, never `_<digits>`: the game does not load such waves.

```
python say_qwen3.py --voice ai --lines warfare_lines.txt --takes 8 --model <ckpt> --speaker cortana --out <takes>
python transcribe.py <takes>
python pick_takes.py <takes> --lines warfare_lines.txt --voice ai --real <real clips> --final <waves> --prefix cortana
python voice_catalog.py <waves>/manifest.tsv     # writes mods/MJOLNIRHud/Scripts/warfare_voice_lines.lua
```

`pick_takes.py` decides which take wins:
- A take must say the right words.
- It must not run on: at most 1.5 times the median length of the word-perfect takes.
- Calm lines then rank by likeness to the real voice, shouted ones by loudness.
- The winner is trimmed and its level evened out.

## 4. Into the game

```
set MJ_VOICE_DIR=<waves>
UnrealEditor-Cmd.exe unreal/MJOLNIRMaterials/Meteorite.uproject -run=pythonscript -script=Scripts/build_warfare_voice.py
powershell -File tools/ue/cook.ps1
```

The cook stages `pakchunk950-Windows.*`; install it as `pakchunk950-MJOLNIRVOICE*_P`.

Why chunk 950: a container's id is CityHash64 of its cooked name, and hub
maps already use several numbers. No installed container shares 950's id,
though whether a shared id matters is unproven (`build_warfare_voice.py`).

`mods/MJOLNIRHud/Scripts/warfare_voice.lua` decides from the warfare snapshot
what is said and when. It stays silent when the container is not installed.
