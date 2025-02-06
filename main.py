import time
import re
import streamlit as st
import openai
import requests
from docx import Document
from io import BytesIO

# ----------------------------
# Page Configuration & Title
# ----------------------------
st.set_page_config(page_title="SEO Element Generator", layout="wide")
st.title("SEO Element Generator")
st.write("Created by Brandon Lazovic")

st.markdown("""
## How to use this app:
1. Enter your OpenAI API key.
2. Enter your DataForSEO credentials.
3. Select how many competitor results to analyze (10 or 20).
4. Input up to 10 target keywords (one per line).
5. Click **Generate SEO Elements** to get recommendations.
6. Review the results and explanations.
7. Download the results as a Word document.
""")

# ----------------------------
# User Inputs for Credentials and Keywords
# ----------------------------
openai_api_key = st.text_input("Enter your OpenAI API key:", type="password")
dataforseo_username = st.text_input("Enter your DataForSEO username:")
dataforseo_password = st.text_input("Enter your DataForSEO password:", type="password")

# Let the user choose how many organic results to analyze.
num_results = st.radio(
    "How many competitor results would you like to analyze?",
    (10, 20),
    index=0,
    horizontal=True
)

keywords = st.text_area("Enter up to 10 target keywords (one per line):", height=200)
keyword_list = [k.strip() for k in keywords.split("\n") if k.strip()]

# Let the user choose which model to use
model_choice = st.selectbox("Select the OpenAI model:", ["gpt-4o", "gpt-4o-mini"])


# ----------------------------
# Function: Parse GPT's Output to Extract H1, Title Tag, Meta Description
# ----------------------------
def parse_seo_recommendations(gpt_text):
    """
    Extracts H1, Title Tag, and Meta Description (plus their explanations)
    from the GPT output if it follows the structure:
       H1: ...
       Explanation:
       - ...
       Title Tag: ...
       Explanation:
       - ...
       Meta Description: ...
       Explanation:
       - ...
    Adjust as necessary if GPT’s format changes.
    """
    lines = gpt_text.splitlines()

    h1 = ""
    h1_explanation = []
    title = ""
    title_explanation = []
    meta = ""
    meta_explanation = []

    current_section = None
    in_explanation = False

    for line in lines:
        stripped = line.strip()

        # Detect "H1:"
        if stripped.startswith("H1:"):
            h1 = stripped[len("H1:"):].strip()
            current_section = "h1"
            in_explanation = False
            continue

        # Detect "Title Tag:"
        if stripped.startswith("Title Tag:"):
            title = stripped[len("Title Tag:"):].strip()
            current_section = "title"
            in_explanation = False
            continue

        # Detect "Meta Description:"
        if stripped.startswith("Meta Description:"):
            meta = stripped[len("Meta Description:"):].strip()
            current_section = "meta"
            in_explanation = False
            continue

        # Detect "Explanation:"
        if stripped.startswith("Explanation:"):
            in_explanation = True
            continue

        # Collect explanations if in_explanation = True
        if in_explanation:
            if current_section == "h1":
                h1_explanation.append(stripped)
            elif current_section == "title":
                title_explanation.append(stripped)
            elif current_section == "meta":
                meta_explanation.append(stripped)

    return {
        "H1": h1,
        "H1_explanation": "\n".join(h1_explanation),
        "Title": title,
        "Title_explanation": "\n".join(title_explanation),
        "Meta": meta,
        "Meta_explanation": "\n".join(meta_explanation)
    }


# ----------------------------
# Function: DataForSEO Google SERP Scraper
# ----------------------------
def scrape_google_results(keyword, username, password, limit=10):
    """
    Pulls type=organic results and uses the 'description' field from DataForSEO,
    converting None to '' to avoid errors.
    """
    url = "https://api.dataforseo.com/v3/serp/google/organic/live/advanced"
    payload = [{
        "keyword": keyword,
        "language_code": "en",
        "location_code": 2840,  # e.g. 2840 = United States
        "device": "desktop"
    }]

    response = requests.post(url, auth=(username, password), json=payload)
    data = response.json()

    results = []
    for task in data.get("tasks", []):
        for result_item in task.get("result", []):
            for item in result_item.get("items", []):
                if item.get("type") == "organic":
                    title = item.get("title") or ""
                    snippet = item.get("description") or ""
                    if title:
                        results.append({"title": title, "snippet": snippet})
    return results[:limit]


# ----------------------------
# Function: Summarize Competitor Elements
# ----------------------------
def summarize_competitor_elements(results):
    """
    Creates a summary of competitor results with average title/snippet length,
    common title words, and sample titles/snippets.

    - Shows up to 20 titles.
    - Shows up to 20 non-blank snippets.
    - Truncates snippets to ~100 characters for readability.
    """
    if not results:
        return "No competitor results found. Unable to perform competitor analysis."

    titles = [r["title"] for r in results]
    snippets = [r["snippet"] for r in results]

    avg_title_length = sum(len(t) for t in titles) / len(titles) if titles else 0
    avg_snippet_length = sum(len(s) for s in snippets) / len(snippets) if snippets else 0

    summary = f"Analyzed {len(results)} competitor results.\n"
    summary += f"Average title length: {avg_title_length:.1f} characters.\n"
    summary += f"Average snippet length: {avg_snippet_length:.1f} characters.\n"

    # Count word frequencies in titles (ignoring words < 4 chars)
    word_freq = {}
    for title in titles:
        for word in re.findall(r'\w+', title.lower()):
            if len(word) > 3:
                word_freq[word] = word_freq.get(word, 0) + 1
    common_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]
    summary += f"Common words in titles: {', '.join([w for w, _ in common_words])}\n\n"

    # -- Up to 20 titles --
    max_titles_to_show = min(len(titles), 20)
    summary += "Sample competitor titles:\n"
    for title in titles[:max_titles_to_show]:
        summary += f"- {title}\n"

    # -- Up to 20 non-blank snippets --
    non_blank_snippets = [s for s in snippets if s.strip()]
    max_snippets_to_show = min(len(non_blank_snippets), 20)
    summary += "\nSample competitor snippets (omitting blanks):\n"
    for snippet in non_blank_snippets[:max_snippets_to_show]:
        snippet_preview = snippet[:100]
        if len(snippet) > 100:
            snippet_preview += "..."
        summary += f"- {snippet_preview}\n"

    return summary

# ----------------------------
# Function: Generate SEO Elements (Synchronous)
# ----------------------------
def generate_seo_elements(keyword, competitor_summary, openai_api_key, model_choice, max_retries=3):
    """
    Calls OpenAI's ChatCompletion.create() in a loop with retries.
    """
    openai.api_key = openai_api_key

    prompt = f"""
Generate an H1, title tag, and meta description for the keyword: "{keyword}"

Requirements:
- H1 and title tag should be 70 characters or less.
- Meta description should be 155 characters or less.
- Avoid buzzwords and branded terms.
- Include an exact match or close variation of the target keyword.
- Closely align with the competitor results provided below.
- The elements should be a summarization of common elements from the top competitors.

Competitor analysis:
{competitor_summary}

Based on the competitor analysis, create SEO elements that are very similar to the competitors' approach, while still being unique. Focus on common phrases, structures, and themes used by competitors.

Please provide your response in the following structure:
COMPETITOR ELEMENTS SUMMARY
1. Most Common Title Structures:
   - [Point 1]
   - [Point 2]
   ...
2. Common Themes in Meta Descriptions:
   - [Point 1]
   - [Point 2]
   ...

3. Frequently Used Phrases or Keywords:
   - [Phrase 1]
   - [Phrase 2]
   ...
4. Notable Patterns in Competitor Information Presentation:
   - [Pattern 1]
   - [Pattern 2]
   ...

SEO ELEMENTS
H1: [Your H1]
Explanation:
- [Point 1]
- [Point 2]
...
Title Tag: [Your Title Tag]
Explanation:
- [Point 1]
- [Point 2]
...
Meta Description: [Your Meta Description]
Explanation:
- [Point 1]
- [Point 2]
...
    """

    for attempt in range(max_retries):
        try:
            response = openai.ChatCompletion.create(
                model=model_choice,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an SEO expert tasked with creating optimized on-page elements "
                            "that closely align with competitor trends."
                        )
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                request_timeout=60
            )
            return response.choices[0].message.content
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            time.sleep(2 ** attempt)


# ----------------------------
# Function: Create Word Document
# ----------------------------
def create_word_document(results):
    """
    Creates a Word doc summarizing each keyword's SEO elements and competitor analysis.
    """
    doc = Document()
    doc.add_heading('SEO Element Generator Results', 0)
    for result in results:
        doc.add_heading(f"Keyword: {result['Keyword']}", level=1)
        doc.add_paragraph(result['SEO Elements and Competitor Summary'])
        doc.add_heading("Competitor Analysis", level=2)
        doc.add_paragraph(result['Competitor Analysis'])
        doc.add_paragraph("\n")
    return doc


# ----------------------------
# Main Application Logic
# ----------------------------
if st.button("Generate SEO Elements") \
   and openai_api_key \
   and dataforseo_username \
   and dataforseo_password \
   and keyword_list:

    results = []

    for keyword in keyword_list[:10]:
        st.subheader(f"Results for: {keyword}")

        with st.spinner(f"Analyzing competitors (top {num_results}) for '{keyword}'..."):
            competitor_results = scrape_google_results(
                keyword,
                dataforseo_username,
                dataforseo_password,
                limit=num_results
            )
            competitor_summary = summarize_competitor_elements(competitor_results)

        with st.spinner(f"Generating SEO elements for '{keyword}' using {model_choice}..."):
            seo_elements = generate_seo_elements(
                keyword,
                competitor_summary,
                openai_api_key,
                model_choice
            )

        # -- PARSE GPT OUTPUT INTO COMPONENT PARTS --
        parsed = parse_seo_recommendations(seo_elements)

        # -- DISPLAY GPT OUTPUT IN A STRUCTURED WAY --
        # Full GPT text in an expander (for context)
        with st.expander("Full GPT Output (SEO Elements & Explanation)"):
            st.markdown(f"```\n{seo_elements}\n```")

        # Separate dropdown for the main on-page recommendations
        with st.expander("Quick Reference: Recommended On-Page Elements"):
            st.subheader("H1")
            st.write(parsed["H1"])
            if parsed["H1_explanation"]:
                st.markdown("**Explanation:**")
                st.markdown(parsed["H1_explanation"].replace("\n", "\n\n"))

            st.subheader("Title Tag")
            st.write(parsed["Title"])
            if parsed["Title_explanation"]:
                st.markdown("**Explanation:**")
                st.markdown(parsed["Title_explanation"].replace("\n", "\n\n"))

            st.subheader("Meta Description")
            st.write(parsed["Meta"])
            if parsed["Meta_explanation"]:
                st.markdown("**Explanation:**")
                st.markdown(parsed["Meta_explanation"].replace("\n", "\n\n"))

        # Competitor analysis in another expander
        with st.expander("Competitor Analysis Summary"):
            st.markdown(f"```\n{competitor_summary}\n```")

        # Add final result for Word doc creation
        results.append({
            "Keyword": keyword,
            "SEO Elements and Competitor Summary": seo_elements,
            "Competitor Analysis": competitor_summary
        })

    # Create and offer the Word document download
    doc = create_word_document(results)
    bio = BytesIO()
    doc.save(bio)
    st.download_button(
        label="Download results as Word Document",
        data=bio.getvalue(),
        file_name="seo_elements_results.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

else:
    st.write("Please enter your OpenAI API key, DataForSEO credentials, and at least one keyword to generate SEO elements.")
