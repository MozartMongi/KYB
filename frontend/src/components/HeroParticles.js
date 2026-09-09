import { useEffect, useRef } from "react";

const DENSITY = 1 / 14000; // particles per CSS pixel of hero area
const MAX_PARTICLES = 90;
const LINK_DISTANCE = 130;
const POINTER_DISTANCE = 170;

function createParticle(width, height) {
  return {
    x: Math.random() * width,
    y: Math.random() * height,
    vx: (Math.random() - 0.5) * 0.28,
    vy: (Math.random() - 0.5) * 0.28,
    r: 1 + Math.random() * 1.6,
  };
}

/**
 * Floating dot field with proximity links, drawn on a canvas sized to its
 * parent. The parent needs `position: relative`; this layer fills it.
 */
export default function HeroParticles({ className = "" }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const parent = canvas.parentElement;
    const ctx = canvas.getContext("2d");
    if (!ctx || !parent) return undefined;

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let particles = [];
    let width = 0;
    let height = 0;
    let frame = null;
    let visible = true;
    const pointer = { x: -Infinity, y: -Infinity };

    const resize = () => {
      const rect = parent.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = rect.width;
      height = rect.height;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      const target = Math.min(MAX_PARTICLES, Math.round(width * height * DENSITY));
      if (particles.length > target) {
        particles.length = target;
      } else {
        while (particles.length < target) particles.push(createParticle(width, height));
      }
    };

    const draw = () => {
      ctx.clearRect(0, 0, width, height);

      for (let i = 0; i < particles.length; i += 1) {
        const p = particles[i];

        for (let j = i + 1; j < particles.length; j += 1) {
          const q = particles[j];
          const dx = p.x - q.x;
          const dy = p.y - q.y;
          const dist = Math.hypot(dx, dy);
          if (dist >= LINK_DISTANCE) continue;
          ctx.strokeStyle = `rgba(37, 99, 235, ${0.16 * (1 - dist / LINK_DISTANCE)})`;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(q.x, q.y);
          ctx.stroke();
        }

        const pdx = p.x - pointer.x;
        const pdy = p.y - pointer.y;
        const pDist = Math.hypot(pdx, pdy);
        if (pDist < POINTER_DISTANCE) {
          ctx.strokeStyle = `rgba(37, 99, 235, ${0.3 * (1 - pDist / POINTER_DISTANCE)})`;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(pointer.x, pointer.y);
          ctx.stroke();
        }

        ctx.fillStyle = "rgba(37, 99, 235, 0.45)";
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();
      }
    };

    const step = () => {
      for (const p of particles) {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < -p.r) p.x = width + p.r;
        else if (p.x > width + p.r) p.x = -p.r;
        if (p.y < -p.r) p.y = height + p.r;
        else if (p.y > height + p.r) p.y = -p.r;
      }
      draw();
      frame = window.requestAnimationFrame(step);
    };

    const stop = () => {
      if (frame !== null) {
        window.cancelAnimationFrame(frame);
        frame = null;
      }
    };

    const start = () => {
      if (frame !== null || !visible) return;
      if (reduceMotion.matches) {
        draw();
        return;
      }
      frame = window.requestAnimationFrame(step);
    };

    const restart = () => {
      stop();
      start();
    };

    const onPointerMove = (e) => {
      const rect = parent.getBoundingClientRect();
      pointer.x = e.clientX - rect.left;
      pointer.y = e.clientY - rect.top;
    };
    const onPointerLeave = () => {
      pointer.x = -Infinity;
      pointer.y = -Infinity;
    };
    const onVisibility = () => {
      if (document.hidden) stop();
      else start();
    };

    resize();
    start();

    const resizeObserver = new ResizeObserver(() => {
      resize();
      if (frame === null) draw();
    });
    resizeObserver.observe(parent);

    // Skip work while the hero is scrolled out of view.
    const intersectionObserver = new IntersectionObserver(
      ([entry]) => {
        visible = entry.isIntersecting;
        if (visible) start();
        else stop();
      },
      { threshold: 0 }
    );
    intersectionObserver.observe(parent);

    parent.addEventListener("pointermove", onPointerMove);
    parent.addEventListener("pointerleave", onPointerLeave);
    document.addEventListener("visibilitychange", onVisibility);
    reduceMotion.addEventListener("change", restart);

    return () => {
      stop();
      resizeObserver.disconnect();
      intersectionObserver.disconnect();
      parent.removeEventListener("pointermove", onPointerMove);
      parent.removeEventListener("pointerleave", onPointerLeave);
      document.removeEventListener("visibilitychange", onVisibility);
      reduceMotion.removeEventListener("change", restart);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className={`pointer-events-none absolute inset-0 w-full h-full ${className}`}
    />
  );
}
