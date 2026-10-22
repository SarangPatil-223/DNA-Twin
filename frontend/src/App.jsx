import { lazy, Suspense, useEffect } from "react";
import { Route, Routes, useLocation } from "react-router-dom";
import { Nav } from "@/components/Nav";
import { Empty, Spinner } from "@/components/ui";
import { WorkspaceProvider } from "@/lib/workspace";

// each page loads on first visit, so charts are only downloaded where they are used
const Ask = lazy(() => import("@/pages/Ask"));
const Compare = lazy(() => import("@/pages/Compare"));
const Encoding = lazy(() => import("@/pages/Encoding"));
const Home = lazy(() => import("@/pages/Home"));
const Images = lazy(() => import("@/pages/Images"));
const Recommend = lazy(() => import("@/pages/Recommend"));
const Reports = lazy(() => import("@/pages/Reports"));
const Research = lazy(() => import("@/pages/Research"));
const Retrieval = lazy(() => import("@/pages/Retrieval"));
const Sequences = lazy(() => import("@/pages/Sequences"));
const Settings = lazy(() => import("@/pages/Settings"));
const Twin = lazy(() => import("@/pages/Twin"));
const Upload = lazy(() => import("@/pages/Upload"));

const TITLES = {
  "/": "DNA Twin",
  "/upload": "Upload",
  "/encoding": "Encode",
  "/sequences": "Sequences",
  "/twin": "Digital twin",
  "/retrieval": "Retrieve",
  "/compare": "Compare",
  "/ask": "Ask the data",
  "/recommend": "Recommend",
  "/images": "Image lab",
  "/research": "Research",
  "/reports": "Reports",
  "/settings": "Settings",
};

function PageEffects() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    document.title = pathname === "/" ? "DNA Twin" : `${TITLES[pathname] ?? "Not found"} · DNA Twin`;
    if (!hash) window.scrollTo(0, 0);
  }, [pathname, hash]);
  return null;
}

export default function App() {
  return (
    <WorkspaceProvider>
      <PageEffects />
      <Nav />
      <main className="mx-auto max-w-6xl px-4 pb-24 pt-8">
        <Suspense fallback={<Spinner label="Loading" />}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/upload" element={<Upload />} />
            <Route path="/encoding" element={<Encoding />} />
            <Route path="/sequences" element={<Sequences />} />
            <Route path="/twin" element={<Twin />} />
            <Route path="/retrieval" element={<Retrieval />} />
            <Route path="/compare" element={<Compare />} />
            <Route path="/ask" element={<Ask />} />
            <Route path="/recommend" element={<Recommend />} />
            <Route path="/images" element={<Images />} />
            <Route path="/research" element={<Research />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Empty title="This page doesn't exist" href="/" cta="Go home" />} />
          </Routes>
        </Suspense>
      </main>
      <footer className="border-t-[1.5px] border-ink py-8 text-center font-mono text-[11px] text-soft">
        DNA Twin is a software simulation. No DNA is synthesized or sequenced, and no result here is biologically validated.
      </footer>
    </WorkspaceProvider>
  );
}
