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

st.set_page_config(page_title="Receipt Assistant", page_icon="🧾")

title_row = st.container(
    horizontal=True,
    vertical_alignment="bottom",
)

# Increased file size limit
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# Max dimensions for processing
MAX_IMAGE_SIZE = 2000  # pixels

ocr_extract_system_prompt = """
Your main task is to extract key information from an OCR result. The processed content is mainly a receipt. You must extract these information:
1. Receipt Date (Use DD-MM-YYYY Format)
2. Item Name
3. Price

After you retrieve those information, I want you to create a structured format to inject the information to an SQLlite table with column:
1. date
2. item
3. price

Use this structure as a guide:


ONLY ANSWER WITH A STRUCTURE LIKE THIS:
(Receipt Date, Item Name, Price)
"""
model = "gemini-3.5-flash-lite"

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)




def ocr_reasoner(extracted_text):
    response = client.models.generate_content(
        model=model,
        contents=extracted_text,
        config=types.GenerateContentConfig(system_instruction=ocr_extract_system_prompt),
        )
    print(response.text)
    st.success(response.text)

def ocr_image(receipt):
    st.success("Form submitted successfully!")
    image = Image.open(receipt)
    extracted_text = pytesseract.image_to_string(image, lang="ind", config='--psm 6')
    return extracted_text

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
                ocr_reasoner(extracted_text)
            elif submitted:
                st.warning("Please upload an image before submitting.")
            
def main_page() -> None:
    with title_row:
        st.title(
            # ":material/cognition_2: Streamlit AI assistant", anchor=False, width="stretch"
            "Receipt Assistant",
            anchor=False,
            width="stretch",
        )
    with st.container():
        st.chat_input("Ask a question...", key="initial_question")


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