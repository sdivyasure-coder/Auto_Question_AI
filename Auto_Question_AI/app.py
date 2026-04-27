from flask import Flask, render_template, request, redirect, session, send_file, jsonify
import os
import sqlite3
import csv
import json
import re
import hashlib
import mimetypes
import io
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
import requests
import numpy as np
from werkzeug.exceptions import RequestEntityTooLarge

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

from generator import (
    GeneratorConfig,
    ai_generate_questions,
    append_questions_to_csv,
    apply_preview_edits,
    build_download_name,
    generate_pdf_from_questions,
    generate_question_paper_from_data,
    get_question_bank_rows,
    get_question_by_id,
    get_questions,
    update_question_in_csv,
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 60 * 1024 * 1024  # 60 MB upload limit

if load_dotenv is not None:
    load_dotenv()

app.secret_key = os.getenv("FLASK_SECRET_KEY") or os.getenv("SECRET_KEY", "dev-only-change-me")

CSV_FILE = "questionbank.csv"
DB_FILE = "users.db"
OUTPUT_FOLDER = "output"
OUTPUT_FILE_REGULAR = os.path.join(OUTPUT_FOLDER, "AI_Question_Paper.docx")
OUTPUT_FILE_CIA = os.path.join(OUTPUT_FOLDER, "CIA_50_Question_Paper.docx")
OUTPUT_FILE_75 = os.path.join(OUTPUT_FOLDER, "Question_Paper_75.docx")
OUTPUT_FILE_PDF = os.path.join(OUTPUT_FOLDER, "Question_Paper.pdf")

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

SUBJECT_NAMES = {
    "CNCC": "Computer Networks and Cloud Computing",
    "CNS": "Computer Networks and Security",
    "MA": "Mobile Application"
}

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1").strip()
OPENAI_TIMEOUT = int(os.getenv("OPENAI_TIMEOUT", "30"))
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
try:
    GROQ_TEMPERATURE = float(os.getenv("GROQ_TEMPERATURE", "0.4"))
except ValueError:
    GROQ_TEMPERATURE = 0.4
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small").strip()
RAG_CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "900"))
RAG_CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "150"))
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "4"))

_EMBEDDER = None
_EMBEDDER_MODE = None
_RAG_CACHE = {}

# ---------- DATABASE INIT ----------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
    """)
    conn.commit()

    # Insert default accounts (only if missing)
    cur.execute("SELECT 1 FROM users WHERE username='professor1'")
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            ("professor1", "prof123", "professor")
        )

    cur.execute("SELECT 1 FROM users WHERE username='student1'")
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            ("student1", "stud123", "student")
        )

    conn.commit()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS exam_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            subject TEXT,
            pattern TEXT,
            started_at TEXT,
            submitted_at TEXT,
            answers_json TEXT
        )
        """
    )
    conn.commit()

    conn.close()

init_db()

@app.before_request
def auto_login_default_user():
    # Login page removed: keep a default session so protected routes work directly.
    if "user" not in session:
        session["user"] = "professor1"
        session["role"] = "professor"


def call_openai_chat(messages):
    if not OPENAI_API_KEY:
        return None, "OpenAI API key not configured"
    payload = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 400
    }
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=OPENAI_TIMEOUT
        )
        if resp.status_code != 200:
            return None, f"OpenAI API error: {resp.status_code} {resp.text}"
        data = resp.json()
        return data["choices"][0]["message"]["content"], None
    except requests.RequestException as exc:
        return None, f"Network error: {exc}"


def call_groq_chat(messages):
    if not GROQ_API_KEY:
        return None, "Groq API key not configured"
    try:
        from langchain_groq import ChatGroq
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    except Exception:
        return None, "langchain-groq not installed"

    try:
        lc_messages = []
        for msg in messages:
            role = str(msg.get("role", "")).strip().lower()
            content = str(msg.get("content", "")).strip()
            if not content:
                continue
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))
            else:
                lc_messages.append(HumanMessage(content=content))

        llm = ChatGroq(
            model=GROQ_MODEL,
            api_key=GROQ_API_KEY,
            temperature=max(0.0, min(1.0, GROQ_TEMPERATURE)),
        )
        response = llm.invoke(lc_messages)
        content = getattr(response, "content", "") or ""
        if isinstance(content, list):
            text = " ".join(
                item.get("text", "") for item in content if isinstance(item, dict)
            ).strip()
            return text, None
        return str(content).strip(), None
    except Exception as exc:
        return None, f"Groq error: {exc}"


def local_chat_reply(user_message):
    def format_response(title, qa_items, summary=None, subject=None, unit=None, topics=None):
        lines = [f"Title: {title}"]
        if subject:
            lines.append(f"Subject: {subject}")
        if unit is not None:
            lines.append(f"Unit: {unit}")
        if topics:
            lines.append("Key Topics:")
            for topic in topics:
                lines.append(f"- {topic}")
        lines.append("")
        lines.append("Questions:")
        for idx, qa in enumerate(qa_items, start=1):
            marks = qa.get("marks")
            mark_text = f" ({marks} Marks)" if marks else ""
            lines.append(f"Question {idx}{mark_text}")
            lines.append(qa["question"])
            lines.append("")
            lines.append("Answer:")
            lines.append(qa["answer"])
            lines.append("")
        if summary:
            lines.append("Summary:")
            lines.append(summary)
        return "\n".join(lines).strip()

    text = (user_message or "").strip()
    lower_text = text.lower()
    if not text:
        return format_response(
            title="Exam Prep Starter",
            qa_items=[
                {
                    "marks": 2,
                    "question": "What is network security?",
                    "answer": "Network security protects systems, services, and data from unauthorized access and attacks."
                },
                {
                    "marks": 5,
                    "question": "List five objectives of information security.",
                    "answer": "Confidentiality, integrity, availability, authentication, and non-repudiation."
                },
                {
                    "marks": 7,
                    "question": "Explain firewall and its role in a network.",
                    "answer": "A firewall filters incoming and outgoing traffic using rules. It blocks suspicious connections and allows trusted communication."
                },
                {
                    "marks": 10,
                    "question": "Describe common network threats and prevention methods.",
                    "answer": "Threats include phishing, malware, MITM, and DDoS. Prevention includes MFA, patching, segmentation, IDS/IPS, and user awareness."
                },
                {
                    "marks": 15,
                    "question": "Discuss layered network defense with practical examples.",
                    "answer": "Layered defense combines access control, encryption, endpoint security, monitoring, and incident response to reduce attack impact."
                },
            ],
            summary="Share a subject or upload notes, and I will generate questions, answers, and revision summaries from your material."
        )

    if any(word in lower_text for word in ["hi", "hello", "hey"]):
        return format_response(
            title="Welcome to Study Assistant",
            qa_items=[
                {
                    "question": "How can this assistant help me?",
                    "answer": "I can generate exam questions, answers, summaries, explanations, and model question papers from uploaded notes."
                }
            ],
            summary="Tell me a subject like CNS/CNCC/MA or upload a PDF to start."
        )

    if any(word in lower_text for word in ["generate", "paper", "question paper", "exam pattern"]):
        return format_response(
            title="Model Question Paper",
            qa_items=[
                {"marks": 2, "question": "Define computer network security.", "answer": "It is the practice of protecting network infrastructure and data from unauthorized access and attacks."},
                {"marks": 5, "question": "List types of firewalls.", "answer": "Packet filtering, stateful inspection, proxy firewall, and next-generation firewall."},
                {"marks": 7, "question": "Compare TCP and UDP.", "answer": "TCP is reliable and connection-oriented; UDP is faster, connectionless, and lightweight."},
                {"marks": 10, "question": "Explain VPN architecture and use cases.", "answer": "VPN creates encrypted tunnels over public networks for secure remote access and site-to-site communication."},
                {"marks": 15, "question": "Discuss SSL/TLS handshake with security properties.", "answer": "Handshake negotiates ciphers, authenticates server via certificates, establishes shared keys, then encrypts sessions."},
            ],
            summary="This pattern covers short, medium, and long-answer exam preparation."
        )

    topic_guides = {
        "tcp": "TCP is connection-oriented and reliable. It uses handshake, sequencing, acknowledgements, and flow control.",
        "udp": "UDP is connectionless and lightweight. It has low latency but no delivery guarantee.",
        "osi": "OSI has 7 layers: Physical, Data Link, Network, Transport, Session, Presentation, Application.",
        "dns": "DNS maps domain names to IP addresses using distributed name servers.",
        "cloud": "Cloud computing provides on-demand resources with scalability, elasticity, and pay-as-you-go pricing.",
        "firewall": "A firewall filters network traffic based on security rules to block unauthorized access.",
        "activity": "In Android, an Activity is a UI screen with lifecycle states like onCreate, onStart, onResume, onPause, onStop, onDestroy.",
        "apk": "APK is the Android package file format used to distribute and install Android apps.",
    }
    requested_topic = next((key for key in topic_guides if key in lower_text), None)

    subject_hint = detect_requested_subject(text)

    chapter_match = re.search(r"(chapter|unit)\s*[-:]?\s*(\d+)", lower_text)
    chapter_hint = int(chapter_match.group(2)) if chapter_match else None
    mark_match = re.search(r"(\d+)\s*[- ]?\s*mark", lower_text)
    mark_hint = int(mark_match.group(1)) if mark_match else None
    wants_answers = any(word in lower_text for word in ["answer", "answers", "explain", "explanation"])
    asks_definition = bool(re.search(r"^(what is|define|explain)\b", lower_text))

    wants_questions = any(
        word in lower_text for word in ["question", "questions", "give", "any", "important", "sample", "practice"]
    )

    tokens = [t for t in "".join(ch if ch.isalnum() else " " for ch in lower_text).split() if len(t) >= 3]
    rows = []
    try:
        with open(CSV_FILE, newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                q_text = str(row.get("question", "") or "").strip()
                subject = str(row.get("subject", "") or "").strip()
                chapter_raw = str(row.get("chapter", "") or "").strip()
                mark_raw = str(row.get("mark", "") or "").strip()
                if not q_text or not subject:
                    continue
                try:
                    chapter = int(chapter_raw)
                except ValueError:
                    chapter = None
                try:
                    mark = int(mark_raw)
                except ValueError:
                    mark = None
                rows.append(
                    {
                        "question": q_text,
                        "subject": subject,
                        "chapter": chapter,
                        "mark": mark,
                        "haystack": f"{q_text} {subject} chapter {chapter_raw} {mark_raw}".lower(),
                    }
                )
    except Exception:
        return (
            "I could not read the local question bank right now. "
            "You can still ask about study strategy, and I will guide you."
        )

    if requested_topic and not wants_questions:
        return format_response(
            title=f"{requested_topic.upper()} Concept Explanation",
            qa_items=[
                {
                    "question": f"Explain {requested_topic.upper()} in simple terms.",
                    "answer": topic_guides[requested_topic]
                }
            ],
            summary="Use this as a short-note answer. I can also provide 2/5/7/10/15 mark versions."
        )

    filtered = rows
    if subject_hint:
        if subject_hint in SUBJECT_NAMES:
            filtered = [row for row in filtered if row["subject"] == subject_hint]
        else:
            filtered = [row for row in filtered if subject_hint.lower() in str(row["subject"]).lower()]
    if chapter_hint is not None:
        filtered = [row for row in filtered if row["chapter"] == chapter_hint]
    if mark_hint is not None:
        filtered = [row for row in filtered if row["mark"] == mark_hint]

    scored = []
    token_pool = tokens + ([requested_topic] if requested_topic else [])
    for row in filtered:
        score = sum(1 for token in token_pool if token and token in row["haystack"])
        if wants_questions and score == 0 and (subject_hint or chapter_hint or mark_hint):
            score = 1
        if score > 0:
            scored.append((score, row))

    if not scored and wants_questions:
        # Fallback: provide a few examples even for generic asks like "give any questions"
        pool = filtered if filtered else rows
        scored = [(1, row) for row in pool[:5]]

    if not scored:
        if requested_topic:
            return format_response(
                title=f"{requested_topic.upper()} Revision",
                qa_items=[
                    {"question": f"What is {requested_topic.upper()}?", "answer": topic_guides[requested_topic]}
                ],
                summary=f"Focus on definition, working, and use-cases of {requested_topic.upper()}."
            )
        if asks_definition:
            topic_text = re.sub(r"^(what is|define|explain)\s+", "", text, flags=re.IGNORECASE).strip(" ?.:")
            if topic_text:
                concise = (
                    f"{topic_text} is a concept where core principles are applied to solve real-world problems. "
                    f"It typically involves definition, key components, working process, and practical applications."
                )
                return format_response(
                    title=f"{topic_text} - General Explanation",
                    qa_items=[
                        {
                            "question": f"What is {topic_text}?",
                            "answer": concise,
                        },
                        {
                            "question": f"Why is {topic_text} important?",
                            "answer": (
                                f"It is important because it improves efficiency, enables better decision-making, "
                                f"and is widely used in modern academic and industry scenarios."
                            ),
                        },
                    ],
                    summary=f"This is a general-knowledge explanation for {topic_text}. I can also give a 2/5/7/10/15 mark answer format."
                )
        if subject_hint:
            return format_response(
                title=f"{subject_hint} Important Questions and Answers",
                subject=subject_hint,
                unit=chapter_hint,
                topics=[
                    f"Fundamentals of {subject_hint}",
                    f"Important concepts in {subject_hint}",
                    f"Applications and examples in {subject_hint}",
                    f"Exam-focused revision points for {subject_hint}",
                ],
                qa_items=[
                    {
                        "marks": 2,
                        "question": f"What is {subject_hint}? Give a brief definition.",
                        "answer": f"{subject_hint} is a subject area that covers key concepts, terminology, and foundational principles required for exam understanding."
                    },
                    {
                        "marks": 5,
                        "question": f"Write short notes on one important topic in {subject_hint}.",
                        "answer": f"Introduce the selected {subject_hint} topic, list core points, and add one example relevant to the syllabus."
                    },
                    {
                        "marks": 7,
                        "question": f"Explain a major concept in {subject_hint} with key points.",
                        "answer": f"Start with definition, explain structure/workflow, include important terms, and conclude with practical relevance."
                    },
                    {
                        "marks": 10,
                        "question": f"Discuss the importance and applications of {subject_hint}.",
                        "answer": f"Explain why {subject_hint} matters, where it is applied, and how it helps in academic and real-world contexts."
                    },
                    {
                        "marks": 15,
                        "question": f"Write a detailed essay on a core unit of {subject_hint}.",
                        "answer": f"Provide introduction, concept explanation, examples, comparison points, and conclusion for a high-scoring long answer."
                    },
                ],
                summary="This is an auto-generated revision pack for quick exam preparation."
            )
        return format_response(
            title="General Exam Questions and Answers",
            qa_items=[
                {"marks": 2, "question": "What is network security?", "answer": "Network security protects systems, data, and communication channels from unauthorized access and attacks."},
                {"marks": 5, "question": "What is the role of a firewall?", "answer": "A firewall filters traffic using predefined rules to block suspicious or unauthorized access."},
                {"marks": 7, "question": "Differentiate TCP and UDP.", "answer": "TCP is reliable and connection-oriented. UDP is faster, connectionless, and has no delivery guarantee."},
                {"marks": 10, "question": "Explain DNS working with a practical flow.", "answer": "DNS resolves domain names to IP addresses through resolver, root, TLD, and authoritative name servers."},
                {"marks": 15, "question": "Discuss network attacks and defenses.", "answer": "Cover phishing, DDoS, malware, and MITM; defenses include MFA, IDS/IPS, encryption, patching, and monitoring."},
            ],
            summary="Upload your notes for file-specific questions and answers."
        )

    scored.sort(key=lambda item: item[0], reverse=True)
    top = scored[:5]
    qa_items = []
    for _, row in top:
        mark_value = row["mark"] if row["mark"] in {2, 5, 7, 10, 15} else mark_hint
        answer_text = (
            "Write definition, key points, and one example from the syllabus. "
            "Use concise bullets for short marks and structured paragraphs for long marks."
        )
        if wants_answers:
            answer_text = (
                "Detailed answer guide: start with definition, explain core mechanism, include keywords, "
                "and end with an application/example relevant to exams."
            )
        qa_items.append(
            {
                "marks": mark_value,
                "question": row["question"],
                "answer": answer_text,
            }
        )
    return format_response(
        title="Generated Questions and Answers from Question Bank",
        subject=subject_hint,
        unit=chapter_hint,
        qa_items=qa_items,
        summary="These are prioritized from your available question bank; I can expand any answer in detail."
    )


def _extract_docx_text(raw_bytes):
    texts = []
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as docx_zip:
        xml_data = docx_zip.read("word/document.xml")
    root = ET.fromstring(xml_data)
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] == "t" and node.text:
            value = node.text.strip()
            if value:
                texts.append(value)
    return "\n".join(texts)


def _extract_pptx_text(raw_bytes):
    texts = []
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as pptx_zip:
        slide_files = sorted(
            [name for name in pptx_zip.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml")]
        )
        for slide_name in slide_files:
            xml_data = pptx_zip.read(slide_name)
            root = ET.fromstring(xml_data)
            for node in root.iter():
                if node.tag.rsplit("}", 1)[-1] == "t" and node.text:
                    value = node.text.strip()
                    if value:
                        texts.append(value)
    return "\n".join(texts)


def _extract_pdf_text(raw_bytes):
    if PdfReader is None:
        return ""
    reader = PdfReader(io.BytesIO(raw_bytes))
    texts = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            texts.append(page_text.strip())
    return "\n".join(texts)


def extract_uploaded_file_texts(files):
    docs = []
    image_names = []
    other_files = []

    for uploaded in files:
        if not uploaded:
            continue
        filename = os.path.basename(uploaded.filename or "").strip() or "unnamed_file"
        mime_type = (uploaded.mimetype or mimetypes.guess_type(filename)[0] or "").lower()

        if mime_type.startswith("image/"):
            image_names.append(filename)
            continue

        raw = uploaded.read()
        lower_name = filename.lower()
        is_large_doc = lower_name.endswith((".docx", ".pptx", ".pdf"))
        byte_limit = 50000000 if is_large_doc else 2000000
        if len(raw) > byte_limit:
            other_files.append(f"{filename} (skipped: file too large)")
            continue

        text_value = ""
        if mime_type.startswith("text/") or lower_name.endswith((".txt", ".md", ".csv", ".json", ".py", ".html", ".css", ".js")):
            try:
                text_value = raw.decode("utf-8", errors="ignore").strip()
            except Exception:
                text_value = ""
        elif lower_name.endswith(".docx"):
            try:
                text_value = _extract_docx_text(raw)
            except Exception:
                text_value = ""
        elif lower_name.endswith(".pptx"):
            try:
                text_value = _extract_pptx_text(raw)
            except Exception:
                text_value = ""
        elif lower_name.endswith(".pdf"):
            try:
                text_value = _extract_pdf_text(raw)
            except Exception:
                text_value = ""
            if not text_value and PdfReader is None:
                other_files.append(f"{filename} (pdf parser not installed)")
                continue
        else:
            other_files.append(f"{filename} (type: {mime_type or 'unknown'})")
            continue

        cleaned = (text_value or "").strip()
        if not cleaned:
            other_files.append(f"{filename} (no readable text)")
            continue
        docs.append({"filename": filename, "text": cleaned})

    return docs, {
        "images": image_names,
        "others": other_files,
        "text_count": len(docs),
    }


def build_attachment_context(docs, attachment_meta):
    text_blocks = []
    other_files = list(attachment_meta.get("others", []))
    image_names = list(attachment_meta.get("images", []))
    max_chars_per_file = 6000
    max_total_chars = 12000
    total_chars = 0

    for item in docs:
        filename = item["filename"]
        snippet = item["text"][:max_chars_per_file]
        remaining = max_total_chars - total_chars
        if remaining <= 0:
            other_files.append(f"{filename} (skipped: text limit reached)")
            continue
        snippet = snippet[:remaining]
        total_chars += len(snippet)
        text_blocks.append(f"[File: {filename}]\n{snippet}")

    context_parts = []
    if text_blocks:
        context_parts.append(
            "Use the uploaded file content below as additional context:\n\n" + "\n\n".join(text_blocks)
        )
    if image_names:
        context_parts.append(
            "User uploaded image file(s): " + ", ".join(image_names) +
            ". Note: image OCR/vision is not enabled in this chatbot. Ask the user for the text from the image if needed."
        )
    if other_files:
        context_parts.append("Uploaded file metadata: " + ", ".join(other_files))

    attachment_meta["others"] = other_files
    attachment_meta["text_count"] = len(text_blocks)
    return "\n\n".join(context_parts)


def split_text_into_chunks(text, chunk_size=900, overlap=150):
    cleaned = re.sub(r"\s+\n", "\n", (text or "").strip())
    if not cleaned:
        return []
    chunk_size = max(200, int(chunk_size))
    overlap = max(0, min(int(overlap), chunk_size - 1))

    chunks = []
    start = 0
    text_len = len(cleaned)
    while start < text_len:
        end = min(start + chunk_size, text_len)
        piece = cleaned[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= text_len:
            break
        start = end - overlap
    return chunks


def _get_embedding_backend():
    global _EMBEDDER, _EMBEDDER_MODE
    if _EMBEDDER is not None and _EMBEDDER_MODE:
        return _EMBEDDER_MODE, _EMBEDDER, None

    try:
        from sentence_transformers import SentenceTransformer
        _EMBEDDER = SentenceTransformer("all-MiniLM-L6-v2")
        _EMBEDDER_MODE = "sentence-transformers"
        return _EMBEDDER_MODE, _EMBEDDER, None
    except Exception:
        pass

    if OPENAI_API_KEY:
        _EMBEDDER = OPENAI_EMBEDDING_MODEL
        _EMBEDDER_MODE = "openai"
        return _EMBEDDER_MODE, _EMBEDDER, None

    return None, None, "No embedding backend configured (install sentence-transformers or set OPENAI_API_KEY)"


def _embed_texts(texts):
    mode, backend, err = _get_embedding_backend()
    if err:
        return None, err

    if mode == "sentence-transformers":
        try:
            arr = backend.encode(
                texts,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False
            )
            return np.asarray(arr, dtype="float32"), None
        except Exception as exc:
            return None, f"Embedding error: {exc}"

    vectors = []
    try:
        for i in range(0, len(texts), 64):
            batch = texts[i:i + 64]
            resp = requests.post(
                "https://api.openai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"model": OPENAI_EMBEDDING_MODEL, "input": batch},
                timeout=OPENAI_TIMEOUT,
            )
            if resp.status_code != 200:
                return None, f"OpenAI embedding error: {resp.status_code} {resp.text}"
            data = resp.json().get("data", [])
            data = sorted(data, key=lambda item: item.get("index", 0))
            vectors.extend(item.get("embedding", []) for item in data)
        arr = np.asarray(vectors, dtype="float32")
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        arr = arr / norms
        return arr, None
    except Exception as exc:
        return None, f"Embedding network error: {exc}"


def build_rag_index(docs):
    try:
        import faiss
    except Exception:
        return None, "faiss-cpu not installed"

    all_chunks = []
    for item in docs:
        filename = item["filename"]
        chunks = split_text_into_chunks(item["text"], chunk_size=RAG_CHUNK_SIZE, overlap=RAG_CHUNK_OVERLAP)
        for idx, chunk in enumerate(chunks):
            all_chunks.append({"filename": filename, "chunk_id": idx, "text": chunk})

    if not all_chunks:
        return None, "No text chunks available"

    signature = hashlib.sha256(
        "\n".join(f"{c['filename']}::{c['chunk_id']}::{c['text']}" for c in all_chunks).encode("utf-8", errors="ignore")
    ).hexdigest()
    cached = _RAG_CACHE.get(signature)
    if cached:
        return cached, None

    embeddings, err = _embed_texts([item["text"] for item in all_chunks])
    if err:
        return None, err

    if embeddings.ndim != 2 or embeddings.shape[0] == 0:
        return None, "Invalid embeddings generated"

    embeddings = np.asarray(embeddings, dtype="float32")
    faiss.normalize_L2(embeddings)
    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)

    bundle = {"index": index, "chunks": all_chunks, "signature": signature}
    _RAG_CACHE[signature] = bundle
    return bundle, None


def retrieve_rag_context(query, rag_bundle, top_k=4):
    if not rag_bundle or not query.strip():
        return ""

    embeddings, err = _embed_texts([query.strip()])
    if err or embeddings is None or embeddings.shape[0] == 0:
        return ""

    query_vec = np.asarray(embeddings, dtype="float32")
    try:
        import faiss
        faiss.normalize_L2(query_vec)
    except Exception:
        pass

    index = rag_bundle["index"]
    chunks = rag_bundle["chunks"]
    k = max(1, min(int(top_k), index.ntotal))
    scores, ids = index.search(query_vec, k)
    hits = []
    for score, idx in zip(scores[0], ids[0]):
        if idx < 0 or idx >= len(chunks):
            continue
        if float(score) <= 0:
            continue
        chunk = chunks[idx]
        hits.append(
            f"[Source: {chunk['filename']} | chunk {chunk['chunk_id']} | score {float(score):.3f}]\n{chunk['text']}"
        )

    if not hits:
        return ""
    return "Use these retrieved chunks from uploaded documents as primary context:\n\n" + "\n\n".join(hits)


def retrieve_question_bank_context(query, top_k=5, requested_subject=None):
    text = (query or "").strip().lower()
    if not text:
        return ""

    tokens = [t for t in re.findall(r"[a-z0-9]+", text) if len(t) >= 3]
    if not tokens:
        return ""

    rows = []
    try:
        with open(CSV_FILE, newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                question = str(row.get("question", "") or "").strip()
                subject = str(row.get("subject", "") or "").strip()
                chapter = str(row.get("chapter", "") or "").strip()
                mark = str(row.get("mark", "") or "").strip()
                if not question:
                    continue
                if requested_subject:
                    subject_lower = subject.lower()
                    req_lower = requested_subject.lower()
                    full_name = SUBJECT_NAMES.get(requested_subject, "").lower() if requested_subject in SUBJECT_NAMES else ""
                    if req_lower not in subject_lower and (not full_name or full_name not in subject_lower):
                        continue
                haystack = f"{question} {subject} {chapter} {mark}".lower()
                score = sum(1 for token in tokens if token in haystack)
                if score > 0:
                    rows.append((score, subject, chapter, mark, question))
    except Exception:
        return ""

    if not rows:
        return ""

    rows.sort(key=lambda item: item[0], reverse=True)
    top = rows[:max(1, min(top_k, 8))]
    lines = ["Use this matching question bank context as secondary source after uploaded files:"]
    for score, subject, chapter, mark, question in top:
        lines.append(
            f"- [score={score}] Subject={subject or '-'} Unit={chapter or '-'} Marks={mark or '-'} | {question}"
        )
    return "\n".join(lines)


def detect_requested_subject(user_message, docs=None):
    text = (user_message or "").strip()
    lower = text.lower()
    if not text:
        text = ""

    for code, name in SUBJECT_NAMES.items():
        if code.lower() in lower or name.lower() in lower:
            return code

    subject_match = re.search(r"([a-zA-Z][a-zA-Z\s]{1,30})\s+subject", text, re.IGNORECASE)
    if subject_match:
        return subject_match.group(1).strip().title()

    if re.fullmatch(r"[A-Za-z]{2,20}", text):
        return text.upper() if text.upper() in SUBJECT_NAMES else text.title()

    generic_subjects = ["tamil", "english", "mathematics", "maths", "physics", "chemistry", "biology", "history"]
    for item in generic_subjects:
        if item in lower:
            return item.title()

    if docs:
        for doc in docs:
            content = (doc.get("text", "") or "")[:4000]
            m = re.search(r"\bsubject\s*:\s*([^\n\r]+)", content, re.IGNORECASE)
            if m:
                return m.group(1).strip().split("|")[0].strip().title()
    return None


def build_file_based_qa_fallback(docs, requested_subject=None, min_items=5):
    if not docs:
        return ""

    topics = []
    for doc in docs:
        lines = [line.strip() for line in (doc.get("text", "") or "").splitlines()]
        for line in lines:
            cleaned = re.sub(r"^[\-\*\d\.\)\(]+\s*", "", line).strip()
            cleaned = re.sub(r"\s+", " ", cleaned)
            if len(cleaned) < 8 or len(cleaned) > 140:
                continue
            if not re.search(r"[A-Za-z]", cleaned):
                continue
            if cleaned.lower() in {item.lower() for item in topics}:
                continue
            topics.append(cleaned)
            if len(topics) >= 12:
                break
        if len(topics) >= 12:
            break

    if not topics:
        return ""

    marks_cycle = [2, 5, 7, 10, 15]
    selected = topics[:max(min_items, 5)]
    title_subject = requested_subject or "Uploaded Notes"
    lines = [f"Title: {title_subject} - Questions from Uploaded File", "Questions:"]
    for idx, topic in enumerate(selected, start=1):
        marks = marks_cycle[(idx - 1) % len(marks_cycle)]
        if marks == 2:
            question = f"What is {topic}?"
        elif marks == 5:
            question = f"Write short notes on {topic}."
        elif marks == 7:
            question = f"Explain {topic} with key points."
        elif marks == 10:
            question = f"Discuss the significance of {topic}."
        else:
            question = f"Describe {topic} in detail with examples."
        lines.append(f"Question {idx} ({marks} Marks)")
        lines.append(question)
        lines.append("")

    lines.append("Answers:")
    for idx, topic in enumerate(selected, start=1):
        marks = marks_cycle[(idx - 1) % len(marks_cycle)]
        lines.append(f"Answer {idx}")
        lines.append(
            f"From the uploaded notes, {topic} is an important concept. "
            f"For a {marks}-mark answer, include definition, key points, and one relevant example from the notes."
        )
        lines.append("")
    lines.append("Summary:")
    lines.append("Questions are generated directly from uploaded file content and aligned to exam mark patterns.")
    return "\n".join(lines).strip()


def local_attachment_reply(user_message, attachment_context, attachment_meta):
    if not attachment_context or int(attachment_meta.get("text_count", 0)) <= 0:
        return None

    file_sections = []
    file_markers = list(re.finditer(r"\[File:\s*(.*?)\]\n", attachment_context))
    for idx, marker in enumerate(file_markers):
        filename = (marker.group(1) or "").strip() or "uploaded_file"
        start = marker.end()
        end = file_markers[idx + 1].start() if idx + 1 < len(file_markers) else len(attachment_context)
        section = (attachment_context[start:end] or "").strip()
        if section:
            file_sections.append((filename, section))

    if not file_sections:
        return None

    stopwords = {
        "the", "and", "for", "with", "from", "that", "this", "what", "when", "where",
        "which", "have", "about", "please", "could", "would", "there", "their", "your",
        "into", "just", "need", "want", "show", "tell", "give", "make"
    }
    message_tokens = [
        t for t in re.findall(r"[a-z0-9]+", (user_message or "").lower())
        if len(t) >= 3 and t not in stopwords
    ]

    ranked = []
    for filename, section in file_sections:
        lines = [line.strip() for line in section.splitlines() if line.strip()]
        best_line = lines[0] if lines else section[:200]
        best_score = 0

        if message_tokens:
            for line in lines[:60]:
                line_lower = line.lower()
                score = sum(1 for token in message_tokens if token in line_lower)
                if score > best_score:
                    best_score = score
                    best_line = line

        ranked.append((best_score, filename, best_line))

    ranked.sort(key=lambda item: item[0], reverse=True)
    strong_matches = [item for item in ranked if item[0] > 0][:3]

    if strong_matches:
        marks_cycle = [2, 5, 7]
        lines = ["Title: Questions from Uploaded File", "Questions:"]
        for idx, (_, filename, excerpt) in enumerate(strong_matches, start=1):
            marks = marks_cycle[(idx - 1) % len(marks_cycle)]
            lines.append(f"Question {idx} ({marks} Marks)")
            lines.append(f"Explain: {excerpt[:180]}")
            lines.append("")
        lines.append("Answers:")
        for idx, (_, filename, excerpt) in enumerate(strong_matches, start=1):
            lines.append(f"Answer {idx}")
            lines.append(
                f"From {filename}, this topic highlights: {excerpt[:220]}. "
                "Write the answer with definition, key points, and one example from the note."
            )
            lines.append("")
        lines.append("Summary:")
        lines.append("Generated directly from uploaded file content.")
        return "\n".join(lines)

    preview = ranked[0][2][:220]
    return (
        "Title: Uploaded File Quick Revision\n"
        "Questions:\n"
        "Question 1 (2 Marks)\n"
        f"What is the meaning of: {preview[:120]}?\n\n"
        "Question 2 (5 Marks)\n"
        f"Write short notes on: {preview[:120]}.\n\n"
        "Answers:\n"
        "Answer 1\n"
        f"The uploaded notes describe this concept as: {preview}.\n\n"
        "Answer 2\n"
        f"Based on the file content, explain the definition, key points, and use-case of: {preview[:120]}.\n\n"
        "Summary:\n"
        "Generated from uploaded file text."
    )

# ---------- AI LOGIC FUNCTIONS ----------

# ---------- ROUTES ----------
@app.route("/")
def login():
    return redirect("/dashboard")

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")
    return render_template("dashboard.html", user=session["user"], role=session["role"])

@app.route("/generate", methods=["GET", "POST"])
def generate():
    if "user" not in session:
        return redirect("/")

    if session.get("role") not in ["professor", "student"]:
        return "Access Denied: Invalid role"

    subject = None
    pattern = "regular"
    if request.method == "POST":
        subject = request.form.get("subject")
        pattern = request.form.get("pattern", "regular")
        config = GeneratorConfig.from_form(request.form)
    else:
        subject = request.args.get("subject")
        pattern = request.args.get("pattern", "regular")
        config = GeneratorConfig.from_form(request.args)

    # Open the generator form when no subject has been selected yet.
    if not subject:
        return render_template("generate.html", subjects=SUBJECT_NAMES.keys())

    if subject not in SUBJECT_NAMES:
        return "Invalid subject selected", 400
    if pattern not in ["regular", "cia50", "75"]:
        return "Invalid pattern selected", 400

    questions = get_questions(CSV_FILE, subject, SUBJECT_NAMES[subject], pattern, config)
    status = request.args.get("status")
    return render_template(
        "preview.html",
        questions=questions,
        subject=subject,
        pattern=pattern,
        status=status,
        config=config
    )

@app.route("/download", methods=["GET", "POST"])
def download():
    if "user" not in session:
        return redirect("/")

    if session.get("role") not in ["professor", "student"]:
        return "Access Denied"

    if request.method == "POST":
        subject = request.form.get("subject")
        pattern = request.form.get("pattern", "regular")
        edited_payload = request.form.get("edited_questions", "")
        custom_header = request.form.get("custom_header", "").strip()
        custom_footer = request.form.get("custom_footer", "").strip()
        output_format = request.form.get("output_format", "docx")
        config = GeneratorConfig.from_form(request.form)
    else:
        subject = request.args.get("subject")
        pattern = request.args.get("pattern", "regular")
        edited_payload = ""
        custom_header = request.args.get("custom_header", "").strip()
        custom_footer = request.args.get("custom_footer", "").strip()
        output_format = request.args.get("output_format", "docx")
        config = GeneratorConfig.from_form(request.args)

    if subject not in SUBJECT_NAMES:
        return "Invalid subject selected", 400
    if pattern not in ["regular", "cia50", "75"]:
        return "Invalid pattern selected", 400
    if output_format not in ["docx", "pdf"]:
        return "Invalid output format", 400

    # If preview edits are provided, generate from edited preview data.
    if edited_payload:
        try:
            edited_items = json.loads(edited_payload)
            questions = get_questions(CSV_FILE, subject, SUBJECT_NAMES[subject], pattern, config)
            questions = apply_preview_edits(questions, edited_items)
            if output_format == "pdf":
                output_file = generate_pdf_from_questions(
                    SUBJECT_NAMES[subject],
                    pattern,
                    questions,
                    OUTPUT_FILE_PDF,
                    session.get("user", "system"),
                    custom_header,
                    custom_footer,
                )
                download_name = build_download_name(SUBJECT_NAMES[subject], pattern).replace(".docx", ".pdf")
                return send_file(
                    output_file,
                    as_attachment=True,
                    download_name=download_name,
                    mimetype="application/pdf"
                )
            else:
                output_docx = OUTPUT_FILE_REGULAR
                if pattern == "cia50":
                    output_docx = OUTPUT_FILE_CIA
                elif pattern == "75":
                    output_docx = OUTPUT_FILE_75
                output_file = generate_question_paper_from_data(
                    SUBJECT_NAMES[subject],
                    pattern,
                    questions,
                    session.get("user", "system"),
                    output_docx,
                    custom_header,
                    custom_footer,
                )
                download_name = build_download_name(SUBJECT_NAMES[subject], pattern)
            return send_file(output_file, as_attachment=True, download_name=download_name)
        except json.JSONDecodeError:
            return "Invalid edited question payload", 400

    questions = get_questions(CSV_FILE, subject, SUBJECT_NAMES[subject], pattern, config)
    if output_format == "pdf":
        output_file = generate_pdf_from_questions(
            SUBJECT_NAMES[subject],
            pattern,
            questions,
            OUTPUT_FILE_PDF,
            session.get("user", "system"),
            custom_header,
            custom_footer,
        )
        download_name = build_download_name(SUBJECT_NAMES[subject], pattern).replace(".docx", ".pdf")
        return send_file(
            output_file,
            as_attachment=True,
            download_name=download_name,
            mimetype="application/pdf"
        )
    else:
        output_docx = OUTPUT_FILE_REGULAR
        if pattern == "cia50":
            output_docx = OUTPUT_FILE_CIA
        elif pattern == "75":
            output_docx = OUTPUT_FILE_75
        output_file = generate_question_paper_from_data(
            SUBJECT_NAMES[subject],
            pattern,
            questions,
            session.get("user", "system"),
            output_docx,
            custom_header,
            custom_footer,
        )
        download_name = build_download_name(SUBJECT_NAMES[subject], pattern)

    return send_file(output_file, as_attachment=True, download_name=download_name)

@app.route("/admin/questions")
def manage_questions():
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "professor":
        return "Access Denied: Only professors can manage question bank"

    status = request.args.get("status")
    edit_id = request.args.get("edit_id", type=int)
    questions = get_question_bank_rows(CSV_FILE)
    edit_question = get_question_by_id(CSV_FILE, edit_id) if edit_id else None
    return render_template(
        "manage_questions.html",
        questions=questions,
        status=status,
        edit_question=edit_question
    )

@app.route("/admin/add_question", methods=["POST"])
def add_question():
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "professor":
        return "Access Denied: Only professors can add questions"

    subject = request.form.get("subject", "").strip()
    question_text = request.form.get("question_text", "").strip()

    try:
        chapter = int(request.form.get("chapter", 0))
        mark = int(request.form.get("mark", 0))
    except ValueError:
        return "Invalid chapter or marks value", 400

    if subject not in SUBJECT_NAMES:
        return "Invalid subject selected", 400
    if chapter not in [1, 2, 3, 4, 5]:
        return "Chapter must be between 1 and 5", 400
    if mark not in [2, 7, 15]:
        return "Invalid marks selected", 400
    if not question_text:
        return "Question text is required", 400

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([chapter, question_text, mark, subject, "manual", "-"])

    next_url = request.form.get("next", "").strip()
    if next_url and next_url.startswith("/"):
        joiner = "&" if "?" in next_url else "?"
        return redirect(f"{next_url}{joiner}status=added")

    return redirect("/admin/questions?status=added")

@app.route("/admin/edit_question", methods=["POST"])
def edit_question():
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "professor":
        return "Access Denied: Only professors can edit questions"

    try:
        question_id = int(request.form.get("id", 0))
        chapter = int(request.form.get("chapter", 0))
        mark = int(request.form.get("mark", 0))
    except ValueError:
        return "Invalid input values", 400

    subject = request.form.get("subject", "").strip()
    question_text = request.form.get("question_text", "").strip()

    if question_id <= 0:
        return "Invalid question ID", 400
    if subject not in SUBJECT_NAMES:
        return "Invalid subject selected", 400
    if chapter not in [1, 2, 3, 4, 5]:
        return "Chapter must be between 1 and 5", 400
    if mark not in [2, 7, 15]:
        return "Invalid marks selected", 400
    if not question_text:
        return "Question text is required", 400

    updated = update_question_in_csv(CSV_FILE, question_id, subject, chapter, mark, question_text)
    if not updated:
        return "Question not found", 404

    return redirect("/admin/questions?status=updated")

@app.route("/admin/ai_generate", methods=["POST"])
def ai_generate():
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "professor":
        return "Access Denied: Only professors can generate AI questions"

    subject = request.form.get("subject", "").strip()
    try:
        chapter = int(request.form.get("chapter", 0))
        mark = int(request.form.get("mark", 0))
        count = int(request.form.get("count", 0))
    except ValueError:
        return "Invalid input values", 400

    if subject not in SUBJECT_NAMES:
        return "Invalid subject selected", 400
    if chapter not in [1, 2, 3, 4, 5]:
        return "Chapter must be between 1 and 5", 400
    if mark not in [2, 7, 15]:
        return "Invalid marks selected", 400
    if count <= 0 or count > 20:
        return "Count must be between 1 and 20", 400

    generated = ai_generate_questions(CSV_FILE, subject, chapter, mark, count)
    rows = [(chapter, q, mark, subject, "ai", "-") for q in generated]
    append_questions_to_csv(CSV_FILE, rows)

    return redirect("/admin/questions?status=added")

@app.route("/exam", methods=["GET", "POST"])
def exam():
    if "user" not in session:
        return redirect("/")
    if session.get("role") not in ["professor", "student"]:
        return "Access Denied"

    if request.method == "POST":
        subject = request.form.get("subject")
        pattern = request.form.get("pattern", "regular")
        config = GeneratorConfig.from_form(request.form)
        if subject not in SUBJECT_NAMES:
            return "Invalid subject selected", 400
        if pattern not in ["regular", "cia50", "75"]:
            return "Invalid pattern selected", 400
        questions = get_questions(CSV_FILE, subject, SUBJECT_NAMES[subject], pattern, config)
        started_at = datetime.now().isoformat(timespec="seconds")
        return render_template(
            "exam.html",
            questions=questions,
            subject=subject,
            pattern=pattern,
            started_at=started_at,
            config=config
        )

    return render_template("exam_start.html", subjects=SUBJECT_NAMES.keys())

@app.route("/exam/submit", methods=["POST"])
def submit_exam():
    if "user" not in session:
        return redirect("/")
    if session.get("role") not in ["professor", "student"]:
        return "Access Denied"

    subject = request.form.get("subject")
    pattern = request.form.get("pattern")
    started_at = request.form.get("started_at")
    answers = {}
    for key, value in request.form.items():
        if key.startswith("answer_"):
            answers[key] = value

    submitted_at = datetime.now().isoformat(timespec="seconds")
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO exam_submissions (username, subject, pattern, started_at, submitted_at, answers_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (session.get("user"), subject, pattern, started_at, submitted_at, json.dumps(answers))
    )
    conn.commit()
    conn.close()

    return render_template("exam_submitted.html", subject=subject, pattern=pattern, submitted_at=submitted_at)

@app.route("/admin/exam_submissions")
def exam_submissions():
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "professor":
        return "Access Denied: Only professors can view submissions"

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, username, subject, pattern, started_at, submitted_at FROM exam_submissions ORDER BY id DESC"
    )
    rows = cur.fetchall()
    conn.close()
    submissions = [
        {
            "id": r[0],
            "username": r[1],
            "subject": r[2],
            "pattern": r[3],
            "started_at": r[4],
            "submitted_at": r[5],
        }
        for r in rows
    ]
    return render_template("exam_results.html", submissions=submissions)


@app.route("/admin/exam_submissions/<int:submission_id>/edit", methods=["GET", "POST"])
def edit_exam_submission(submission_id):
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "professor":
        return "Access Denied: Only professors can edit submissions"

    error = None
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    if request.method == "POST":
        subject = request.form.get("subject", "").strip()
        pattern = request.form.get("pattern", "").strip()
        started_at = request.form.get("started_at", "").strip()
        submitted_at = request.form.get("submitted_at", "").strip()
        answers_raw = request.form.get("answers_json", "").strip() or "{}"

        try:
            parsed_answers = json.loads(answers_raw)
            if not isinstance(parsed_answers, dict):
                raise ValueError("Answers must be a JSON object")
        except Exception:
            error = "Answers JSON is invalid. Please provide a valid JSON object."
            submission = {
                "id": submission_id,
                "subject": subject,
                "pattern": pattern,
                "started_at": started_at,
                "submitted_at": submitted_at,
                "answers_json": answers_raw,
            }
            conn.close()
            return render_template("exam_submission_edit.html", submission=submission, error=error)

        cur.execute(
            """
            UPDATE exam_submissions
            SET subject = ?, pattern = ?, started_at = ?, submitted_at = ?, answers_json = ?
            WHERE id = ?
            """,
            (subject, pattern, started_at, submitted_at, json.dumps(parsed_answers), submission_id),
        )
        conn.commit()
        updated = cur.rowcount
        conn.close()
        if updated == 0:
            return "Submission not found", 404
        return redirect("/admin/exam_submissions")

    cur.execute(
        """
        SELECT id, username, subject, pattern, started_at, submitted_at, answers_json
        FROM exam_submissions
        WHERE id = ?
        """,
        (submission_id,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return "Submission not found", 404

    try:
        answers_json = json.dumps(json.loads(row[6] or "{}"), indent=2)
    except Exception:
        answers_json = row[6] or "{}"

    submission = {
        "id": row[0],
        "username": row[1],
        "subject": row[2],
        "pattern": row[3],
        "started_at": row[4],
        "submitted_at": row[5],
        "answers_json": answers_json,
    }
    return render_template("exam_submission_edit.html", submission=submission, error=error)


@app.route("/admin/exam_submissions/<int:submission_id>/delete", methods=["POST"])
def delete_exam_submission(submission_id):
    if "user" not in session:
        return redirect("/")
    if session.get("role") != "professor":
        return "Access Denied: Only professors can delete submissions"

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM exam_submissions WHERE id = ?", (submission_id,))
    conn.commit()
    conn.close()
    return redirect("/admin/exam_submissions")

@app.route("/chatbot")
@app.route("/chatbot-mockup")
def chatbot_mockup():
    return render_template("chatbot_mockup.html")


@app.route("/chat", methods=["POST"])
def chat():
    files = []
    docs = []
    rag_bundle = None
    rag_error = None
    requested_subject = None
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        user_message = str(payload.get("message", "")).strip()
        history = payload.get("history", [])
    else:
        payload = request.form
        user_message = str(payload.get("message", "")).strip()
        files = request.files.getlist("attachments")
        history_raw = payload.get("history", "[]")
        try:
            history = json.loads(history_raw)
        except Exception:
            history = []

    attachment_context = ""
    attachment_meta = {"images": [], "others": [], "text_count": 0}
    if files:
        docs, attachment_meta = extract_uploaded_file_texts(files)
        attachment_context = build_attachment_context(docs, attachment_meta)
        rag_bundle, rag_error = build_rag_index(docs)
    requested_subject = detect_requested_subject(user_message, docs=docs)

    if not user_message and files:
        user_message = "Analyze uploaded attachments."

    if not user_message and not files:
        return jsonify(
            {
                "status": "error",
                "message": "Please type a topic/subject or upload notes, and I will generate questions, answers, and summaries.",
                "data": {},
            }
        ), 400

    messages = [
        {
            "role": "system",
            "content": (
                "You are an intelligent AI assistant designed for an educational Question Paper Generator system.\n\n"
                "Your purpose is to help students and teachers generate questions, answers, summaries, and explanations from uploaded study materials or from general knowledge.\n\n"
                "You must behave like ChatGPT: intelligent, helpful, conversational, and capable of understanding user intent.\n\n"
                "--------------------------------\n"
                "KNOWLEDGE SOURCES\n"
                "--------------------------------\n\n"
                "You have three knowledge sources. Always follow this priority order:\n\n"
                "1. Uploaded files (PDF, DOCX, TXT)\n"
                "2. Question bank database\n"
                "3. General knowledge\n\n"
                "--------------------------------\n"
                "FILE UNDERSTANDING\n"
                "--------------------------------\n\n"
                "When a user uploads a file:\n\n"
                "1. Read the entire file content.\n"
                "2. Detect headings, unit titles, keywords, and important concepts.\n"
                "3. Use these topics to generate exam-style questions and answers.\n\n"
                "If the user asks:\n"
                "\"give question from this file\"\n\n"
                "You must:\n"
                "• Extract topics from the uploaded document\n"
                "• Generate at least 5 meaningful exam questions\n"
                "• Provide clear answers from the document\n\n"
                "Never generate placeholder questions such as:\n"
                "\"Explain the main concept shown above.\"\n\n"
                "Always generate real exam questions.\n\n"
                "--------------------------------\n"
                "QUESTION GENERATION RULES\n"
                "--------------------------------\n\n"
                "Generate questions in standard exam formats.\n\n"
                "Marks types:\n"
                "• 2 marks\n"
                "• 5 marks\n"
                "• 7 marks\n"
                "• 10 marks\n"
                "• 15 marks\n\n"
                "Example format:\n\n"
                "Title: Unit 1 Important Questions\n\n"
                "Question 1 (2 Marks)\n"
                "What is network security?\n\n"
                "Answer\n"
                "Network security refers to protecting computer networks and data from unauthorized access and attacks.\n\n"
                "Question 2 (7 Marks)\n"
                "Explain firewall with diagram.\n\n"
                "Answer\n"
                "A firewall is a network security system that monitors and controls incoming and outgoing network traffic based on predefined rules.\n\n"
                "--------------------------------\n"
                "SUBJECT DETECTION\n"
                "--------------------------------\n\n"
                "Always detect the subject mentioned by the user.\n\n"
                "Example:\n\n"
                "User: Tamil subject give questions\n\n"
                "You must generate Tamil questions.\n\n"
                "Never return questions from unrelated subjects like Android or networking.\n\n"
                "--------------------------------\n"
                "INTELLIGENT RESPONSE\n"
                "--------------------------------\n\n"
                "If the user's message is short, infer the likely intent.\n\n"
                "Example:\n\n"
                "User: \"CNS\"\n\n"
                "Respond with:\n"
                "• Important questions\n"
                "• Key topics\n"
                "• Short summary\n\n"
                "--------------------------------\n"
                "OUT-OF-SYLLABUS QUESTIONS\n"
                "--------------------------------\n\n"
                "If a question is not in the uploaded file or question bank:\n\n"
                "You must answer using general knowledge.\n\n"
                "Never say:\n"
                "\"Question not found.\"\n\n"
                "Instead give a helpful explanation.\n\n"
                "--------------------------------\n"
                "CONVERSATION STYLE\n"
                "--------------------------------\n\n"
                "Behave like ChatGPT:\n\n"
                "• Friendly and helpful\n"
                "• Clear explanations\n"
                "• Structured answers\n"
                "• Use headings and bullet points\n\n"
                "--------------------------------\n"
                "GOAL\n"
                "--------------------------------\n\n"
                "Help students prepare for exams by:\n\n"
                "• Generating questions\n"
                "• Providing answers\n"
                "• Summarizing notes\n"
                "• Explaining topics\n"
                "• Creating model question papers\n\n"
                "Always produce meaningful educational responses based on the best available knowledge source."
            ),
        }
    ]
    safe_history = []
    if isinstance(history, list):
        for item in history[-8:]:
            role = item.get("role")
            content = item.get("content")
            if role in ["user", "assistant"] and content:
                safe_history.append({"role": role, "content": str(content).strip()})
    effective_user_content = user_message
    rag_context = retrieve_rag_context(user_message, rag_bundle, top_k=RAG_TOP_K) if rag_bundle else ""
    qb_context = ""
    if not docs:
        qb_context = retrieve_question_bank_context(user_message, top_k=5, requested_subject=requested_subject)
    if rag_context:
        effective_user_content = (
            f"{user_message}\n\n{rag_context}\n\n"
            f"Requested subject: {requested_subject or 'Not specified'}\n"
            "Use uploaded file content only for this turn."
        )
    elif attachment_context or qb_context:
        parts = [user_message]
        if attachment_context:
            parts.append(attachment_context)
        if qb_context:
            parts.append(qb_context)
        parts.append(f"Requested subject: {requested_subject or 'Not specified'}")
        parts.append("Answer by priority: uploaded file content, then question bank, then general knowledge.")
        effective_user_content = "\n\n".join(parts)
    elif requested_subject:
        effective_user_content = (
            f"{user_message}\n\nRequested subject: {requested_subject}\n"
            "If no relevant question bank content exists, answer with general knowledge for this subject."
        )

    if safe_history and safe_history[-1]["role"] == "user":
        if safe_history[-1]["content"].lower() == user_message.lower():
            safe_history = safe_history[:-1]
    messages.extend(safe_history)
    messages.append({"role": "user", "content": effective_user_content})

    reply, error = call_groq_chat(messages)
    mode = "groq"
    if error or not reply:
        groq_error = error or "empty Groq response"
        reply, error = call_openai_chat(messages)
        mode = "openai"
    if error or not reply:
        fallback = ""
        if docs:
            fallback = build_file_based_qa_fallback(docs, requested_subject=requested_subject, min_items=5)
        if not fallback:
            fallback = local_attachment_reply(user_message, attachment_context, attachment_meta)
        if not fallback:
            fallback = local_chat_reply(user_message)
        return jsonify(
            {
                "status": "success",
                "message": "fallback",
                "data": {
                    "reply": fallback,
                    "mode": "fallback",
                    "reason": groq_error if "groq_error" in locals() else error,
                    "attachments": attachment_meta,
                    "rag": {
                        "enabled": bool(rag_bundle),
                        "error": rag_error,
                    },
                },
            }
        )

    return jsonify(
        {
            "status": "success",
            "message": "",
            "data": {
                "reply": reply,
                "mode": mode,
                "attachments": attachment_meta,
                "rag": {
                    "enabled": bool(rag_bundle),
                    "error": rag_error,
                },
            },
        }
    )


@app.errorhandler(RequestEntityTooLarge)
def handle_too_large(_error):
    return jsonify(
        {
            "status": "error",
            "message": "Uploaded file is too large. Max allowed size is 60 MB.",
            "data": {},
        }
    ), 413

if __name__ == "__main__":
    app.run(debug=True)
