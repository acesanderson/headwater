import streamlit as st
import requests
import pandas as pd

# CONFIGURATION
# If running on the same machine as the Headwater server:
API_URL = "http://127.0.0.1:8080/curator/curate"

st.set_page_config(page_title="Curator Search", layout="centered")
st.title("🌊 Curator Search")

# Inputs
query = st.text_input("Search query", placeholder="e.g., Intro to Python")

with st.expander("Advanced Settings"):
    col1, col2 = st.columns(2)
    with col1:
        k_results = st.number_input("Top Results", min_value=1, value=5)
    with col2:
        # Matches the keys in your rerank.py
        model_options = ["bge", "mxbai", "ce", "flash", "colbert", "cohere", "jina"]
        model = st.selectbox("Reranker", model_options, index=0)

# Execution
if query and st.button("Search", type="primary"):
    payload = {
        "query_string": query,
        "k": k_results,
        "n_results": 30,
        "model_name": model,
        "cached": True,
    }

    try:
        with st.spinner("Curating results..."):
            response = requests.post(API_URL, json=payload)
            response.raise_for_status()
            data = response.json()

        # The API returns structured data; let's extract the results list
        # Your CuratorResponse schema wraps results in a "results" key
        results = data.get("results", [])

        if not results:
            st.warning("No results found.")
        else:
            # Flatten the CuratorResult objects for the dataframe
            # API returns: [{'id': 'Title', 'score': 0.95}, ...]
            flat_results = [{"Title": r["id"], "Score": r["score"]} for r in results]

            df = pd.DataFrame(flat_results)

            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Title": st.column_config.TextColumn("Course Title"),
                    "Score": st.column_config.ProgressColumn(
                        "Relevance", format="%.4f", min_value=0, max_value=1
                    ),
                },
            )

    except requests.exceptions.ConnectionError:
        st.error(
            f"Cannot connect to Headwater Server at `{API_URL}`. Is the backend running?"
        )
    except Exception as e:
        st.error(f"An error occurred: {e}")
