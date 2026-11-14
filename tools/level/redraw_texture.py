"""Redraw one small texture with an image model, for a remaster.

    python tools/level/redraw_texture.py <source image> <out.png>
        --what "a worn metal safety sign" [--text "NOTICE / ENTRANCE FOR / EMPLOYEES / ONLY"]
        [--size 1024] [--model gpt-image-2.6-sunburst] [--quality high] [--keep-raw]

An upscaler can only sharpen what is there, and a 64 by 32 sign holds no
letter shapes: Real-ESRGAN, tried on a whole map's textures, invented blobs
for letters and was dropped. A texture is enlarged only on purpose, one at
a time, with someone saying what it shows: write the result to
`<work>/redrawn/<asset name>.png` and a map with `"redrawn": true` builds
with it (upgrade_ce_map.py). This sends
the texture, magnified, to OpenAI's image edit endpoint with a prompt that
says what it is and what it reads, and asks for the same picture drawn
again: same layout, colours and proportions, front on, filling the frame.

The result is scaled to `--size` on its long side at the source's aspect.
The source's own alpha is kept (magnified and smoothed), so a cut-out
keeps its outline whatever the model drew outside it.

A bump map is redrawn the same way with `--normal-map` (the model keeps
the encoding and the way each slope faces) and then finished with
redraw_bump.py, which makes the picture a normal map again.

The key is read from OPENAI_API_KEY, or from `.env.local` / `.env` at the
repository root (both ignored by git). It is never written anywhere.
The source image leaves this machine: use it on textures you may send.
"""
import argparse
import base64
import io
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
URL = "https://api.openai.com/v1/images/edits"
PROMPT = (
    "This image is a tiny, heavily magnified video game texture of {what}. "
    "Redraw exactly this picture at high resolution: the same layout, the same colours, the same proportions, "
    "every element in the same place. {text}"
    "Flat and front on, with no perspective, no frame, no background, no shadow and no added border: "
    "the picture fills the whole image edge to edge as the input does. "
    "{wear}"
)
NORMAL_MAP = (
    "This image is a tiny, heavily magnified tangent-space normal map from a video game, the purple-blue relief "
    "encoding game engines use: flat areas are RGB 128,128,255, a slope facing right is redder, a slope facing "
    "left is less red, and green encodes slopes facing up or down. It is the relief for {what}. "
    "Redraw exactly this normal map at high resolution: the same layout, every shape in the same place, "
    "the same colour encoding and the same direction of every slope, flat areas the same flat purple-blue, "
    "filling the whole image edge to edge. Make every bevel clean, sharp and evenly wide, as if baked from a "
    "high-resolution sculpt. Add no lighting, no shadows, no texture grain and no new shapes."
)
WEAR = "Crisp edges and clean lettering, lightly worn like a painted sign that has been outdoors, not new and not grimy."


def api_key():
    key = os.environ.get("OPENAI_API_KEY")
    for name in (".env.local", ".env"):
        path = os.path.join(REPO, name)
        if not key and os.path.isfile(path):
            for line in open(path, encoding="utf-8"):
                if line.strip().startswith("OPENAI_API_KEY="):
                    key = line.strip().split("=", 1)[1].strip().strip('"')
    if not key:
        sys.exit("no key: set OPENAI_API_KEY or put OPENAI_API_KEY=... in .env.local")
    return key


def request_size(w, h):
    """The size asked of the model: the source's aspect (held to the API's
    1:3 to 3:1), both edges multiples of 16, about 1.2 million pixels."""
    aspect = min(max(w / h, 1 / 3), 3.0)
    height = (1_200_000 / aspect) ** 0.5
    return max(16, round(height * aspect / 16) * 16), max(16, round(height / 16) * 16)


def multipart(fields, files):
    boundary = uuid.uuid4().hex
    body = io.BytesIO()
    for name, value in fields.items():
        body.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    for name, (filename, data, mime) in files.items():
        body.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                   f"Content-Type: {mime}\r\n\r\n".encode())
        body.write(data)
        body.write(b"\r\n")
    body.write(f"--{boundary}--\r\n".encode())
    return body.getvalue(), f"multipart/form-data; boundary={boundary}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("source")
    ap.add_argument("out")
    ap.add_argument("--what", required=True, help="what the texture shows, in a few words")
    ap.add_argument("--text", help="what it reads, lines separated by ' / '")
    ap.add_argument("--size", type=int, default=1024, help="the output's long side")
    ap.add_argument("--model", default="gpt-image-2.6-sunburst")
    ap.add_argument("--quality", default="high")
    ap.add_argument("--alpha", choices=("cutout", "smooth"), default="cutout",
                    help="the source's alpha is a cut-out's outline (cut back to a clean edge), or a mask with "
                         "levels of its own, such as a specular mask (magnified as it is)")
    ap.add_argument("--normal-map", action="store_true",
                    help="the source is a bump (normal) map: redraw it as one. Finish the result with "
                         "redraw_bump.py before using it")
    ap.add_argument("--prompt", help="replace the closing sentence about wear (the default suits a painted sign)")
    ap.add_argument("--tile", action="store_true",
                    help="the texture repeats both ways (a surface's grain): the redraw is made to wrap by "
                         "blending it with itself shifted half a tile, the shifted copy at the edges")
    ap.add_argument("--tile-v", action="store_true",
                    help="the texture repeats top to bottom on its models: it is sent twice, one copy above the "
                         "other, and the two copies drawn back are blended so the result tiles")
    ap.add_argument("--keep-raw", action="store_true", help="also write the model's own image beside the output")
    a = ap.parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    src = Image.open(a.source).convert("RGBA")
    w, h = src.size
    # `--tile-v`: two copies, one above the other, so the model draws the
    # join between them; its two copies are blended back into one below.
    reps = 2 if a.tile_v else 1
    rw, rh = request_size(w, h * reps)
    # Opaque for the model: the colour under a transparent texel is whatever
    # the artist left there, usually the sign's own.
    base = src.convert("RGB")
    if reps > 1:
        stacked = Image.new("RGB", (w, h * reps))
        for k in range(reps):
            stacked.paste(base, (0, h * k))
        base = stacked
    sent = base.resize((rw, rh), Image.LANCZOS)
    buf = io.BytesIO()
    sent.save(buf, "PNG")
    text = ""
    if a.text:
        lines = [t.strip() for t in a.text.split("/") if t.strip()]
        text = "It reads, line by line: " + "; ".join(f'"{t}"' for t in lines) + ". Spell it exactly so. "
    prompt = NORMAL_MAP.format(what=a.what) if a.normal_map else PROMPT.format(what=a.what, text=text,
                                                                                wear=a.prompt or WEAR)
    if reps > 1:
        prompt += (" The input is one texture repeated twice, one copy above the other, because the texture repeats "
                   "endlessly upward and downward: keep the two copies identical, every stripe and edge continuing "
                   "straight across the join between them and across the top and bottom edges.")
    body, ctype = multipart({"model": a.model, "prompt": prompt, "size": f"{rw}x{rh}", "quality": a.quality,
                             "n": "1", "output_format": "png"},
                            {"image": ("texture.png", buf.getvalue(), "image/png")})
    req = urllib.request.Request(URL, data=body, headers={"Authorization": "Bearer " + api_key(),
                                                          "Content-Type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            reply = json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"{e.code}: {e.read().decode(errors='replace')[:600]}")
    raw = Image.open(io.BytesIO(base64.b64decode(reply["data"][0]["b64_json"]))).convert("RGB")
    if a.keep_raw:
        raw.save(os.path.splitext(a.out)[0] + ".raw.png")
    scale = a.size / max(w, h)
    ow, oh = max(4, round(w * scale / 4) * 4), max(4, round(h * scale / 4) * 4)
    if reps > 1:
        # The bottom copy runs on from the top one's last row, so blending
        # from it (at the top) into the top copy (at the bottom) gives a
        # texture whose last row runs into its first.
        both = np.asarray(raw.resize((ow, oh * 2), Image.LANCZOS)).astype(np.float64)
        top, bottom = both[:oh], both[oh:]
        t = np.linspace(0.0, 1.0, oh)[:, None, None]
        t = t * t * (3 - 2 * t)
        out = Image.fromarray(np.clip(bottom * (1 - t) + top * t + 0.5, 0, 255).astype(np.uint8)).convert("RGBA")
        print(f"tile-v: the two copies differ by {np.abs(top - bottom).mean():.1f} levels on average")
    else:
        out = raw.resize((ow, oh), Image.LANCZOS).convert("RGBA")
    if a.tile:
        # The copy shifted half a tile has its seams in the middle and wraps
        # at the edges: it takes over towards the edges, the redraw keeps
        # the middle. A grain texture hides the blend; a layout would not.
        img = np.asarray(out.convert("RGB")).astype(np.float64)
        shifted = np.roll(np.roll(img, oh // 2, 0), ow // 2, 1)
        y = np.abs(np.linspace(-1.0, 1.0, oh))[:, None]
        x = np.abs(np.linspace(-1.0, 1.0, ow))[None, :]
        m = np.clip((np.maximum(x, y) - 0.45) / 0.45, 0.0, 1.0)
        m = (m * m * (3 - 2 * m))[..., None]
        out = Image.fromarray(np.clip(img * (1 - m) + shifted * m + 0.5, 0, 255).astype(np.uint8)).convert("RGBA")
        e = np.asarray(out.convert("L")).astype(np.float64)
        print(f"tile: edge steps {np.abs(e[0] - e[-1]).mean():.1f} (rows) {np.abs(e[:, 0] - e[:, -1]).mean():.1f} (columns)"
              f" against {np.abs(np.diff(e, axis=0)).mean():.1f} between neighbours")
    alpha = src.getchannel("A")
    if alpha.getextrema() != (255, 255):
        # The source's outline, magnified: smoothed, then cut back to a
        # clean edge so 64 texels of stair steps do not show.
        big = alpha.resize((ow, oh), Image.BICUBIC).filter(ImageFilter.GaussianBlur(scale * 0.5))
        if a.alpha == "smooth":
            big = alpha.resize((ow, oh), Image.BICUBIC)
        else:
            big = big.point(lambda v: 0 if v < 96 else 255 if v > 160 else int((v - 96) * 255 / 64))
        out.putalpha(big)
    out.save(a.out)
    usage = reply.get("usage") or {}
    print(f"{os.path.basename(a.source)}: {w}x{h} -> {ow}x{oh} ({a.model}, {a.quality}; asked {rw}x{rh}"
          + (f", {usage.get('total_tokens')} tokens" if usage.get("total_tokens") else "") + ")")


if __name__ == "__main__":
    main()
