"use client";

import { useState, useRef, useEffect, KeyboardEvent, DragEvent } from "react";
import ReactMarkdown from "react-markdown";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

interface Citation {
  id: string;
  page?: number | null;
  type: "text" | "web";
  content?: string | null;
  title?: string | null;
  url?: string | null;
}

interface PageImage {
  page: number;
  image: string;
}

// ─── Upload Panel ─────────────────────────────────────────────────────────────

function UploadPanel({
  onUpload,
  isUploading,
  docName,
  webSearchEnabled,
  onToggleWebSearch,
}: {
  onUpload: (file: File) => void;
  isUploading: boolean;
  docName: string | null;
  webSearchEnabled: boolean;
  onToggleWebSearch: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const handleFile = (file: File) => {
    if (file.type === "application/pdf") onUpload(file);
    else alert("Only PDF files are supported.");
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  return (
    <div className="upload-panel">
      <p className="panel-label">Document</p>
      <div
        className={`drop-zone ${dragging ? "dz-active" : ""} ${docName ? "dz-loaded" : ""}`}
        onClick={() => !isUploading && inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf"
          style={{ display: "none" }}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
        />
        {isUploading ? (
          <div className="dz-inner">
            <div className="spinner" />
            <span>Processing…</span>
          </div>
        ) : docName ? (
          <div className="dz-inner">
            <span style={{ fontSize: 24 }}>📄</span>
            <span className="doc-name" title={docName}>{docName}</span>
            <span className="doc-change">Click to change</span>
          </div>
        ) : (
          <div className="dz-inner">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ color: "var(--t3)" }}>
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            <span>Drop PDF here</span>
            <span style={{ fontSize: 11, color: "var(--t3)" }}>or click to browse</span>
          </div>
        )}
      </div>

      <div className="toggle-row">
        <div>
          <p className="toggle-label">Web Search</p>
          <p className="toggle-sub">Supplement with live results</p>
        </div>
        <button
          className={`toggle ${webSearchEnabled ? "toggle-on" : ""}`}
          onClick={onToggleWebSearch}
          aria-pressed={webSearchEnabled}
        >
          <span className="toggle-thumb" />
        </button>
      </div>
    </div>
  );
}

// ─── Citation Panel ───────────────────────────────────────────────────────────

function CitationPanel({
  citations,
  pageImages,
}: {
  citations: Citation[];
  pageImages: PageImage[];
}) {
  const [tab, setTab] = useState<"sources" | "pages">("sources");
  const [lightbox, setLightbox] = useState<string | null>(null);

  const docCitations = citations.filter((c) => c.type === "text");
  const webCitations = citations.filter((c) => c.type === "web");

  return (
    <div className="citation-panel">
      <div className="ctabs">
        <button className={`ctab ${tab === "sources" ? "ctab-active" : ""}`} onClick={() => setTab("sources")}>
          Sources <span className="badge">{citations.length}</span>
        </button>
        {pageImages.length > 0 && (
          <button className={`ctab ${tab === "pages" ? "ctab-active" : ""}`} onClick={() => setTab("pages")}>
            Pages <span className="badge">{pageImages.length}</span>
          </button>
        )}
      </div>

      {tab === "sources" && (
        <div className="clist">
          {docCitations.length > 0 && (
            <>
              <p className="cgroup">From Document</p>
              {docCitations.map((c) => (
                <div key={c.id} className="ccard ccard-doc">
                  <div className="ccard-header">
                    <span className="ccard-type">📄 Doc</span>
                    {c.page && <span className="ccard-page">p.{c.page}</span>}
                  </div>
                  {c.content && <p className="ccard-text">{c.content}</p>}
                </div>
              ))}
            </>
          )}
          {webCitations.length > 0 && (
            <>
              <p className="cgroup">From Web</p>
              {webCitations.map((c) => (
                <a key={c.id} href={c.url ?? "#"} target="_blank" rel="noopener noreferrer" className="ccard ccard-web">
                  <div className="ccard-header">
                    <span className="ccard-type">🌐 Web</span>
                  </div>
                  {c.title && <p className="ccard-title">{c.title}</p>}
                  {c.content && <p className="ccard-text">{c.content}</p>}
                </a>
              ))}
            </>
          )}
        </div>
      )}

      {tab === "pages" && (
        <div className="clist">
          {pageImages.map((pi) => (
            <div key={pi.page} className="page-card" onClick={() => setLightbox(pi.image)}>
              <img src={`data:image/png;base64,${pi.image}`} alt={`Page ${pi.page}`} className="page-thumb" />
              <span className="page-label">Page {pi.page}</span>
            </div>
          ))}
        </div>
      )}

      {lightbox && (
        <div className="lightbox" onClick={() => setLightbox(null)}>
          <img src={`data:image/png;base64,${lightbox}`} alt="Page" className="lightbox-img" />
          <button className="lightbox-close">✕</button>
        </div>
      )}
    </div>
  );
}

// ─── Chat Panel ───────────────────────────────────────────────────────────────

function ChatPanel({
  messages,
  isLoading,
  onSend,
}: {
  messages: Message[];
  isLoading: boolean;
  onSend: (q: string) => void;
}) {
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const send = () => {
    const q = input.trim();
    if (!q || isLoading) return;
    onSend(q);
    setInput("");
    if (taRef.current) taRef.current.style.height = "auto";
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  };

  const onInput = () => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
  };

  return (
    <div className="chat-panel">
      <div className="messages">
        {messages.length === 0 && (
          <div className="empty">
            <div className="empty-icon">◈</div>
            <p className="empty-title">Upload a document to begin</p>
            <p className="empty-sub">Ask questions about any PDF — tables, images, and text understood.</p>
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`msg msg-${m.role}`}>
            <div className="avatar">{m.role === "user" ? "U" : "◈"}</div>
            <div className="msg-body">
              {m.role === "assistant" ? (
                <div className="msg-md"><ReactMarkdown>{m.content}</ReactMarkdown></div>
              ) : (
                <p className="msg-text">{m.content}</p>
              )}
              <span className="msg-time">
                {m.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              </span>
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="msg msg-assistant">
            <div className="avatar">◈</div>
            <div className="msg-body">
              <div className="thinking"><span /><span /><span /></div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="input-row">
        <textarea
          ref={taRef}
          className="chat-input"
          placeholder="Ask about your document…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKey}
          onInput={onInput}
          rows={1}
          disabled={isLoading}
        />
        <button className="send-btn" onClick={send} disabled={!input.trim() || isLoading}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      </div>
    </div>
  );
}

// ─── Root Page ────────────────────────────────────────────────────────────────

export default function Home() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [docName, setDocName] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [pageImages, setPageImages] = useState<PageImage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [webSearch, setWebSearch] = useState(false);

  const handleUpload = async (file: File) => {
    setIsUploading(true);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const res = await fetch("http://localhost:8000/upload", { method: "POST", body: fd });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setSessionId(data.session_id);
      setDocName(file.name);
      setMessages([{
        id: crypto.randomUUID(),
        role: "assistant",
        content: `Document **"${file.name}"** uploaded and indexed successfully. Ask me anything about it!`,
        timestamp: new Date(),
      }]);
      setCitations([]);
      setPageImages([]);
    } catch (err: any) {
      alert("Upload failed: " + err.message);
    } finally {
      setIsUploading(false);
    }
  };

  const handleQuery = async (query: string) => {
    setMessages((p) => [...p, { id: crypto.randomUUID(), role: "user", content: query, timestamp: new Date() }]);
    setIsLoading(true);
    setCitations([]);
    setPageImages([]);
    try {
      const res = await fetch("http://localhost:8000/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, session_id: sessionId ?? "", is_web_search_enabled: webSearch }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setMessages((p) => [...p, { id: crypto.randomUUID(), role: "assistant", content: data.answer, timestamp: new Date() }]);
      setCitations(data.citations ?? []);
      setPageImages(data.page_images ?? []);
    } catch (err: any) {
      setMessages((p) => [...p, { id: crypto.randomUUID(), role: "assistant", content: "Error: " + err.message, timestamp: new Date() }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-icon">◈</span>
          <span className="brand-name">DocMind</span>
        </div>
        <UploadPanel
          onUpload={handleUpload}
          isUploading={isUploading}
          docName={docName}
          webSearchEnabled={webSearch}
          onToggleWebSearch={() => setWebSearch((v) => !v)}
        />
        {(citations.length > 0 || pageImages.length > 0) && (
          <CitationPanel citations={citations} pageImages={pageImages} />
        )}
      </aside>
      <main className="main">
        <ChatPanel messages={messages} isLoading={isLoading} onSend={handleQuery} />
      </main>
    </div>
  );
}
