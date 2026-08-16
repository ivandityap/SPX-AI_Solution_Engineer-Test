# Technical AI Engineer Test — Submission

## 🎥 Demo Video
[Link to video walkthrough](https://drive.google.com/file/d/1ApInSxrzUmRj7ipjXHcAU5Xd5TVz6SbD/view?usp=sharing)

## Overview
This repo contains my submission for the Technical AI Engineer Test: five written knowledge-question answers and five coding tasks, covering CSV processing at scale, a self-deployed vector database with a hand-implemented cosine similarity function, and a full receipt-scanning AI assistant (OCR → LLM structuring → SQLite → tool-calling agent), containerized and built via CI/CD.

## Repository Structure

| Path | Contents |
|---|---|
| `Engineering_Knowledge_Answer.md` | Written answers to the 5 knowledge questions |
| `Coding-01.ipynb` | Small CSV (100k rows) exploration notebook — pandas + seaborn |
| `Coding-02.ipynb` | Large CSV (2M rows) low-memory streaming parser — raw `csv` module |
| `Coding-03.md` | Written explanation: small vs. large file approach, memory tradeoffs |
| `Coding-04.ipynb` | Self-deployed Milvus (Docker Compose) + hand-written cosine similarity, validated against Milvus's native search |
| `Coding05-UI/` | Full receipt assistant platform — Streamlit UI, OCR, LLM-based structuring, SQLite storage, tool-calling agent, Dockerfile |
| `.github/workflows/ci.yml` | CI/CD pipeline — builds the platform's Docker image on every push |

## Tech Stack
- **Language:** Python 3.12
- **Data processing:** pandas, seaborn, Python's built-in `csv` module (streaming)
- **Vector DB:** Milvus (self-hosted via Docker Compose), `sentence-transformers` for embeddings
- **OCR:** Tesseract (`pytesseract`), Indonesian + English language packs
- **LLM:** Google Gemini (`google-genai`) — receipt structuring and the natural-language query agent (tool-calling)
- **Storage:** SQLite (via Streamlit's `st.connection`)
- **UI:** Streamlit
- **Containerization:** Docker
- **CI/CD:** GitHub Actions

## Running the Platform (`Coding05-UI/`)

### Local (without Docker)
```bash
cd Coding05-UI
pip install -r requirements.txt
```
Create a `.env` file in `Coding05-UI/` with:
```
GEMINI_API_KEY=your_key_here
```
Then run:
```bash
streamlit run app.py
```

### Via Docker
```bash
docker build -t receipt-agent ./Coding05-UI
docker run -p 8501:8501 --env-file ./Coding05-UI/.env receipt-agent
```
Visit `http://localhost:8501`.

## Running the Vector DB (`vector-db/`)
```bash
cd vector-db
docker compose up -d
```
Then open and run the notebook — it embeds a sample document set, inserts into Milvus, and validates a hand-written cosine similarity function against Milvus's native search results.
