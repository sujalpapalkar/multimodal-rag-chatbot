# DocMind — Multimodal RAG Chatbot

A production-grade Multimodal Retrieval-Augmented Generation (RAG) chatbot that lets you upload PDF documents and ask questions about them using AI. Supports text, tables, and images extracted from PDFs, with optional live web search.

---

## Features

- **PDF Upload & Indexing** — Upload any PDF and have it processed, chunked, and indexed automatically
- **Multimodal Understanding** — Extracts and understands text, tables, and images from PDFs
- **AI-Powered Q&A** — Ask natural language questions and get accurate answers with page citations
- **Web Search Integration** — Toggle web search to supplement document answers with live results
- **Hybrid Search** — Combines document and web results into a single synthesized answer
- **Page Image Previews** — View the actual pages referenced in each answer
- **Dark Editorial UI** — Clean, modern interface built with Next.js and Tailwind CSS

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14, React, Tailwind CSS, TypeScript |
| Backend | FastAPI, Python 3.12, Uvicorn |
| LLM | Google Gemini 2.5 Flash Lite |
| Embeddings | Google Gemini Embedding 001 |
| Vector Store | Pinecone (Serverless) |
| PDF Processing | Unstructured, PyMuPDF |
| Web Search | Serper API |

---

## Project Structure

```
multimodal_rag/
├── backend/
│   ├── main.py              # FastAPI app with all endpoints
│   ├── requirements.txt     # Python dependencies
│   └── .env                 # Environment variables (not committed)
├── frontend/
│   ├── app/
│   │   ├── page.tsx         # Main page with all components inline
│   │   ├── layout.tsx       # Root layout
│   │   └── globals.css      # Global styles
│   ├── package.json
│   ├── next.config.mjs
│   ├── tailwind.config.ts
│   └── tsconfig.json
└── README.md
```

---

## Prerequisites

- Python 3.12+
- Node.js 18+
- Homebrew (macOS) for system dependencies
- Tesseract OCR: `brew install tesseract`

---

## API Keys Required

| Key | Where to Get |
|---|---|
| `GEMINI_API_KEY` | [aistudio.google.com](https://aistudio.google.com) |
| `PINECONE_API_KEY` | [app.pinecone.io](https://app.pinecone.io) |
| `SERPER_API_KEY` | [serper.dev](https://serper.dev) |

---

## Setup & Installation

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd multimodal_rag
```

### 2. Backend Setup

```bash
cd backend

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
touch .env
```

Add the following to `backend/.env`:

```env
GEMINI_API_KEY=your-gemini-api-key
PINECONE_API_KEY=your-pinecone-api-key
SERPER_API_KEY=your-serper-api-key
```

### 3. Pinecone Index Setup

Create a new index in your Pinecone dashboard with:
- **Name**: `multimodal-rag-index`
- **Dimensions**: `2048`
- **Metric**: `cosine`
- **Cloud**: AWS, Region: us-east-1

### 4. Frontend Setup

```bash
cd frontend
npm install
```

---

## Running the App

Start the backend (in one terminal):

```bash
cd backend
source venv/bin/activate
uvicorn main:app --reload --port 8000
```

Start the frontend (in another terminal):

```bash
cd frontend
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## Usage

1. Upload a PDF using the drop zone in the sidebar
2. Wait for processing (first upload downloads AI models, takes a few minutes)
3. Ask any question about your document in the chat input
4. Toggle **Web Search** to supplement answers with live web results
5. Click **Pages** in the sidebar to view referenced page images

---

## Notes

- The free tier of Gemini API has rate limits (20 requests/day for some models). If you hit limits, wait until the next day or use a new API key.
- The first upload downloads YOLO and Table Transformer models (~330MB total) — subsequent uploads are faster.
- Session data is stored in memory and is lost when the backend restarts. Re-upload your document after restarting.

---


## 👤 Author

**Sujal P.** — Final Year Student | AI / ML | Full-Stack Development

---

## ⭐ If you like this project

Give it a ⭐ on GitHub — it really helps!