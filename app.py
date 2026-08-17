import os
import pandas as pd
from flask import Flask, render_template, request, jsonify
from utility import query_features, optimize_product, RAW_PATH

app = Flask(__name__)

@app.route('/')
def index():
    # Read the contents of tmobile_detailed_specs.csv and convert to JSON format for display
    csv_content = ""
    if os.path.exists(RAW_PATH):
        df = pd.read_csv(RAW_PATH)
        csv_content = df.to_json(orient='records', indent=2)
    return render_template('index.html', csv_content=csv_content)

@app.route('/api/specs', methods=['GET'])
def get_specs():
    if os.path.exists(RAW_PATH):
        df = pd.read_csv(RAW_PATH)
        return jsonify({'status': 'success', 'content': df.to_json(orient='records', indent=2)})
    return jsonify({'status': 'error', 'message': 'CSV file not found'}), 404

@app.route('/api/query', methods=['POST'])
def handle_query():
    try:
        data = request.get_json() or {}
        user_query = data.get('query', '').strip()
        if not user_query:
            return jsonify({'status': 'error', 'message': 'Query string is required'}), 400

        results = query_features(user_query)
        return jsonify({'status': 'success', 'query': user_query, 'results': results})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/optimize', methods=['POST'])
def handle_optimize():
    try:
        data = request.get_json() or {}
        source = data.get('source', '').strip()
        target = data.get('target', '').strip()
        if not source or not target:
            return jsonify({'status': 'error', 'message': 'Both source and target products are required'}), 400

        results = optimize_product(source, target)
        return jsonify({'status': 'success', 'source': source, 'target': target, 'results': results})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    print(f"Starting Flask server on http://127.0.0.1:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)
