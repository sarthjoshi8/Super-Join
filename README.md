Super Join: Semantic Reconciliation

You can test on : https://sarthjoshi8-super-join.vercel.app/

Super Join is a full-stack, AI-powered fact extraction and reconciliation engine. It ingests complex PDF documents such as financial prospectuses, economic surveys, annual reports, and cover letters, extracts structured facts, and automatically maps relationships between them to detect corroborations, contradictions, and contextual differences across the knowledge base.

## 🚀 Features

* **Automated Ingestion Pipeline:** Drag and drop PDFs to automatically extract granular, structured facts including Subject, Predicate, Value, Scope, and Time.
* **Lightweight Vector Search:** Uses an optimized, deterministic feature-hashing algorithm to vectorize text without requiring heavy ML embedding models.
* **AI-Powered Adjudication:** Uses Google's Gemini API to evaluate fact pairs across different documents and categorize their relationships as `CORROBORATES`, `CONTRADICTS`, `CONTEXTUALLY_DIFFERS`, or `UNRELATED`.
* **Heuristic Fallback:** If the LLM is unavailable or rate-limited, the system can fall back to deterministic, overlap-based matching.
* **Built-in Financial Datasets:** Includes baseline datasets such as India Economic Survey, RBI Annual Reports, and Delhivery financial documents for cross-document analysis.
* **Cross-Document Reconciliation:** Identifies relationships between facts extracted from different documents.
* **Structured Fact Storage:** Stores extracted facts with metadata such as source document, page number, scope, time period, and confidence.

## 🛠 Tech Stack

### Frontend

* **Framework:** React + Vite
* **Styling:** Vanilla CSS with custom glassmorphism and modern dark-mode UI
* **Deployment:** Vercel

### Backend

* **Framework:** FastAPI
* **Database:** SQLite with SQLAlchemy
* **Vector Store:** ChromaDB
* **PDF Processing:** PyMuPDF
* **AI Integration:** Google GenAI SDK / Gemini
* **Deployment:** Render

## 📦 Local Development Setup

### 1. Clone the Repository

```bash
git clone https://github.com/sarthjoshi8/Super-Join.git
cd Super-Join
```

### 2. Backend Setup

Navigate to the backend directory:

```bash
cd backend
```

Create and activate a virtual environment:

```bash
python -m venv venv
source venv/bin/activate
```

On Windows:

```bash
venv\Scripts\activate
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

Create a `.env` file inside the `backend` directory:

```env
GEMINI_API_KEY=your_gemini_api_key_here
```

Start the FastAPI server:

```bash
uvicorn app.main:app --reload
```

The backend will be available at:

```text
http://127.0.0.1:8000
```

### 3. Frontend Setup

Open a new terminal and navigate to the frontend directory:

```bash
cd frontend
```

Install dependencies:

```bash
npm install
```

Start the development server:

```bash
npm run dev
```

The frontend will be available at:

```text
http://localhost:5173
```

## ☁️ Deployment Architecture

```text
                    ┌─────────────────────┐
                    │      User / PDF      │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   React + Vite UI   │
                    │      (Vercel)        │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    FastAPI Backend  │
                    │      (Render)       │
                    └──────────┬──────────┘
                               │
                 ┌─────────────┼─────────────┐
                 ▼             ▼             ▼
          ┌───────────┐ ┌───────────┐ ┌────────────┐
          │ PyMuPDF   │ │  Gemini   │ │   SQLite   │
          │ PDF Text  │ │   Facts   │ │  Database  │
          └───────────┘ └───────────┘ └────────────┘
                               │
                               ▼
                       ┌─────────────┐
                       │  ChromaDB   │
                       │ Vector Store│
                       └─────────────┘
```

* **Frontend:** Hosted on Vercel and communicates with the backend through the `VITE_API_BASE_URL` environment variable.
* **Backend:** Hosted on Render and provides PDF ingestion, fact extraction, vector search, and reconciliation APIs.
* **Gemini:** Used server-side for structured fact extraction and relationship adjudication.
* **SQLite:** Stores documents, extracted facts, and reconciliation results.
* **ChromaDB:** Stores lightweight local vector representations for similarity search.
* **Built-in Dataset:** The repository includes a `data/built-in-dataset` directory containing baseline PDF documents.

## 🧠 How It Works

### 1. PDF Ingestion

A user uploads a PDF through the frontend.

The FastAPI backend receives the document and processes it using PyMuPDF.

### 2. Fact Extraction

The extracted PDF text is divided into manageable chunks and sent to Gemini.

Gemini returns structured facts containing information such as:

* Subject
* Predicate
* Value
* Numeric Value
* Unit
* Time Period
* Scope
* Source Statement
* Confidence

### 3. Fact Storage

The extracted facts are stored in SQLite using SQLAlchemy.

Each fact maintains its relationship with the source document and page.

### 4. Vectorization

Each fact is converted into a lightweight deterministic vector using feature hashing.

This avoids the need for large embedding models and keeps the vector-search layer lightweight.

The vectors are stored in ChromaDB.

### 5. Cross-Document Matching

When the user requests connection analysis, the system searches ChromaDB for similar facts originating from other documents.

This identifies potentially related information across the knowledge base.

### 6. AI Adjudication

Potentially related fact pairs are evaluated by Gemini.

The system categorizes each relationship as:

```text
CORROBORATES
CONTRADICTS
CONTEXTUALLY_DIFFERS
UNRELATED
```

### 7. Visualization

The resulting relationships are stored in the database and displayed through the React frontend.

This allows users to explore connections, supporting evidence, contradictions, and contextual differences between documents.

## 🔐 Environment Variables

### Backend

Create a `.env` file inside `backend`:

```env
GEMINI_API_KEY=your_gemini_api_key_here
```

Never commit API keys or other secrets to GitHub.

### Frontend

For production deployment, configure:

```env
VITE_API_BASE_URL=https://super-join-backend.onrender.com
```

## 📁 Project Structure

```text
Super-Join/
│
├── backend/
│   ├── app/
│   │   ├── routers/
│   │   ├── services/
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models.py
│   │   └── main.py
│   ├── requirements.txt
│   └── .env
│
├── frontend/
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── vite.config.js
│
├── data/
│   ├── built-in-dataset/
│   └── README.md
│
└── README.md
```

## 🌐 Live Deployment

**Frontend:**
https://sarthjoshi8-super-join.vercel.app/

**Backend:**
https://super-join-backend.onrender.com

## 🎯 Project Goal

Super Join is designed to transform unstructured PDF collections into an interconnected knowledge base.

Instead of simply searching documents individually, the system extracts factual claims and determines how information from different sources relates to one another.

This makes it possible to discover:

* Supporting evidence
* Contradictory claims
* Similar information expressed differently
* Time-dependent changes
* Cross-document relationships
* Contextual differences

The result is a lightweight **semantic reconciliation layer** for complex document collections.
