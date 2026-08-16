import streamlit as st
from htbuilder.units import rem
from htbuilder import div, styles
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor
import datetime
import textwrap
import time
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

main_agent_system_prompt = textwrap.dedent("""
    You are an AI assistant focused on answering user question about purchase history.
    DO NOT use your own memory to answer. If the provided context is not sufficent, asks for follow ups.
    You MUST only answer with a the factual data only without much explanations.
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
    with conn.session as s:
        s.execute(
            text('INSERT INTO purchase (date, item, store, price) VALUES (:date, :item, :store, :price);'),
            {"date": extracted_keys[0], "item": extracted_keys[1], "store": extracted_keys[2], "price": extracted_keys[3]}
        )
        s.commit()

def ocr_reasoner(extracted_text):
    response = client.models.generate_content(
        model=model,
        contents=extracted_text,
        config=types.GenerateContentConfig(system_instruction=ocr_extract_system_prompt),
        )
    cleansed_response = response.text.split(", ")
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
         )
    for chunk in response_stream:
        if chunk.text:
            yield chunk.text

def build_question_prompt(question):
    """Fetches info from different services and creates the prompt string."""
    old_history = st.session_state.messages[:-HISTORY_LENGTH]
    recent_history = st.session_state.messages[-HISTORY_LENGTH:]

    if recent_history:
        recent_history_str = history_to_text(recent_history)
    else:
        recent_history_str = None

    # Fetch information from different services in parallel.
    task_infos = []


    return build_prompt(
        instructions=main_agent_system_prompt,
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

            with st.spinner("Thinking..."):
                        response_gen = get_response(full_prompt)

            with st.container():
                        # Stream the LLM response.
                        response = st.write_stream(get_response(full_prompt))
            
                        # Add messages to chat history.
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