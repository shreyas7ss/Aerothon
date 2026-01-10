'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import Link from 'next/link';
import { LogOut, Upload, Users, MessageSquare } from 'lucide-react';

/* ================= MODAL SHELL ================= */

function ModalShell({
  children,
  onClose,
}: {
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-white/10 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-xl w-full max-w-md mx-4 p-8 border border-slate-200 shadow-2xl"
      >
        {children}
      </div>
    </div>
  );
}

/* ================= NAVBAR ================= */

export default function Navbar() {
  const router = useRouter();
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [userType, setUserType] = useState<string | null>(null);
  const [username, setUsername] = useState<string | null>(null);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [showCreateUserModal, setShowCreateUserModal] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (token) {
      setIsLoggedIn(true);
      setUserType(localStorage.getItem('user_type'));
      setUsername(localStorage.getItem('username'));
    }
  }, []);

  const handleLogout = () => {
    localStorage.clear();
    window.location.href = '/';
  };

  return (
    <>
      <header className="sticky top-0 z-50">
        <div className="bg-slate-100">
          <div className="bg-white rounded-tl-[100px]">
            <div className="mx-auto max-w-7xl px-6 h-20 flex items-center justify-between">
              {/* Left: IIIT Logo */}
              <Link href="/" className="cursor-pointer">
                <LogoBlock
                  src="/iiitdwd.jpeg"
                  title="IIIT Dharwad"
                  subtitle="Institute of National Importance"
                  clickable={true}
                />
              </Link>

              {/* Center: Actions */}
              <div className="flex items-center gap-3">
                {isLoggedIn ? (
                  <>
                    <span className="text-sm text-slate-600">
                      Welcome, <b>{username}</b>
                    </span>

                    {userType === 'admin' && (
                      <>
                        <ActionBtn onClick={() => setShowUploadModal(true)} icon={Upload} label="File Upload" />
                        <ActionBtn onClick={() => setShowCreateUserModal(true)} icon={Users} label="Create User" />
                      </>
                    )}

                    <ActionBtn
                      onClick={() => router.push(userType === 'ruser' ? '/chat' : '/chat-dual')}
                      icon={MessageSquare}
                      label="Chat"
                    />

                    <button
                      onClick={handleLogout}
                      className="h-10 px-4 inline-flex items-center gap-2 rounded-md bg-red-600 text-white text-sm hover:bg-red-700"
                    >
                      <LogOut className="w-4 h-4" /> Logout
                    </button>
                  </>
                ) : (
                  <Link href="/login" className="h-10 px-5 flex items-center border rounded-md text-sm">
                    Login
                  </Link>
                )}
              </div>

              {/* Right: HAL Logo */}
              <LogoBlock
                src="/hal.jpeg"
                title="Hindustan Aeronautics Ltd."
                subtitle="A Maharatna CPSE"
              />
            </div>
          </div>
        </div>

        <div className="bg-blue-900 h-12" />
      </header>

      {showUploadModal && <FileUploadModal onClose={() => setShowUploadModal(false)} />}
      {showCreateUserModal && <CreateUserModal onClose={() => setShowCreateUserModal(false)} />}

    </>
  );
}

/* ================= HELPERS ================= */

function LogoBlock({ src, title, subtitle, clickable = false }: any) {
  return (
    <div className={`flex items-center gap-3 ${clickable ? 'cursor-pointer hover:opacity-80 transition-opacity' : ''}`}>
      <Image src={src} alt={title} width={48} height={48} />
      <div>
        <p className="text-sm font-semibold">{title}</p>
        <p className="text-xs text-slate-500">{subtitle}</p>
      </div>
    </div>
  );
}

function ActionBtn({ onClick, icon: Icon, label }: any) {
  return (
    <button
      onClick={onClick}
      className="h-10 px-4 inline-flex items-center gap-2 rounded-md border text-sm hover:bg-slate-100"
    >
      <Icon className="w-4 h-4" /> {label}
    </button>
  );
}

/* ================= FILE UPLOAD MODAL ================= */

function FileUploadModal({ onClose }: { onClose: () => void }) {
  const [files, setFiles] = useState<FileList | null>(null);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState('');
  const [uploadType, setUploadType] = useState<'public' | 'secure'>('public');

  const handleUpload = async () => {
    if (!files) return setMessage('Select at least one file');

    setUploading(true);
    const formData = new FormData();
    Array.from(files).forEach(f => formData.append('files', f));
    formData.append('category', uploadType === 'secure' ? 'confidential' : 'general');

    try {
      const endpoint = uploadType === 'secure' ? '/ingest/secure' : '/ingest/public';
      const res = await fetch(`http://localhost:8000${endpoint}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` },
        body: formData,
      });
      if (!res.ok) throw new Error();
      setMessage('Upload successful');
      setTimeout(onClose, 1200);
    } catch {
      setMessage('Upload failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <ModalShell onClose={onClose}>
      <h2 className="text-xl font-semibold mb-4">Upload Documents</h2>

      <div className="mb-4">
        <label className="block text-sm font-medium mb-2">Upload Type</label>
        <div className="flex gap-4">
          <label className="flex items-center cursor-pointer">
            <input
              type="radio"
              name="uploadType"
              value="public"
              checked={uploadType === 'public'}
              onChange={() => setUploadType('public')}
              className="mr-2"
            />
            <span className="text-sm">Public Knowledge Base</span>
          </label>
          <label className="flex items-center cursor-pointer">
            <input
              type="radio"
              name="uploadType"
              value="secure"
              checked={uploadType === 'secure'}
              onChange={() => setUploadType('secure')}
              className="mr-2"
            />
            <span className="text-sm">Secure Knowledge Base</span>
          </label>
        </div>
      </div>

      <label className="block border-2 border-dashed rounded-lg p-6 text-center cursor-pointer mb-4">
        <Upload className="mx-auto mb-2 text-slate-400" />
        <input type="file" multiple hidden onChange={(e) => setFiles(e.target.files)} />
        <span className="text-sm text-slate-600">
          {files ? `${files.length} file(s) selected` : 'Click to select files'}
        </span>
      </label>

      {message && <p className="text-sm mb-3">{message}</p>}

      <div className="flex gap-3">
        <button onClick={onClose} className="flex-1 border rounded-md h-10">Cancel</button>
        <button onClick={handleUpload} disabled={uploading} className="flex-1 bg-slate-900 text-white rounded-md h-10">
          {uploading ? 'Uploading...' : 'Upload'}
        </button>
      </div>
    </ModalShell>
  );
}

/* ================= CREATE USER MODAL ================= */

function CreateUserModal({ onClose }: { onClose: () => void }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [type, setType] = useState<'user' | 'ruser'>('user');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  const submit = async (e: any) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await fetch('http://localhost:8000/create-user', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('access_token')}`,
        },
        body: JSON.stringify({ username, password, usertype: type }),
      });
      if (!res.ok) throw new Error();
      setMessage('User created');
      setTimeout(onClose, 1200);
    } catch {
      setMessage('Failed to create user');
    } finally {
      setLoading(false);
    }
  };

  return (
    <ModalShell onClose={onClose}>
      <h2 className="text-xl font-semibold mb-4">Create User</h2>

      <form onSubmit={submit} className="space-y-4">
        <input placeholder="Username" value={username} onChange={e => setUsername(e.target.value)} className="w-full border rounded-md p-2" required />
        <input type="password" placeholder="Password" value={password} onChange={e => setPassword(e.target.value)} className="w-full border rounded-md p-2" required />
        <select value={type} onChange={e => setType(e.target.value as 'user' | 'ruser')} className="w-full border rounded-md p-2">
          <option value="user">User (Full Access)</option>
          <option value="ruser">Restricted User (Public Only)</option>
        </select>

        {message && <p className="text-sm">{message}</p>}

        <div className="flex gap-3">
          <button type="button" onClick={onClose} className="flex-1 border h-10 rounded-md">Cancel</button>
          <button disabled={loading} className="flex-1 bg-slate-900 text-white h-10 rounded-md">
            {loading ? 'Creating...' : 'Create'}
          </button>
        </div>
      </form>
    </ModalShell>
  );
}
