import streamlit as st
import openai
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
from urllib.parse import quote_plus

# Set page title and creator info
st.set_page_config(page_title="SEO Element Generator", layout="wide")
st.title("SEO Element Generator")
st.write("Created by Brandon Lazovic")

# Instructions
st.markdown("""
## How to use this app:
1. Enter your OpenAI API key.
2. Input up to 10 target keywords (one per line).
3. Click 'Generate SEO Elements' to get recommendations.
4. Review the results and explanations.
5. Download the results as a CSV file.
""")

# Input for OpenAI API key
api_key = st.text_input("Enter your OpenAI API key:", type="password")

# Function to scrape Google search results
def scrape_google_results(keyword, num_results=10):
    url = f"https://www.google.com/search?q={quote_plus(keyword)}&num={num_results}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")
    
    results = []
    for result in soup.select("div.g"):
        title = result.select_one("h3")
        if title:
            title = title.text
            link = result.select_one("a")["href"]
            snippet = result.select_one("div.VwiC3b")
            snippet = snippet.text if snippet else ""
            results.append({"title": title, "snippet": snippet})
    
    return results[:num_results]

# Function to summarize competitor elements
def summarize_competitor_elements(results):
    titles = [result["title"] for result in results]
    snippets = [result["snippet"] for result in results]
    
    summary = f"Analyzed {len(results)} competitor results.\n"
    summary += f"Average title length: {sum(len(title) for title in titles) / len(titles):.1f} characters.\n"
    summary += f"Average snippet length: {sum(len(snippet) for snippet in snippets) / len(snippets):.1f} characters.\n"
    
    common_words = set.intersection(*[set(re.findall(r'\w+', title.lower())) for title in titles])
    summary += f"Common words in titles: {', '.join(list(common_words)[:5])}\n"
    
    return summary

# Function to generate SEO elements using GPT-4
def generate_seo_elements(keyword, competitor_summary):
    openai.api_key = api_key
    
    prompt = f"""
    Generate an H1, title tag, and meta description for the keyword: "{keyword}"
    
    Requirements:
    - H1 and title tag should be 70 characters or less
    - Meta description should be 155 characters or less
    - Avoid AI filler words like "cracking the code" or "topic demystified"
    - Omit branded terms
    - Include an exact match or close variation of the target keyword
    
    Competitor analysis:
    {competitor_summary}
    
    Provide explanations for your choices.
    """
    
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are an SEO expert tasked with creating optimized on-page elements."},
            {"role": "user", "content": prompt}
        ]
    )
    
    return response.choices[0].message.content

# Input for keywords
keywords = st.text_area("Enter up to 10 target keywords (one per line):", height=200)
keyword_list = [k.strip() for k in keywords.split("\n") if k.strip()]

if st.button("Generate SEO Elements") and api_key and keyword_list:
    results = []
    
    for keyword in keyword_list[:10]:
        st.subheader(f"Results for: {keyword}")
        
        with st.spinner(f"Analyzing competitors for '{keyword}'..."):
            competitor_results = scrape_google_results(keyword)
            competitor_summary = summarize_competitor_elements(competitor_results)
        
        with st.spinner(f"Generating SEO elements for '{keyword}'..."):
            seo_elements = generate_seo_elements(keyword, competitor_summary)
        
        st.write(seo_elements)
        st.write("Competitor Analysis Summary:")
        st.write(competitor_summary)
        
        results.append({
            "Keyword": keyword,
            "SEO Elements": seo_elements,
            "Competitor Summary": competitor_summary
        })
    
    # Create a DataFrame and offer CSV download
    df = pd.DataFrame(results)
    csv = df.to_csv(index=False)
    st.download_button(
        label="Download results as CSV",
        data=csv,
        file_name="seo_elements_results.csv",
        mime="text/csv"
    )
else:
    st.write("Please enter your OpenAI API key and at least one keyword to generate SEO elements.")
