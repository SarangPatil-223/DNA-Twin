import { Link } from "react-router-dom";
import { useLocation } from "react-router-dom";
import { useWorkspace } from "@/lib/workspace";

const LINKS = [
  ["/", "Home"],
  ["/upload", "Upload"],
  ["/encoding", "Encode"],
  ["/sequences", "Sequences"],
  ["/twin", "Digital twin"],
  ["/retrieval", "Retrieve"],
  ["/compare", "Compare"],
  ["/ask", "Ask the data"],
  ["/recommend", "Recommend"],
  ["/images", "Image lab"],
  ["/research", "Research"],
  ["/reports", "Reports"],
  ["/settings", "Settings"],
];

export function Helix({ size = 28 }) {
  const rungs = ["#2E9E5B", "#C43D3D", "#7A5CC9", "#B8802F", "#2E9E5B", "#C43D3D"];
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <path d="M8 2 C 24 10, 8 22, 24 30" stroke="#14171C" strokeWidth="2.6" fill="none" strokeLinecap="round" />
      <path d="M24 2 C 8 10, 24 22, 8 30" stroke="#14171C" strokeWidth="2.6" fill="none" strokeLinecap="round" />
      {rungs.map((c, i) => {
        const y = 5 + i * 4.4;
        const w = Math.abs(Math.cos((y / 32) * Math.PI * 2)) * 11 + 1;
        return <line key={i} x1={16 - w} x2={16 + w} y1={y} y2={y} stroke={c} strokeWidth="2.2" strokeLinecap="round" />;
      })}
    </svg>
  );
}

export function Nav() {
  const path = useLocation().pathname;
  const { file } = useWorkspace();
  return (
    <header className="sticky top-0 z-40 border-b-[1.5px] border-ink bg-paper">
      <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3">
        <Link to="/" className="flex shrink-0 items-center gap-2 text-ink no-underline">
          <Helix />
          <span className="font-display text-lg uppercase">DNA Twin</span>
        </Link>
        {file && (
          <Link
            to="/upload"
            className="hidden max-w-[260px] truncate rounded-full border-[1.5px] border-ink bg-white px-3 py-1 font-mono text-[11px] text-ink no-underline md:block"
            title="Current file"
          >
            {file.filename}
          </Link>
        )}
      </div>
      <nav aria-label="Main" className="mx-auto max-w-6xl overflow-x-auto px-4 pb-3">
        <ul className="flex gap-2 whitespace-nowrap lg:flex-wrap">
          {LINKS.map(([href, label]) => {
            const active = href === "/" ? path === "/" : path.startsWith(href);
            return (
              <li key={href}>
                <Link
                  to={href}
                  aria-current={active ? "page" : undefined}
                  className={`block rounded-full border-[1.5px] border-ink px-3.5 py-1.5 font-mono text-[11px] uppercase tracking-[0.06em] no-underline transition-colors ${active ? "bg-ink text-paper" : "text-ink hover:bg-white"}`}
                >
                  {label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </header>
  );
}
