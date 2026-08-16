import streamlit as st
from htbuilder.units import rem
from htbuilder import div, styles
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor
import datetime
import textwrap
import time
import re
import pytesseract
from PIL import Image
from google import genai
from google.genai import types
import os
from dotenv import load_dotenv
import sqlite3
from sqlalchemy import text

st.set_page_config(page_title="Receipt Assistant", page_icon="🧾")

title_row = st.container(
    horizontal=True,
    vertical_alignment="bottom",
)

# Increased file size limit
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
SUMMARIZE_OLD_HISTORY = True
HISTORY_LENGTH = 5
MAX_IMAGE_SIZE = 2000  # pixels
MIN_TIME_BETWEEN_REQUESTS = datetime.timedelta(seconds=3)
DEBUG_MODE = st.query_params.get("debug", "false").lower() == "true"

ocr_extract_system_prompt = textwrap.dedent("""
Your main task is to extract key information from an OCR result. The processed content is mainly a receipt. You must extract these information:
1. Receipt Date (Use YYYY-MM-DD Format)
2. Item Name
3. Store Name/Location Name
4. Price

After you retrieve those information, I want you to create a structured format to inject the information to an SQLlite table with column:
1. date
2. item
3. store
4. price

Use this structure as a guide:


ONLY ANSWER WITH A STRUCTURE LIKE THIS:
Receipt Date, Item Name, Store/Location Name, Price
""")

def build_main_agent_system_prompt() -> str:
    today = datetime.date.today()
    return textwrap.dedent(f"""
    You are an AI assistant focused on answering user question about purchase history.
    Today's date is {today.isoformat()} ({today.strftime('%A, %B %d, %Y')}). Use this to resolve any
    relative date reference (e.g. "yesterday", "last 7 days", "this month") into an absolute
    YYYY-MM-DD date or range before calling get_date.
    DO NOT use your own memory to answer. If the provided context is not sufficent, asks for follow ups.
    You MUST only answer with a the factual data only without much explanations.
    You have access to functions that query the user's real purchase database.
    Before asking any follow-up question, you MUST first attempt to call the relevant function to retrieve real data.
    Only ask a follow-up if the function's result genuinely doesn't answer the question — never ask for clarification on a term the user already stated clearly (like an item name).
    NEVER state a date, item, store, or price that did not come from a function result. If a function
    call returns an empty list, say plainly that no matching purchase was found — do not guess or make
    one up. If the user's question implies a filter (e.g. a category like "food") that has no matching
    column, say you can only search by item, price, store, or date, instead of inventing a match.
    You can answer users questions like these:
        --------------------------------------------
        Q:'What food did i buy yesterday?'
        A:'Yesterday on August 10th, you bought a hamburger for Rp20.000
        --------------------------------------------
        Q:'Give me total expenses for food on 20 June'
        A:'Your total expenses is Rp140.000 consist of 4 items. Do you want the breakdown?'
        --------------------------------------------
        Q:'Where did I buy hamburger from last 7 day'
        A:'You bought hamburger twice on the last 7 days, one from X and one from Y.'


""")

model = "gemini-3.5-flash-lite"

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

conn = st.connection('receipt_agent', type='sql')
def data_store(extracted_keys):
    if len(extracted_keys) != 4:
        st.error(f"Could not parse receipt into 4 fields (got {len(extracted_keys)}: {extracted_keys}). Not saved.")
        return
    date, item, store, raw_price = extracted_keys
    clean_price = re.sub(r"[^\d]", "", raw_price)
    if not clean_price:
        st.error(f"Could not parse a numeric price from '{raw_price}'. Not saved.")
        return
    with conn.session as s:
        s.execute(
            text('INSERT INTO purchase (date, item, store, price) VALUES (:date, :item, :store, :price);'),
            {"date": date, "item": item, "store": store, "price": int(clean_price)}
        )
        s.commit()

    st.cache_data.clear()

def ocr_reasoner(extracted_text):
    response = client.models.generate_content(
        model=model,
        contents=extracted_text,
        config=types.GenerateContentConfig(system_instruction=ocr_extract_system_prompt, temperature=0),
        )
    cleansed_response = response.text.strip().split(", ")
    return cleansed_response


def ocr_image(receipt):
    st.success("Form submitted successfully!")
    image = Image.open(receipt)
    extracted_text = pytesseract.image_to_string(image, lang="ind", config='--psm 6')
    return extracted_text

def history_to_text(chat_history):
    """Converts chat history into a string."""
    return "\n".join(f"[{h['role']}]: {h['content']}" for h in chat_history)

def build_prompt(**kwargs):
    """Builds a prompt string with the kwargs as HTML-like tags.

    For example, this:

        build_prompt(foo="1\n2\n3", bar="4\n5\n6")

    ...returns:

        '''
        <foo>
        1
        2
        3
        </foo>
        <bar>
        4
        5
        6
        </bar>
        '''
    """
    prompt = []

    for name, contents in kwargs.items():
        if contents:
            prompt.append(f"<{name}>\n{contents}\n</{name}>")

    prompt_str = "\n".join(prompt)

    return prompt_str

def get_response(prompt):
    response_stream =  client.models.generate_content_stream(
         model=model,
         contents=prompt,
         config=types.GenerateContentConfig(
             system_instruction=build_main_agent_system_prompt(),
             tools=[get_item, get_price, get_date, get_store],
             temperature=0,
         )
         )
    for chunk in response_stream:
        if chunk.text:
            yield chunk.text

def get_item(search_term: str):
    """Look up purchases matching an item name.

    Args:
        search_term: The item name or partial keyword to search for (e.g. "hamburger").
    """
    print(f"[TOOL CALLED] get_item with search_term={search_term}")
    query = "SELECT * FROM purchase WHERE item LIKE :term;"
    df = conn.query(query, params={"term": f"%{search_term}%"}, ttl=0)
    return df.to_dict(orient="records")

def get_price(search_term: str):
    """Look up purchases matching an item price.

    Args:
        search_term: The item price or partial keyword to search for (e.g. "20000").
    """
    print(f"[TOOL CALLED] get_item with search_term={search_term}")
    query = "SELECT * FROM purchase WHERE price LIKE :term;"
    df = conn.query(query, params={"term": f"%{search_term}%"}, ttl=0)
    return df.to_dict(orient="records")

def get_store(search_term: str):
    """Look up purchases matching an item store/shop.

    Args:
        search_term: The item store/shop or partial keyword to search for (e.g. "kopi kenangan").
    """
    print(f"[TOOL CALLED] get_item with search_term={search_term}")
    query = "SELECT * FROM purchase WHERE store LIKE :term;"
    df = conn.query(query, params={"term": f"%{search_term}%"}, ttl=0)
    return df.to_dict(orient="records")

def get_date(search_term: str):
    """Look up purchases matching an item bought date.

    Args:
        search_term: The item date or partial keyword to search for (e.g. "YYYY-MM-DD").
    """
    print(f"[TOOL CALLED] get_item with search_term={search_term}")
    query = "SELECT * FROM purchase WHERE date LIKE :term;"
    df = conn.query(query, params={"term": f"%{search_term}%"}, ttl=0)
    return df.to_dict(orient="records")

def build_question_prompt(question):
    """Fetches info from different services and creates the prompt string."""
    old_history = st.session_state.messages[:-HISTORY_LENGTH]
    recent_history = st.session_state.messages[-HISTORY_LENGTH:]

    if recent_history:
        recent_history_str = history_to_text(recent_history)
    else:
        recent_history_str = None

    task_infos = []


    return build_prompt(
        recent_messages=recent_history_str,
        question=question,
    )



def configure_sidebar() -> None:
    """
    Setup and display the sidebar elements.

    This function configures the sidebar of the Streamlit application, 
    including the form for user inputs and the resources section.
    """
    with st.sidebar:
        with st.form("my_form"):
            st.info("**Receipt Assistant**", icon="🧾")
            my_upload = st.file_uploader("Upload your receipt here", type=["png", "jpg", "jpeg"])
            # Information about limitations
            with st.sidebar.expander("ℹ️ Image Guidelines"):
                    st.write("""
                    - Receipt screenshot or photo
                    - Maximum file size: 200MB
                    - Large images will be automatically resized
                    - Supported formats: PNG, JPG, JPEG
                    - Processing time depends on image size
                    """)
            submitted = st.form_submit_button(
                "Submit", type="primary", use_container_width=True)
            if submitted and my_upload is not None:
                extracted_text = ocr_image(my_upload)
                extracted_keys = ocr_reasoner(extracted_text)
                data_store(extracted_keys)
            elif submitted:
                st.warning("Please upload an image before submitting.")
            
def main_page() -> None:
    user_just_asked_initial_question = (
        "initial_question" in st.session_state and st.session_state.initial_question
        )
    user_first_interaction = (
        user_just_asked_initial_question
        )
    has_message_history = (
        "messages" in st.session_state and len(st.session_state.messages) > 0
        )

    with title_row:
                st.title(
                    # ":material/cognition_2: Streamlit AI assistant", anchor=False, width="stretch"
                    "Receipt Assistant",
                    anchor=False,
                    width="stretch",
                )
    
    if not user_first_interaction and not has_message_history:

        st.session_state.messages = []

        with st.container():
            st.chat_input("Ask a question...", key="initial_question")

        st.stop()

    user_message = st.chat_input("Ask a follow-up...")

    if not user_message:
        if user_just_asked_initial_question:
            user_message = st.session_state.initial_question

    with title_row:
        def clear_conversation():
                st.session_state.messages = []
                st.session_state.initial_question = None
                st.session_state.selected_suggestion = None

        st.button(
                "Restart",
                icon=":material/refresh:",
                on_click=clear_conversation,
            )

    if "prev_question_timestamp" not in st.session_state:
        st.session_state.prev_question_timestamp = datetime.datetime.fromtimestamp(0)

    for i, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
                if message["role"] == "assistant":
                    st.container()  # Fix ghost message bug.
        
                st.markdown(message["content"])

    if user_message:
        user_message = user_message.replace("$", r"\$")

        with st.chat_message("user"):
            st.text(user_message)

        with st.chat_message("assistant"):
            with st.spinner("Waiting..."):
                question_timestamp = datetime.datetime.now()
                time_diff = question_timestamp - st.session_state.prev_question_timestamp
                st.session_state.prev_question_timestamp = question_timestamp
                if time_diff < MIN_TIME_BETWEEN_REQUESTS:
                    time.sleep(time_diff.seconds + time_diff.microseconds * 0.001)
                
                user_message = user_message.replace("'", "")

            if DEBUG_MODE:
                with st.status("Computing prompt...") as status:
                    full_prompt = build_question_prompt(user_message)
                    st.code(full_prompt)
                    status.update(label="Prompt computed")
            else:
                 with st.spinner("Researching..."):
                    full_prompt = build_question_prompt(user_message)

            with st.container():
                        response = st.write_stream(get_response(full_prompt))
            
                        st.session_state.messages.append({"role": "user", "content": user_message})
                        st.session_state.messages.append({"role": "assistant", "content": response})
            

def main():
    """
    Main function to run the Streamlit application.

    This function initializes the sidebar configuration and the main page layout.
    It retrieves the user inputs from the sidebar, and passes them to the main page function.
    The main page function then generates images based on these inputs.
    """
    configure_sidebar()
    main_page()


if __name__ == "__main__":
    main()