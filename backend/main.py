import os
import json
import tempfile
import uuid
import fitz  # PyMuPDF
import base64
import logging
import time
import asyncio  # Added for parallel execution
from typing import List, Dict, Any, Optional, Literal
from contextlib import asynccontextmanager
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# --- Unstructured, LangChain, and Serper Imports ---
from unstructured.partition.pdf import partition_pdf
from unstructured.chunking.title import chunk_by_title
from langchain_core.documents import Document
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_core.messages import HumanMessage
from langchain_pinecone import PineconeVectorStore
from langchain_community.utilities import GoogleSerperAPIWrapper
from pydantic import BaseModel as V1BaseModel, Field
import pinecone

# --- Load Environment Variables ---
load_dotenv()

# --- Logging Configuration ---
# Replaces all print() statements for better tracking
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Pinecone Configuration ---
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
PINECONE_INDEX_NAME = "multimodal-rag-index" 
if not PINECONE_API_KEY:
    logger.error("PINECONE_API_KEY not found in environment variables")
    raise ValueError("PINECONE_API_KEY not found in environment variables")

# --- Serper API Configuration ---
SERPER_API_KEY = os.environ.get("SERPER_API_KEY")
if not SERPER_API_KEY:
    logger.error("SERPER_API_KEY not found in environment variables")
    raise ValueError("SERPER_API_KEY not found in environment variables")

# --- Global Inits ---
pc = pinecone.Pinecone(api_key=PINECONE_API_KEY)
embeddings = GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-001",
    google_api_key=os.environ.get("GEMINI_API_KEY"),
    output_dimensionality=2048
)
vectorstore = None
# Ensure LLM is async-capable (ChatOpenAI is)
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash-lite",
    temperature=0,
    google_api_key=os.environ.get("GEMINI_API_KEY")
)
web_search_tool = GoogleSerperAPIWrapper()

# Session storage
global_document_storage: Dict[str, Dict[str, Any]] = {}


# --- Document Processing Functions ---
def partition_document(file_path: str):
    logger.info(f"📄 Partitioning document: {file_path}")
    try:
        elements = partition_pdf(
            filename=file_path, 
            strategy="hi_res", 
            infer_table_structure=True, 
            extract_image_block_types=["Image"], 
            extract_image_block_to_payload=True
        )
        logger.info(f"✅ Extracted {len(elements)} elements")
        return elements
    except Exception as e:
        logger.error(f"❌ Failed to partition document {file_path}: {e}")
        raise

def extract_page_images(file_path: str) -> List[str]:
    logger.info("🖼️ Extracting page images...")
    page_images_b64 = []
    try:
        doc = fitz.open(file_path)
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(dpi=150) 
            img_bytes = pix.tobytes("png")
            img_b64 = base64.b64encode(img_bytes).decode('utf-8')
            page_images_b64.append(img_b64)
        doc.close()
        logger.info(f"✅ Extracted {len(page_images_b64)} page images")
    except Exception as e:
        logger.warning(f"❌ Failed to extract page images: {e}")
    return page_images_b64

def create_chunks_by_title(elements):
    logger.info("🔨 Creating smart chunks...")
    chunks = chunk_by_title(
        elements, 
        max_characters=3000, 
        new_after_n_chars=2400, 
        combine_text_under_n_chars=500
    )
    logger.info(f"✅ Created {len(chunks)} chunks")
    return chunks

def separate_content_types(chunk):
    # This is a synchronous helper function, no changes needed
    content_data = {
        'text': chunk.text, 
        'tables': [], 
        'images': [], 
        'types': ['text'], 
        'page_number': None
    }
    
    if hasattr(chunk, 'metadata') and hasattr(chunk.metadata, 'orig_elements'):
        if chunk.metadata.orig_elements:
            first_el = chunk.metadata.orig_elements[0]
            if hasattr(first_el, 'metadata') and hasattr(first_el.metadata, 'page_number'):
                content_data['page_number'] = first_el.metadata.page_number
                
        for element in chunk.metadata.orig_elements:
            element_type = type(element).__name__
            if element_type == 'Table':
                content_data['types'].append('table')
                table_html = getattr(element.metadata, 'text_as_html', element.text)
                content_data['tables'].append(table_html)
            elif element_type == 'Image':
                if hasattr(element, 'metadata') and hasattr(element.metadata, 'image_base64'):
                    content_data['types'].append('image')
                    content_data['images'].append(element.metadata.image_base64)
                    
    content_data['types'] = list(set(content_data['types']))
    return content_data

# --- MODIFICATION: Made async for parallel execution ---
async def create_ai_enhanced_summary(text: str, tables: List[str], images: List[str]) -> str:
    """Asynchronously generates a summary using the LLM."""
    global llm
    try:
        prompt_text = f"""You are creating a searchable description for a document chunk. 
Your goal is to make this content easily findable through semantic search.

TEXT CONTENT:
{text}
"""
        if tables:
            prompt_text += f"\nTABLES:\n{tables}\n"
            
        prompt_text += """
YOUR TASK: Generate a comprehensive, searchable description that:
1. Summarizes the main topics and key information
2. Describes what's in any tables (column headers, data types, key findings)
3. Describes what's shown in any images
4. Uses clear, specific terminology that someone would search for
5. Maintains important details like numbers, dates, names

Keep it factual and detailed. This will be used for semantic search retrieval.
"""
        
        message_content = [{"type": "text", "text": prompt_text}]
        
        for image_base64 in images:
            message_content.append({
                "type": "image_url", 
                "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
            })
            
        message = HumanMessage(content=message_content)
        
        # Use ainvoke for asynchronous execution
        response = await llm.ainvoke([message]) 
        return response.content
    except Exception as e:
        logger.warning(f"     ❌ AI summary failed: {e}")
        return f"{text[:300]}... [Contains {len(tables)} table(s)] [Contains {len(images)} image(s)]"

# --- MODIFICATION: Made async to use asyncio.gather for parallel summaries ---
async def summarise_chunks(chunks):
    """
    Processes all chunks, creating AI summaries in parallel for chunks
    with tables or images.
    """
    logger.info("🧠 Processing chunks with AI Summaries...")
    langchain_documents = []
    chunk_id_to_content_map = {}
    total_chunks = len(chunks)
    
    tasks = []
    chunk_data_list = [] # To hold data in order

    # First, prepare all chunk data and summary tasks
    for i, chunk in enumerate(chunks):
        chunk_id = f"chunk_{uuid.uuid4()}"
        content_data = separate_content_types(chunk)
        
        # Store for later
        chunk_data_list.append({
            "chunk_id": chunk_id,
            "content_data": content_data
        })

        if content_data['tables'] or content_data['images']:
            # Create a coroutine (task) for AI summary
            logger.info(f"   [Task Created] AI summary for chunk {i + 1}/{total_chunks}")
            tasks.append(create_ai_enhanced_summary(
                content_data['text'], 
                content_data['tables'], 
                content_data['images']
            ))
        else:
            # No AI summary needed, add a placeholder task that returns instantly
            # This keeps our results list aligned with chunk_data_list
            tasks.append(asyncio.sleep(0, result=content_data['text'])) 

    # Now, run all summary tasks concurrently
    logger.info(f"🚀 Running {len(tasks)} summary tasks in parallel...")
    enhanced_content_results = await asyncio.gather(*tasks)
    logger.info("✅ All summary tasks complete.")

    # Finally, build the documents
    for i, chunk_data in enumerate(chunk_data_list):
        chunk_id = chunk_data["chunk_id"]
        content_data = chunk_data["content_data"]
        page_number = content_data.get('page_number')
        
        # Get the corresponding result from our parallel execution
        enhanced_content = enhanced_content_results[i]
        
        chunk_id_to_content_map[chunk_id] = {
            "raw_text": content_data['text'], 
            "tables_html": content_data['tables'], 
            "images_base64": content_data['images'], 
            "page_number": page_number
        }
        
        doc = Document(
            page_content=enhanced_content, 
            metadata={"chunk_id": chunk_id, "page_number": page_number}
        )
        langchain_documents.append(doc)
        
    logger.info(f"✅ Processed {len(langchain_documents)} chunks")
    return langchain_documents, chunk_id_to_content_map

# --- MODIFICATION: Made async to support parallel execution ---
async def generate_final_answer(chunks: List[Dict], query: str):
    logger.info("🧠 Generating final answer from DOCUMENTS...")
    global llm
    
    prompt_text = f"""Based on the following document excerpts, please answer this question: {query}

CONTENT TO ANALYZE:
"""
    
    for i, chunk_data in enumerate(chunks):
        prompt_text += f"--- Document Excerpt {i+1} (from Page {chunk_data.get('page_number', 'N/A')}) ---\n"
        if chunk_data.get("raw_text"):
            prompt_text += f"TEXT:\n{chunk_data['raw_text']}\n\n"
        if chunk_data.get("tables_html"):
            prompt_text += "TABLES:\n"
            for j, table in enumerate(chunk_data["tables_html"]):
                prompt_text += f"Table {j+1}:\n{table}\n\n"
                
    prompt_text += """
Please provide a clear, comprehensive answer using the text, tables, and images. 
Cite the page number for facts you use, e.g., [Page 5].

ANSWER:"""
    
    message_content = [{"type": "text", "text": prompt_text}]
    
    for chunk_data in chunks:
        for image_base64 in chunk_data.get("images_base64", []):
            message_content.append({
                "type": "image_url", 
                "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
            })
    
    message = HumanMessage(content=message_content)
    try:
        # Use ainvoke
        response = await llm.ainvoke([message]) 
        return response.content
    except Exception as e:
        logger.error(f"❌ LLM call failed in generate_final_answer: {e}")
        return "Sorry, I encountered an error while generating the final answer."

# --- Pinecone Init Function ---
def init_pinecone():
    global vectorstore
    
    if PINECONE_INDEX_NAME not in pc.list_indexes().names():
        logger.info(f"Creating new Pinecone index: {PINECONE_INDEX_NAME}")
        try:
            pc.create_index(
                name=PINECONE_INDEX_NAME, 
                dimension=2048, 
                metric="cosine", 
                spec=pinecone.ServerlessSpec(cloud='aws', region='us-east-1')
            )
            logger.info("✅ Index created.")
        except Exception as e:
            logger.error(f"❌ Pinecone index creation failed: {e}")
            raise
    else:
        logger.info(f"Index '{PINECONE_INDEX_NAME}' already exists.")
        
    vectorstore = PineconeVectorStore(index_name=PINECONE_INDEX_NAME, embedding=embeddings)
    logger.info("✅ Pinecone vector store initialized.")


# --- FastAPI App ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Server starting up...")
    init_pinecone()
    yield
    logger.info("Server shutting down...")

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["http://localhost:3000"], 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"]
)


# --- Pydantic Models ---
class QueryRequest(BaseModel):
    query: str
    session_id: Optional[str] = ""
    is_web_search_enabled: bool = False

class Citation(BaseModel):
    id: str
    page: Optional[int] = None
    type: Literal["text", "web"]
    content: Optional[str] = None
    title: Optional[str] = None
    url: Optional[str] = None

class PageImage(BaseModel):
    page: int
    image: str

class QueryResponse(BaseModel):
    answer: str
    citations: List[Citation]
    page_images: List[PageImage]


# --- Web Search Function ---
async def perform_web_search(query: str) -> QueryResponse:
    global llm, web_search_tool
    logger.info(f"🔍 Performing WEB search for: {query}")
    
    try:
        # Serper API is synchronous, run it in a threadpool to not block async event loop
        loop = asyncio.get_running_loop()
        search_results = await loop.run_in_executor(None, web_search_tool.results, query)
        
        if not search_results or "organic" not in search_results:
            logger.warning("No web results found.")
            return QueryResponse(
                answer="No web results found.", 
                citations=[], 
                page_images=[]
            )

        citations_for_frontend = []
        context_for_llm = ""
        
        for i, result in enumerate(search_results.get("organic", [])[:5]):
            snippet = result.get("snippet", "No snippet available.")
            title = result.get("title", "No title")
            url = result.get("link", "#")
            
            context_for_llm += f"--- Source {i+1} ---\nTitle: {title}\nSnippet: {snippet}\nURL: {url}\n\n"
            
            citations_for_frontend.append(Citation(
                id=f"web_{uuid.uuid4()}",
                type="web",
                content=snippet,
                title=title,
                url=url
            ))

        prompt = f"""Based *only* on the following web search results, please answer this question: {query}

SEARCH RESULTS:
{context_for_llm}

Please provide a clear, comprehensive answer. If the results don't contain sufficient information, say "I couldn't find a clear answer in the web results."

ANSWER:"""
        
        response = await llm.ainvoke(prompt) # Use ainvoke
        answer = response.content

        return QueryResponse(
            answer=answer,
            citations=citations_for_frontend,
            page_images=[]
        )
    except Exception as e:
        logger.error(f"❌ Error during web search: {e}", exc_info=True)
        return QueryResponse(
            answer=f"Web search failed: {e}",
            citations=[],
            page_images=[]
        )


# --- Document Search Function ---
async def perform_document_search(request: QueryRequest) -> QueryResponse:
    global vectorstore, global_document_storage
    logger.info(f"📄 Performing DOCUMENT search for session: {request.session_id}")
    
    if request.session_id not in global_document_storage:
        logger.warning(f"Session not found: {request.session_id}")
        return QueryResponse(
            answer="Session not found. Please upload the document again.", 
            citations=[], 
            page_images=[]
        )
    
    try:
        session_data = global_document_storage[request.session_id]
        chunk_data_map = session_data.get("chunk_data", {})
        page_images_b64 = session_data.get("page_images", [])

        # Retriever is sync, run in executor
        retriever = vectorstore.as_retriever(
            search_kwargs={"k": 4, "filter": {"session_id": request.session_id}}
        )
        loop = asyncio.get_running_loop()
        retrieved_chunks = await loop.run_in_executor(None, retriever.invoke, request.query)
        
        if not retrieved_chunks:
            logger.warning("No relevant chunks found in document.")
            return QueryResponse(
                answer="Sorry, I couldn't find relevant context in the document.", 
                citations=[], 
                page_images=[]
            )

        hydrated_contexts = []
        citations_for_frontend = []
        page_images_for_frontend_map = {}

        for chunk_doc in retrieved_chunks:
            chunk_id = chunk_doc.metadata.get("chunk_id")
            if chunk_id and chunk_id in chunk_data_map:
                original_content = chunk_data_map[chunk_id]
                page_number = original_content.get("page_number")
                
                hydrated_contexts.append(original_content) 
                citations_for_frontend.append(Citation(
                    id=chunk_id,
                    page=page_number,
                    type="text",
                    content=chunk_doc.page_content[:200] + "..."
                ))
                
                if page_number and (page_number - 1) < len(page_images_b64):
                    page_images_for_frontend_map[page_number] = page_images_b64[page_number - 1]
            else:
                logger.warning(f"Could not find chunk_id {chunk_id} in session storage.")

        # Generate answer (now async)
        answer = await generate_final_answer(hydrated_contexts, request.query)
        
        page_images_list = [
            PageImage(page=page_num, image=img_b64) 
            for page_num, img_b64 in sorted(page_images_for_frontend_map.items())
        ]

        return QueryResponse(
            answer=answer, 
            citations=citations_for_frontend,
            page_images=page_images_list
        )
    except Exception as e:
        logger.error(f"❌ Error during document search: {e}", exc_info=True)
        return QueryResponse(
            answer=f"Document search failed: {e}",
            citations=[],
            page_images=[]
        )


# --- /upload Endpoint ---
@app.post("/upload")
async def upload_document_api(file: UploadFile = File(...)):
    global vectorstore, global_document_storage
    
    if not vectorstore:
        logger.error("Vector store not initialized during upload.")
        raise HTTPException(status_code=500, detail="Vector store not initialized")
        
    session_id = str(uuid.uuid4())
    logger.info(f"🚀 Starting new session: {session_id}")
    
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        logger.info(f"File saved to temp path: {tmp_path}")
        
        # These are synchronous
        page_images_b64 = extract_page_images(tmp_path)
        elements = partition_document(tmp_path)
        chunks = create_chunks_by_title(elements)
        
        # --- MODIFICATION: Await the async summarise_chunks ---
        (processed_chunks, chunk_data_map) = await summarise_chunks(chunks)
        
        for doc in processed_chunks:
            doc.metadata["session_id"] = session_id

        global_document_storage[session_id] = {
            "chunk_data": chunk_data_map, 
            "page_images": page_images_b64
        }
        
        logger.info(f"🔮 Adding {len(processed_chunks)} chunks to Pinecone for session {session_id}...")
        
        # Vectorstore add is sync, run in executor
        loop = asyncio.get_running_loop()
        # Add documents in small batches to avoid rate limits
        batch_size = 10
        for i in range(0, len(processed_chunks), batch_size):
            batch = processed_chunks[i:i + batch_size]
            await loop.run_in_executor(None, vectorstore.add_documents, batch)
            logger.info(f"✅ Added batch {i//batch_size + 1}/{(len(processed_chunks) + batch_size - 1)//batch_size}")
            if i + batch_size < len(processed_chunks):
                await asyncio.sleep(6)  # Wait 6 seconds between batches

        
        logger.info("✅ Chunks added to Pinecone.")
        
        return {
            "message": f"Successfully processed and indexed {file.filename}", 
            "session_id": session_id
        }
    except Exception as e:
        logger.error(f"❌ Error during upload: {e}", exc_info=True)
        if session_id in global_document_storage:
            del global_document_storage[session_id]
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# --- /query Endpoint (Router) ---
@app.post("/query", response_model=QueryResponse)
async def query_index_api(request: QueryRequest):
    global llm, global_document_storage
    
    # Strategy 1: Web Search is OFF. Only search the document.
    if not request.is_web_search_enabled:
        logger.info(f"Strategy: Document-Only for query: '{request.query}'")
        if not request.session_id or request.session_id not in global_document_storage:
            logger.warning(f"Document-Only query failed: No session ID {request.session_id}")
            return QueryResponse(
                answer="Please upload a document to ask questions, or enable the 'Web Search' toggle.",
                citations=[],
                page_images=[]
            )
        # We have a session, so search the document.
        return await perform_document_search(request)

    # Strategy 2: Web Search is ON. Perform hybrid search (Doc + Web).
    else:
        logger.info(f"Strategy: Hybrid (Doc+Web) for query: '{request.query}'")
        
        # --- MODIFICATION: Run searches in parallel ---
        search_tasks = [perform_web_search(request.query)] # Web search task
        
        if request.session_id and request.session_id in global_document_storage:
            logger.info("   → Hybrid: Adding document search to parallel tasks.")
            search_tasks.append(perform_document_search(request)) # Add doc search task
        else:
            logger.info("   → Hybrid: No document session, skipping document search.")

        logger.info(f"🚀 Running {len(search_tasks)} search tasks in parallel...")
        results = await asyncio.gather(*search_tasks)
        logger.info("✅ All search tasks complete.")
        
        # Unpack results
        web_response = results[0] # Web search is always first
        doc_response = None
        if len(results) > 1:
            doc_response = results[1] # Doc search is second, if it ran

        doc_answer = ""
        doc_citations = []
        doc_page_images = []
        
        if doc_response:
            doc_answer = doc_response.answer
            doc_citations = doc_response.citations
            doc_page_images = doc_response.page_images
            
        web_answer = web_response.answer
        web_citations = web_response.citations
        # --- END MODIFICATION ---

        # Step 2c: Synthesize results
        logger.info("   → Hybrid: Synthesizing answers...")
        
        if "Sorry, I couldn't find relevant context" in doc_answer: doc_answer = ""
        if "No web results found" in web_answer: web_answer = ""

        if not doc_answer and not web_answer:
            logger.warning("Hybrid search found no answer from any source.")
            final_answer = "Sorry, I couldn't find any information from your document or the web."
        elif not doc_answer:
            logger.info("Hybrid search using Web-Only answer.")
            final_answer = web_answer
        elif not web_answer:
            logger.info("Hybrid search using Document-Only answer.")
            final_answer = doc_answer 
        else:
            logger.info("Hybrid search synthesizing Doc and Web answers.")
            prompt = f"""You are a helpful assistant. You have received a user query and have two sources of information to answer it.

User Query: "{request.query}"

Source 1: Information from an uploaded document.
Document Answer:
{doc_answer}

Source 2: Information from a real-time web search.
Web Search Answer:
{web_answer}

Your Task:
Synthesize these two pieces of information into a single, comprehensive, and clear answer.
1. Prioritize the document information if it's available and relevant.
2. Use the web search to supplement, confirm, or answer parts the document couldn't.
3. If both sources say the same thing, just state the fact. Don't say "The document said... and the web said...".
4. If the document and web conflict, state the conflict clearly (e.g., "The document states X, but recent web results suggest Y.").
5. If only one source has an answer, use that.
6. If neither has an answer, state that you couldn't find the information.

Final Answer:
"""
            try:
                final_answer_response = await llm.ainvoke(prompt)
                final_answer = final_answer_response.content
            except Exception as e:
                logger.error(f"❌ Synthesizer LLM call failed: {e}")
                final_answer = f"Error synthesizing results: {e}"

        # Step 2d: Combine citations and return
        final_citations = doc_citations + web_citations
        
        return QueryResponse(
            answer=final_answer,
            citations=final_citations,
            page_images=doc_page_images
        )


# --- Main ---
if __name__ == "__main__":
    logger.info("Starting FastAPI server at http://localhost:8000")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)