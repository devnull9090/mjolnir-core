import { useCallback, useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { api, type Reference, type TagPeek, type TextureView } from "../lib/api";
import { buildModelGroup, disposeGeometries } from "../lib/three-model";
import { refKey, tagLabel, useEditor } from "../stores/editor-store";
import { Popover } from "./Popover";
import { SoundPlayer } from "./SoundPlayer";

/** Hover intent: long enough that sweeping the mouse across a form full of
 *  reference rows starts no decodes, short enough to feel immediate. */
const OPEN_DELAY = 350;
/** Grace period for travelling from the chip into the card. */
const CLOSE_DELAY = 150;

/** Thumbnails, cached module-wide and bounded like the store's full-size
 *  texture cache — but kept apart from it: these are 256px renders, and mixing
 *  the two would hand the viewer a blurry image or the card a huge one. */
const thumbCache = new Map<number, TextureView>();
const THUMB_CACHE_MAX = 16;

/**
 * The four-CC chip on a reference row, grown up: colour says whether the
 * reference resolves, hovering shows what is on the other end, clicking pins
 * the card open.
 */
export function RefPreview({ reference }: { reference: Reference }) {
  const key = refKey(reference.group, reference.path);
  const hit = useEditor((s) => s.refStatus[key]);
  const followReference = useEditor((s) => s.followReference);

  const chipRef = useRef<HTMLButtonElement | null>(null);
  const openTimer = useRef<number | null>(null);
  const closeTimer = useRef<number | null>(null);
  /** Ties an in-flight peek to the hover that asked for it, so a card is
   *  never drawn for a row the pointer already left. */
  const token = useRef(0);

  const [anchor, setAnchor] = useState<DOMRect | null>(null);
  const [pinned, setPinned] = useState(false);
  const [peek, setPeek] = useState<TagPeek | null>(null);
  const [peekError, setPeekError] = useState<string | null>(null);

  const clearTimers = () => {
    if (openTimer.current !== null) window.clearTimeout(openTimer.current);
    if (closeTimer.current !== null) window.clearTimeout(closeTimer.current);
    openTimer.current = null;
    closeTimer.current = null;
  };

  const close = useCallback(() => {
    clearTimers();
    token.current++;
    setAnchor(null);
    setPinned(false);
    setPeek(null);
    setPeekError(null);
  }, []);

  useEffect(() => () => close(), [close]);
  // A retargeted reference is a different preview; drop the old card.
  useEffect(() => close, [key, close]);

  const show = useCallback(() => {
    if (!hit || !chipRef.current) return;
    const mine = ++token.current;
    setAnchor(chipRef.current.getBoundingClientRect());
    setPeek(null);
    setPeekError(null);
    api
      .peekTag(hit.index)
      .then((p) => {
        if (token.current === mine) setPeek(p);
      })
      .catch((e) => {
        if (token.current === mine) setPeekError(String(e));
      });
  }, [hit]);

  const onEnter = () => {
    if (closeTimer.current !== null) {
      window.clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
    if (anchor || !hit) return;
    openTimer.current = window.setTimeout(show, OPEN_DELAY);
  };

  const onLeave = () => {
    if (openTimer.current !== null) {
      window.clearTimeout(openTimer.current);
      openTimer.current = null;
    }
    if (anchor && !pinned) {
      closeTimer.current = window.setTimeout(close, CLOSE_DELAY);
    }
  };

  const onCardHover = (over: boolean) => {
    if (over) {
      if (closeTimer.current !== null) {
        window.clearTimeout(closeTimer.current);
        closeTimer.current = null;
      }
    } else if (!pinned) {
      closeTimer.current = window.setTimeout(close, CLOSE_DELAY);
    }
  };

  const broken = hit === null;
  return (
    <>
      <button
        ref={chipRef}
        type="button"
        className={`font-mono text-[10px] ${
          broken
            ? "cursor-help text-accent-red"
            : hit
              ? "cursor-pointer text-mjolnir-gold-dim hover:text-mjolnir-gold"
              : "text-text-dim"
        }`}
        title={
          broken
            ? "This reference does not exist in this installation"
            : hit
              ? "Preview the referenced tag"
              : undefined
        }
        onPointerEnter={onEnter}
        onPointerLeave={onLeave}
        onPointerDown={(e) => e.stopPropagation()}
        onClick={() => {
          if (!hit) return;
          if (anchor && pinned) {
            close();
          } else if (anchor) {
            setPinned(true);
          } else {
            clearTimers();
            setPinned(true);
            show();
          }
        }}
      >
        {broken ? `${reference.group} · missing` : reference.group}
      </button>
      {anchor && hit && (
        <Popover anchor={anchor} onClose={close} onHoverChange={onCardHover}>
          <div className="w-72 p-2 text-xs">
            <div className="mb-1 flex items-baseline justify-between gap-2">
              <span className="truncate font-mono text-text-primary" title={hit.short}>
                {tagLabel(hit)}
              </span>
              <button
                type="button"
                className="shrink-0 cursor-pointer text-mjolnir-gold hover:brightness-110"
                onClick={() => {
                  close();
                  void followReference(reference.group, reference.path);
                }}
              >
                open
              </button>
            </div>
            <div className="mb-1 text-[10px] text-text-dim">
              {hit.group} · {Math.max(1, Math.round(hit.size / 1024)).toLocaleString()} KB
            </div>
            {peekError && <div className="text-accent-red">{peekError}</div>}
            {!peek && !peekError && <div className="text-text-dim">peeking…</div>}
            {peek?.preview === "texture" && peek.texture !== null && (
              <Thumb index={peek.texture} />
            )}
            {peek?.preview === "sound" && peek.sound !== null && (
              <SoundPlayer index={peek.sound} />
            )}
            {peek?.preview === "model" && <MiniModel index={hit.index} />}
            {peek?.preview === "summary" && (
              <div className="text-text-dim">no preview for this group — open it to read the fields</div>
            )}
          </div>
        </Popover>
      )}
    </>
  );
}

/** A 256px texture render, cached so re-hovering costs nothing. */
function Thumb({ index }: { index: number }) {
  const [view, setView] = useState<TextureView | null>(thumbCache.get(index) ?? null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (thumbCache.has(index)) {
      setView(thumbCache.get(index) ?? null);
      return;
    }
    let live = true;
    setView(null);
    setError(null);
    api
      .readTextureThumb(index, 256)
      .then((v) => {
        thumbCache.set(index, v);
        while (thumbCache.size > THUMB_CACHE_MAX) {
          const oldest = thumbCache.keys().next().value;
          if (oldest === undefined) break;
          thumbCache.delete(oldest);
        }
        if (live) setView(v);
      })
      .catch((e) => {
        // A handful of shipped textures never decode (render targets,
        // uncooked virtual payloads); the card says so instead of an image.
        if (live) setError(String(e));
      });
    return () => {
      live = false;
    };
  }, [index]);

  if (error) return <div className="text-accent-red">{error}</div>;
  if (!view) return <div className="text-text-dim">decoding…</div>;
  return (
    <div>
      <img
        src={view.png}
        alt={view.path}
        className="max-h-48 w-full border border-border-subtle object-contain"
        style={{
          backgroundImage:
            "repeating-conic-gradient(#1f2937 0% 25%, #111827 0% 50%)",
          backgroundSize: "16px 16px",
        }}
      />
      <div className="mt-1 text-[10px] text-text-dim">
        {view.width}×{view.height} · {view.format}
      </div>
    </div>
  );
}

/**
 * A small self-spinning render of a model tag's collision shell. The shell,
 * not the render model: one geometry read instead of the Blueprint chase and
 * texture streaming the Model view pays for, which is the right trade at
 * hover prices.
 */
function MiniModel({ index }: { index: number }) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const [note, setNote] = useState<string | null>("reading geometry…");

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;
    let disposed = false;

    const W = 272;
    const H = 180;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.setSize(W, H);
    mount.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.add(new THREE.HemisphereLight(0xbfc8d6, 0x33383f, 1.6));
    const sun = new THREE.DirectionalLight(0xffffff, 1.2);
    sun.position.set(3, 6, 2);
    scene.add(sun);

    const camera = new THREE.PerspectiveCamera(50, W / H, 0.001, 500);
    // Tag space is Z-up; the root's rotation maps it to three's Y-up, the
    // same convention as every other viewer here.
    const root = new THREE.Group();
    root.rotation.x = -Math.PI / 2;
    scene.add(root);
    const spinner = new THREE.Group();
    root.add(spinner);

    let frame = 0;
    const material = new THREE.MeshStandardMaterial({
      color: 0x8fa1b3,
      flatShading: true,
      side: THREE.DoubleSide,
    });

    api
      .readModelGeometry(index)
      .then((g) => {
        if (disposed) return;
        const group = buildModelGroup(g, material);
        // Centre the shell on the spin axis so it turns rather than orbits.
        const box = new THREE.Box3().setFromObject(group);
        const center = box.getCenter(new THREE.Vector3());
        const size = box.getSize(new THREE.Vector3()).length() || 1;
        group.position.sub(center);
        spinner.add(group);
        camera.position.set(size * 0.65, size * 0.4, size * 0.65);
        camera.lookAt(0, 0, 0);
        setNote(null);
        const draw = () => {
          spinner.rotation.z += 0.008;
          renderer.render(scene, camera);
          frame = requestAnimationFrame(draw);
        };
        frame = requestAnimationFrame(draw);
      })
      .catch((e) => {
        if (!disposed) setNote(String(e));
      });

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      disposeGeometries(scene);
      material.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode === mount) {
        mount.removeChild(renderer.domElement);
      }
    };
  }, [index]);

  return (
    <div className="relative" style={{ width: 272, height: 180 }}>
      <div ref={mountRef} />
      {note && (
        <div className="absolute inset-0 flex items-center justify-center p-2 text-center text-text-dim">
          {note}
        </div>
      )}
    </div>
  );
}
