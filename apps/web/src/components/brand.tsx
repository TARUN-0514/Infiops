export function Brand({ size = "md" }: { size?: "md" | "lg" }) {
  const box = size === "lg" ? "size-10" : "size-8";
  return (
    <div className="flex items-center gap-2.5">
      <svg viewBox="0 0 512 512" className={box} aria-hidden>
        <rect width="512" height="512" rx="112" className="fill-raised" />
        <circle cx="256" cy="256" r="150" fill="none" strokeWidth="28" className="stroke-accent" />
        <circle cx="256" cy="256" r="54" className="fill-accent" />
      </svg>
      <span className={size === "lg" ? "text-xl font-semibold tracking-wide" : "font-semibold tracking-wide"}>NEXUS</span>
    </div>
  );
}
