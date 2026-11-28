"use client";

import { useEffect, useRef, useState, type CSSProperties, type PointerEvent, type ReactNode } from "react";

/**
 * Progressive scroll-triggered reveal.
 *
 * Elements already inside the viewport on mount stay visible immediately so
 * above-the-fold content and SSR HTML never flash blank. Anything below the
 * fold gently rises into view once it crosses the observer threshold.
 */
export function Reveal({
  children,
  delay = 0,
  className = "",
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      el.dataset.state = "visible";
      return;
    }
    const rect = el.getBoundingClientRect();
    if (rect.top <= window.innerHeight * 0.94) {
      el.dataset.state = "visible";
      return;
    }
    el.dataset.state = "hidden";
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          el.dataset.state = "visible";
          observer.disconnect();
        }
      },
      { rootMargin: "0px 0px -40px 0px", threshold: 0.06 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      style={delay ? ({ "--reveal-delay": `${delay}ms` } as CSSProperties) : undefined}
      className={`mj-reveal ${className}`}
    >
      {children}
    </div>
  );
}

/**
 * Surface card with a pointer-tracked warm gold radial sheen.
 * Updates CSS variables inside requestAnimationFrame to stay 60/120fps smooth.
 */
export function SpotlightCard({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const raf = useRef<number>(0);

  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (e.pointerType !== "mouse") return;
    const el = ref.current;
    if (!el) return;
    const { clientX, clientY } = e;
    if (raf.current) cancelAnimationFrame(raf.current);
    raf.current = requestAnimationFrame(() => {
      const rect = el.getBoundingClientRect();
      el.style.setProperty("--mx", `${Math.round(clientX - rect.left)}px`);
      el.style.setProperty("--my", `${Math.round(clientY - rect.top)}px`);
    });
  };

  useEffect(() => () => {
    if (raf.current) cancelAnimationFrame(raf.current);
  }, []);

  return (
    <div ref={ref} onPointerMove={onPointerMove} className={`mj-spotlight ${className}`}>
      {children}
    </div>
  );
}

/**
 * Animated count-up numeral that activates once visible.
 * Renders the final value on SSR and for reduced-motion preferences.
 */
export function CountUp({
  value,
  suffix = "",
  prefix = "",
  className = "",
}: {
  value: number;
  suffix?: string;
  prefix?: string;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const [shown, setShown] = useState(value);
  const ran = useRef(false);

  useEffect(() => {
    const el = ref.current;
    if (!el || ran.current || value <= 1) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const animate = () => {
      if (ran.current) return;
      ran.current = true;
      const start = performance.now();
      const duration = Math.min(950, Math.max(480, Math.log10(value + 1) * 320));
      const tick = (now: number) => {
        const t = Math.min(1, (now - start) / duration);
        // Ease-out quartic deceleration
        const eased = 1 - Math.pow(1 - t, 4);
        setShown(Math.round(value * eased));
        if (t < 1) requestAnimationFrame(tick);
      };
      setShown(0);
      requestAnimationFrame(tick);
    };

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          animate();
          observer.disconnect();
        }
      },
      { threshold: 0.25 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [value]);

  return (
    <span ref={ref} className={`tabular-nums ${className}`}>
      {prefix}
      {shown.toLocaleString("en-US")}
      {suffix}
    </span>
  );
}

/**
 * Subtle pointer-reactive parallax container for the hero visor reticle.
 * Sets `--px` and `--py` (-1..1) on desktop mouse movement only.
 */
export function HeroParallax({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLElement>(null);
  const raf = useRef<number>(0);

  const onPointerMove = (e: PointerEvent<HTMLElement>) => {
    if (e.pointerType !== "mouse") return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const el = ref.current;
    if (!el) return;
    const { clientX, clientY } = e;
    if (raf.current) cancelAnimationFrame(raf.current);
    raf.current = requestAnimationFrame(() => {
      const rect = el.getBoundingClientRect();
      const px = ((clientX - rect.left) / Math.max(1, rect.width) - 0.5) * 2;
      const py = ((clientY - rect.top) / Math.max(1, rect.height) - 0.5) * 2;
      el.style.setProperty("--px", px.toFixed(3));
      el.style.setProperty("--py", py.toFixed(3));
    });
  };

  const onPointerLeave = () => {
    const el = ref.current;
    if (!el) return;
    el.style.setProperty("--px", "0");
    el.style.setProperty("--py", "0");
  };

  useEffect(() => () => {
    if (raf.current) cancelAnimationFrame(raf.current);
  }, []);

  return (
    <section
      ref={ref}
      onPointerMove={onPointerMove}
      onPointerLeave={onPointerLeave}
      className={className}
    >
      {children}
    </section>
  );
}
