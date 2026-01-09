'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2, MessageSquare, Plus, Send } from 'lucide-react';

interface Message {
  type: 'user' | 'bot';
  content: string;
  sources?: string[];
}

interface ConversationItem {
  conversation_id: number;
  mode: 'public' | 'dual';
  title?: string | null;
  created_at: string;
  updated_at: string;
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

export default function ChatDualPage() {
  const router = useRouter();
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [isAuthorized, setIsAuthorized] = useState(false);
  const [conversations, setConversations] = useState<ConversationItem[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<number | null>(null);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      router.push('/login');
      return;
    }
    const userType = localStorage.getItem('user_type');
    if (userType !== 'admin' && userType !== 'user') {
      router.push('/chat');
      return;
    }
    setIsLoggedIn(true);
    setIsAuthorized(true);
  }, [router]);

  const authHeaders = () => {
    const token = localStorage.getItem('access_token');
    return {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    };
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const loadConversations = async () => {
    setLoadingList(true);
    try {
      const res = await fetch(`${API_BASE_URL}/conversations?mode=dual`, {
        headers: authHeaders(),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to load conversations');
      setConversations(data.items || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingList(false);
    }
  };

  const loadHistory = async (conversationId: number) => {
    setLoadingHistory(true);
    try {
      const res = await fetch(`${API_BASE_URL}/conversations/${conversationId}/history`, {
        headers: authHeaders(),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to load history');
      const history = (data.history || []) as Array<{ role: 'user' | 'assistant'; content: string }>;
      setMessages(
        history.map((m) => ({
          type: m.role === 'user' ? 'user' : 'bot',
          content: m.content,
        }))
      );
    } catch (e) {
      console.error(e);
      setMessages([]);
    } finally {
      setLoadingHistory(false);
    }
  };

  const createConversation = async () => {
    const res = await fetch(`${API_BASE_URL}/conversations`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ mode: 'dual' }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed to create conversation');
    return data as { conversation_id: number };
  };

  useEffect(() => {
    if (!isAuthorized) return;
    loadConversations();
  }, [isAuthorized]);

  const handleNewChat = async () => {
    setLoading(true);
    try {
      const created = await createConversation();
      setActiveConversationId(created.conversation_id);
      setMessages([]);
      await loadConversations();
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectConversation = async (conversationId: number) => {
    setActiveConversationId(conversationId);
    await loadHistory(conversationId);
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMessage: Message = { type: 'user', content: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      let conversationId = activeConversationId;
      if (!conversationId) {
        const created = await createConversation();
        conversationId = created.conversation_id;
        setActiveConversationId(conversationId);
        await loadConversations();
      }

      const res = await fetch(`${API_BASE_URL}/conversations/${conversationId}/send`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ user_input: input }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Chat failed');

      const botMessage: Message = {
        type: 'bot',
        content: data.answer || 'No response received',
        sources: data.sources || [],
      };
      setMessages((prev) => [...prev, botMessage]);
      await loadConversations();
    } catch (err) {
      console.error('Chat error:', err);
      const errorMessage: Message = {
        type: 'bot',
        content: `Error: ${err instanceof Error ? err.message : 'Failed to get response'}`,
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  if (!isLoggedIn || !isAuthorized) return null;

  return (
    <main className="h-screen bg-slate-50 pt-32">
      <div className="h-[calc(100vh-8rem)] flex">
        <aside className="w-80 border-r border-slate-200 bg-white">
          <div className="p-4 border-b border-slate-200 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <MessageSquare className="w-4 h-4 text-slate-600" />
              <h2 className="text-sm font-semibold text-slate-900">Dual Chats</h2>
            </div>
            <button
              onClick={handleNewChat}
              className="h-8 px-3 inline-flex items-center gap-2 rounded-md bg-slate-900 text-white text-sm hover:bg-slate-800 disabled:opacity-50"
              disabled={loading}
            >
              <Plus className="w-4 h-4" /> New
            </button>
          </div>

          <div className="p-2 overflow-y-auto h-[calc(100%-56px)]">
            {loadingList ? (
              <div className="p-4 text-sm text-slate-600">Loading chats…</div>
            ) : conversations.length === 0 ? (
              <div className="p-4 text-sm text-slate-600">No chats yet.</div>
            ) : (
              <div className="space-y-1">
                {conversations.map((c) => (
                  <button
                    key={c.conversation_id}
                    onClick={() => handleSelectConversation(c.conversation_id)}
                    className={`w-full text-left px-3 py-2 rounded-md border text-sm hover:bg-slate-50 ${
                      activeConversationId === c.conversation_id
                        ? 'border-slate-900 bg-slate-50'
                        : 'border-slate-200 bg-white'
                    }`}
                  >
                    <div className="font-medium text-slate-900 truncate">
                      {c.title || `Conversation ${c.conversation_id}`}
                    </div>
                    <div className="text-xs text-slate-500">{new Date(c.updated_at).toLocaleString()}</div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </aside>

        <section className="flex-1 flex flex-col">
          <div className="flex-1 overflow-y-auto px-4 py-6">
            <div className="max-w-4xl mx-auto space-y-4">
              {loadingHistory ? (
                <div className="flex items-center justify-center h-64">
                  <Loader2 className="w-6 h-6 animate-spin text-slate-600" />
                </div>
              ) : messages.length === 0 ? (
                <div className="flex items-center justify-center h-64">
                  <div className="text-center">
                    <h2 className="text-2xl font-bold text-slate-900 mb-2">Start a Dual Conversation</h2>
                    <p className="text-slate-600">Select a chat or create a new one</p>
                  </div>
                </div>
              ) : (
                messages.map((msg, idx) => (
                  <div key={idx} className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div
                      className={`max-w-2xl rounded-lg px-4 py-3 ${
                        msg.type === 'user'
                          ? 'bg-slate-900 text-white'
                          : 'bg-white border border-slate-200 text-slate-900'
                      }`}
                    >
                      <p className="whitespace-pre-wrap">{msg.content}</p>
                      {msg.sources && msg.sources.length > 0 && (
                        <div className="mt-3 pt-3 border-t border-slate-200">
                          <p className="text-sm font-semibold mb-2">Sources:</p>
                          <ul className="text-sm space-y-1">
                            {msg.sources.map((source, i) => (
                              <li key={i} className="text-slate-600">
                                • {source}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  </div>
                ))
              )}

              {loading && (
                <div className="flex justify-start">
                  <div className="bg-white border border-slate-200 rounded-lg px-4 py-3">
                    <Loader2 className="w-5 h-5 animate-spin text-slate-600" />
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          </div>

          <div className="sticky bottom-0 border-t border-slate-200 bg-white px-4 py-4 shadow-lg">
            <div className="max-w-4xl mx-auto">
              <form onSubmit={handleSendMessage} className="flex gap-3">
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Ask a question..."
                  className="flex-1 px-4 py-2.5 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-900"
                  disabled={loading}
                  autoFocus
                />
                <button
                  type="submit"
                  disabled={loading || !input.trim()}
                  className="h-10 px-4 rounded-lg bg-slate-900 text-white font-medium hover:bg-slate-800 transition disabled:opacity-50 inline-flex items-center gap-2"
                >
                  {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                </button>
              </form>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
