import Image from "next/image";
import Link from "next/link";
import {
  Upload,
  MessageSquare,
  Lock,
  Server,
  Search,
  CheckCircle2,
  LucideIcon,
} from "lucide-react";

/* ---------------- Feature Card ---------------- */

function FeatureCard({
  title,
  description,
  icon: Icon,
}: {
  title: string;
  description: string;
  icon: LucideIcon;
}) {
  return (
    <div className="bg-white rounded-xl p-6 border border-slate-200 shadow-sm">
      <div className="w-10 h-10 rounded-md bg-slate-100 flex items-center justify-center mb-4">
        <Icon className="w-5 h-5 text-slate-700" />
      </div>
      <h4 className="text-lg font-semibold text-slate-900">{title}</h4>
      <p className="mt-2 text-sm text-slate-600 leading-relaxed">
        {description}
      </p>
    </div>
  );
}

/* ---------------- Institutional Header ---------------- */

function Header() {
  return (
    <header className="sticky top-0 z-50">
      {/* Light gray/blue top section */}
      <div className="bg-slate-100">
        {/* White content section with curved top-left */}
        <div className="bg-white rounded-tl-[100px]">
          <div className="mx-auto max-w-7xl px-6 h-20 flex items-center justify-between">
            {/* Left: Logos */}
            <div className="flex items-center gap-6">
              {/* IIIT Dharwad */}
              <div className="flex items-center gap-3">
                <Image
                  src="/iiitdwd.jpeg"
                  alt="IIIT Dharwad"
                  width={44}
                  height={44}
                  priority
                />
                <div className="leading-tight">
                  <p className="text-sm font-semibold text-slate-900">
                    IIIT Dharwad
                  </p>
                  <p className="text-xs text-slate-500">
                    Institute of National Importance
                  </p>
                </div>
              </div>

              <div className="h-10 w-px bg-slate-300" />

              {/* HAL */}
              <div className="flex items-center gap-3">
                <Image
                  src="/hal.jpeg"
                  alt="Hindustan Aeronautics Limited"
                  width={56}
                  height={44}
                  priority
                />
                <div className="leading-tight">
                  <p className="text-sm font-semibold text-slate-900">
                    Hindustan Aeronautics Ltd.
                  </p>
                  <p className="text-xs text-slate-500">
                    A Maharatna CPSE
                  </p>
                </div>
              </div>
            </div>

            {/* Right: Login only */}
            <Link
              href="/login"
              className="h-10 px-5 inline-flex items-center rounded-md border border-slate-300 text-sm font-medium text-slate-700 hover:bg-slate-100 transition"
            >
              Login
            </Link>
          </div>
        </div>
      </div>
      
      {/* Blue navigation bar */}
      <div className="bg-blue-900 h-12"></div>
    </header>
  );
}

/* ---------------- Data ---------------- */

const features = [
  {
    title: "Document Upload & Indexing",
    description:
      "Supports PDF, DOCX, and TXT files. Documents are preprocessed and indexed locally using AI embeddings.",
    icon: Upload,
  },
  {
    title: "Offline RAG Pipeline",
    description:
      "Retriever–Generator architecture running fully offline using a local LLM with strict document grounding.",
    icon: Server,
  },
  {
    title: "Interactive Chat Interface",
    description:
      "Natural language querying with citations and source references from internal documents.",
    icon: MessageSquare,
  },
  {
    title: "Privacy & Security",
    description:
      "No cloud calls or external APIs. All models and data remain within local infrastructure.",
    icon: Lock,
  },
];

const constraints = [
  "Fully offline operation with zero internet dependency",
  "Optimized for local hardware (CPU / optional GPU)",
  "Strict document-based response generation",
  "Designed for sensitive and internal knowledge bases",
];

/* ---------------- Page ---------------- */

export default function HomePage() {
  return (
    <main className="min-h-screen bg-slate-50">
      <Header />

      {/* Hero */}
      <section className="mx-auto max-w-6xl px-6 py-24">
        <div className="max-w-3xl">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-slate-300 text-sm text-slate-700 mb-6">
            <Lock className="w-4 h-4" />
            100% Offline & Secure
          </div>

          <h1 className="text-4xl md:text-5xl font-bold leading-tight text-slate-900">
            Offline AI-Powered Knowledge Retrieval for
            <span className="block text-slate-700">
              Secure Internal Documents
            </span>
          </h1>

          <p className="mt-6 text-lg text-slate-600 leading-relaxed">
            A private, offline RAG-based system enabling organizations to
            search and interact with internal knowledge while maintaining
            complete data sovereignty.
          </p>

          <div className="mt-10 flex gap-4">
            <Link
              href="/login"
              className="h-12 px-6 inline-flex items-center gap-2 rounded-md bg-slate-900 text-white text-sm font-medium hover:bg-slate-800 transition"
            >
              <Search className="w-4 h-4" />
              Access System
            </Link>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="bg-white border-t border-slate-200">
        <div className="mx-auto max-w-6xl px-6 py-20">
          <h2 className="text-3xl font-bold text-slate-900 mb-12">
            Core Capabilities
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {features.map((f) => (
              <FeatureCard
                key={f.title}
                title={f.title}
                description={f.description}
                icon={f.icon}
              />
            ))}
          </div>
        </div>
      </section>

      {/* Constraints */}
      <section className="border-t border-slate-200">
        <div className="mx-auto max-w-6xl px-6 py-20">
          <h2 className="text-3xl font-bold text-slate-900 mb-8">
            Design Constraints
          </h2>

          <ul className="space-y-4 max-w-3xl">
            {constraints.map((c, i) => (
              <li key={i} className="flex items-start gap-3">
                <CheckCircle2 className="w-5 h-5 text-slate-700 mt-0.5" />
                <span className="text-slate-600">{c}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto max-w-6xl px-6 py-8 flex flex-col md:flex-row items-center justify-between gap-4">
          <p className="text-sm text-slate-500">
            Offline AI-Powered RAG Knowledge Portal
          </p>
          <p className="text-sm text-slate-500">
            Data remains fully on-premise
          </p>
        </div>
      </footer>
    </main>
  );
}
