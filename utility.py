

import networkx as nx
import matplotlib.pyplot as plt

from langchain_google_genai import ChatGoogleGenerativeAI
import os
import re

import pandas as pd

import networkx as nx
import pandas as pd

import chromadb
import pandas as pd

def extract_entities(text):
    elist = []
    # Regex pattern to capture everything after **Connectivity** up to the next **Header** or end of string
    pattern = r"\*\*(.*?)\*\*\s*"

    # Extract all matching header titles into a list
    extracted_headers = re.findall(pattern, text)
    for aitem in extracted_headers:
        # print(re.split(r'\s*&\s*',aitem))
        elist.extend(re.split(r'\s*&\s*',aitem))
    return elist

def extract_response_text(response):
    if hasattr(response, 'content'):
        content = response.content
    else:
        content = response

    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
            elif isinstance(item, dict):
                if item.get('type') == 'text' and 'text' in item:
                    text_parts.append(item['text'])
                elif 'text' in item and item.get('type') != 'thinking':
                    text_parts.append(item['text'])
        if text_parts:
            return "\n".join(text_parts).strip()

    if isinstance(content, str):
        pattern_text = r"'type':\s*'text',\s*'text':\s*'(.*?)'\s*\}"
        match_text = re.search(pattern_text, content, re.DOTALL)
        if match_text:
            try:
                return match_text.group(1).encode('utf-8').decode('unicode_escape').strip()
            except Exception:
                return match_text.group(1).strip()

        # Strip any leading thinking dict block if present in stringified content
        clean_content = re.sub(r"^\{'type':\s*'thinking'.*?\}\s*", "", content, flags=re.DOTALL).strip()
        return clean_content

    return str(response).strip()

RAW_PATH = 'tmobile_detailed_specs.csv'
DATA_PATH = 'tmobile_detailed_entities.csv'

llm = ChatGoogleGenerativeAI(
    model="gemma-4-26b-a4b-it",
    google_api_key=os.getenv("GEMINI_API_KEY"),
    temperature=0.1,
    max_output_tokens=4096
)

def parse_raw_data(path):
    df = pd.read_csv(path)#('tmobile_detailed_specs.csv')

    SYSTEM_PROMPT ="""
    Summarize the key features and specifications of {{product}}.

    Output Requirements:

    Format as a clean, bulleted list.

    Group related features under concise, bolded category headings (e.g., Display, Performance, Battery).

    Keep each point direct, factual, and focused on specific capabilities or specs.

    Do not include any introductory setup or concluding filler text.
    """
    entities = []
    for k, v in df.iterrows():
        product =  v['product']
        system_prompt = SYSTEM_PROMPT.replace('{{product}}', product)
        instruction = v['features']
        full_prompt= [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": instruction}
            ]

        response = llm.invoke(full_prompt)

        extracted_text = extract_response_text(response)
        print(extracted_text)
        entities.append(extracted_text)


    df['entities'] = entities


    df.columns = ['product','specs_raw','specs_list']

    df['entities'] = df['specs_list'].apply(extract_entities)
    df_entity = df.copy()
    return df_entity

def load_data(PATH):
	df = pd.read_csv(PATH)
	import ast
	def parse_entities(val):
		if isinstance(val, list):
			return val
		if isinstance(val, str):
			try:
				res = ast.literal_eval(val)
				if isinstance(res, list):
					return res
			except Exception:
				pass
			return [val]
		return []
	if 'entities' in df.columns:
		df['entities'] = df['entities'].apply(parse_entities)
	df_graph = []
	for k, v in df[['product','entities']].iterrows():
	    product = ' '.join(v['product'].split('-'))
	    for aitem in v['entities']:
	        df_graph.append({'product':product, 'entity':aitem})

	# 1. Construct the Graph from df_graph
	df_edges = pd.DataFrame(df_graph)
	G_entity = nx.from_pandas_edgelist(df_edges, source='product', target='entity')

	print(f"Graph initialized with {G_entity.number_of_nodes()} nodes and {G_entity.number_of_edges()} edges.")
	df_entity = df.copy()

	return df_entity, G_entity

def query_features(query=None):
    if not query:
        query = 'find phones with large display and long battery life'
    df, G = load_data(DATA_PATH)
    entity_list = sorted(list(set( re.sub(r'[^a-zA-Z\s]+',' ',e).strip() for es in df['entities'] for e in es if e)))

    USER_PROMPT ="""
    You are an entity classification model. Allowed Entities: {{entity_list}}Query: "{{query}}"Rules:Map terms or intent in the query to their corresponding entity category in {{entity_list}} (e.g., "screen" or "large display" $\rightarrow$ "Display").Only output canonical names present in {{entity_list}}.Format the result as a Python list of strings without additional text.
    """
    entities = []

    user_prompt = USER_PROMPT.replace('{{entity_list}}', ', '.join(entity_list))
    user_prompt = user_prompt.replace('{{query}}', query)

    full_prompt= [
            {"role": "user", "content": user_prompt}
        ]

    response = llm.invoke(full_prompt)

    extracted_text = extract_response_text(response)
    pattern = r'"([^"]+)"'
    extracted_entities = re.findall(pattern, extracted_text)
    if not extracted_entities:
        extracted_entities = [e.strip("'\"[] ") for e in extracted_text.split(',') if e.strip("'\"[] ")]
    entities.extend(extracted_entities)
    # target_entity = entities  # Or specific extracted text item
    # for aitem in target_entity:
    #     if G.has_node(aitem):
    #         matching_products = list(G.neighbors(aitem))
    #         print(f"Products linked to '{aitem}':\n", matching_products)

    target_entity = entities  # Or specific extracted text item
    target_products = []
    for aitem in target_entity:
        if G.has_node(aitem):
            matching_products = list(G.neighbors(aitem))
            target_products.extend(matching_products)

    # Format product names to hyphenated keys matching ChromaDB metadata
    target_products_formatted = list(set(
        [p.replace(' ', '-') for p in target_products] + 
        [p for p in target_products]
    ))

    collection = create_chromadb(df)
    
    filtered_results = None
    if target_products_formatted:
        filtered_results = collection.query(
            query_texts=[query],
            where={"product": {"$in": target_products_formatted}},
            n_results=1
        )

    # Fallback to unfiltered vector similarity search if no matches found with filter
    if not filtered_results or not filtered_results['documents'] or not filtered_results['documents'][0]:
        filtered_results = collection.query(
            query_texts=[query],
            n_results=1
        )

    results = []
    if filtered_results and filtered_results['documents'] and filtered_results['documents'][0]:
        for doc, meta, dist in zip(filtered_results['documents'][0], filtered_results['metadatas'][0], filtered_results['distances'][0]):
            cosine_sim = 1.0 - dist
            results.append({
                "product": meta['product'],
                "distance": dist,
                "similarity": cosine_sim,
                "entities": meta['entities'],
                "specs": doc
            })

    return results


def create_chromadb(df_data):
    # 1. Initialize persistent client (saves data to disk)
    client = chromadb.PersistentClient(path="./chroma_product_db")

    # Check if collection exists
    existing_collections = [col.name for col in client.list_collections()]
    if "product_specs" in existing_collections:
        collection = client.get_collection(name="product_specs")
        print(f"Collection 'product_specs' already exists with {collection.count()} items. Returning existing collection.")
        return collection

    # 2. Create collection
    collection = client.create_collection(
        name="product_specs",
        metadata={"hnsw:space": "cosine"}  # Options: cosine, l2, ip
    )

    # 3. Prepare data from your DataFrame
    documents = []
    metadatas = []
    ids = []

    for idx, row in df_data.iterrows():
        # Convert specs/features to main text embedding content
        specs_text = str(row['features']) if 'features' in row else str(row['specs_list'])

        # Handle entities format (convert list to string if needed)
        entities_val = row['entities'] if 'entities' in row else []
        entities_str = ", ".join(entities_val) if isinstance(entities_val, list) else str(entities_val)

        documents.append(specs_text)
        metadatas.append({
            "product": str(row['product']),
            "entities": entities_str
        })
        ids.append(f"prod_{idx}")

    # 4. Upsert into ChromaDB
    collection.upsert(
        documents=documents,
        metadatas=metadatas,
        ids=ids
    )

    print(f"Successfully indexed {collection.count()} products into ChromaDB.")
    return collection


def optimize_product(source, target):
    df,G = load_data(DATA_PATH)
    data_collection = create_chromadb(df)
    prod1 = source # "samsung-galaxy-z-fold8"
    prod2 = target # "apple-iphone-17"


    from sklearn.metrics.pairwise import cosine_similarity

    # Fetch documents for prod1 and prod2 from ChromaDB
    doc1 = data_collection.get(where={"product": prod1})['documents'][0]
    doc2 = data_collection.get(where={"product": prod2})['documents'][0]

    # Compute embedding similarity using your embedding function
    emb1 = data_collection._embedding_function([doc1])
    emb2 = data_collection._embedding_function([doc2])

    similarity_score = cosine_similarity(emb1, emb2)[0][0]
    print(f"Cosine Similarity Score: {similarity_score:.4f}")


    prod1_entity_list = G.neighbors(' '.join(prod1.split('-')))
    geo_prompt = """
You are a product specifications expert in Generative Engine Optimization (GEO).

Your objective is to modify and upgrade the Target Product specifications so that they match or align with the high-performing features of the Source Product across key specification categories.

### Input Context:
- **Source Product Specs (Reference):**
{{doc1}}

- **Target Product Specs (To Modify):**
{{doc2}}

- **Key Feature Categories to Align:** {{spects_list}}

### Instructions:
1. **Feature Alignment:** Rewrite and update the Target Product specifications under the categories listed in {{spects_list}} so that each feature offers comparable or matching performance/quality to the Source Product.
2. **Completeness:** If any specification listed in {{spects_list}} is missing from the Target Product, supplement it with realistic, competitive technical specifications.
3. **Format & Tone:** Retain the original structural layout, section headings, and bulleted Markdown style of the Source Product in your output.
"""
    geo_prompt = geo_prompt.replace('{{doc1}}', doc1)
    geo_prompt = geo_prompt.replace('{{doc2}}', doc2)
    geo_prompt = geo_prompt.replace('{{spects_list}}', ', '.join(prod1_entity_list))



    full_prompt= [
            {"role": "user", "content": geo_prompt}
        ]

    response = llm.invoke(full_prompt)

    extracted_text = extract_response_text(response)

    # Compute embedding similarity using your embedding function
    emb1 = data_collection._embedding_function([doc1])
    emb2 = data_collection._embedding_function([extracted_text])

    similarity_score_optimized = float(cosine_similarity(emb1, emb2)[0][0])
    print(f"Optimized Cosine Similarity Score: {similarity_score_optimized:.4f}")
    optimize_text_prompt = f"Be direct and concise. Output only the polished product introduction (~100 words) without preamble or reasoning:\n\n{extracted_text}"
    full_prompt = [{"role": "user", "content": optimize_text_prompt}]
    response = llm.invoke(full_prompt)
    optimized_text = extract_response_text(response)
    return {
        'before_optimized': float(similarity_score),
        'after_optimized': float(similarity_score_optimized),
        'optimized_text': optimized_text
    }
if __name__ == "__main__":

    query = 'find phones with large display and long battery life'
    results = query_features(query)
    print(results)

    # source = "samsung-galaxy-z-fold8"
    # target = "apple-iphone-17"
    # results = optimize_product(source, target)
    # print(results)

