'use client';

import { useEffect, useState } from 'react';
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
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [userType, setUserType] = useState<string | null>(null);

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    const storedUserType = localStorage.getItem('user_type');
    
    if (token) {
      setIsLoggedIn(true);
      setUserType(storedUserType);
    }
  }, []);

  return (
    <main className="min-h-screen bg-slate-50">
      {/* Hero */}
      {!isLoggedIn ? (
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
      ): ""}

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
       : (
        <section className="mx-auto max-w-6xl px-6 py-24">
          <h1 className="text-4xl font-bold text-slate-900 mb-8">
            Welcome to Aerothon
          </h1>
          <p className="text-lg text-slate-600 mb-12">
            Offline AI-Powered Knowledge Portal
          </p>

          {userType === 'admin' && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-2xl">
              <div className="bg-white rounded-xl p-8 border border-slate-200 shadow-sm">
                <div className="w-12 h-12 rounded-md bg-blue-100 flex items-center justify-center mb-4">
                  <Upload className="w-6 h-6 text-blue-600" />
                </div>
                <h3 className="text-xl font-semibold text-slate-900 mb-2">
                  File Upload
                </h3>
                <p className="text-slate-600 mb-6">
                  Upload and index documents (PDF, DOCX, TXT) for the knowledge base.
                </p>
              </div>

              <div className="bg-white rounded-xl p-8 border border-slate-200 shadow-sm">
                <div className="w-12 h-12 rounded-md bg-green-100 flex items-center justify-center mb-4">
                  <MessageSquare className="w-6 h-6 text-green-600" />
                </div>
                <h3 className="text-xl font-semibold text-slate-900 mb-2">
                  Create User
                </h3>
                <p className="text-slate-600 mb-6">
                  Create new admin and user accounts for system access.
                </p>
              </div>
            </div>
          )}

          {userType === 'user' && (
            <div className="bg-white rounded-xl p-8 border border-slate-200 shadow-sm max-w-2xl">
              <div className="w-12 h-12 rounded-md bg-purple-100 flex items-center justify-center mb-4">
                <MessageSquare className="w-6 h-6 text-purple-600" />
              </div>
              <h3 className="text-xl font-semibold text-slate-900 mb-2">
                Chat with Knowledge Base
              </h3>
              <p className="text-slate-600 mb-6">
                Ask questions about the indexed documents and get AI-powered responses.
              </p>
            </div>
          )}
        </section>
      )

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
