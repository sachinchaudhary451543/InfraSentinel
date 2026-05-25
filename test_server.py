"""Create a minimal test endpoint in the Flask app to diagnose POST issues"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify, request

app = Flask(__name__)

@app.route('/test-post', methods=['POST'])
def test_post():
    print("TEST-POST CALLED!")
    data = request.get_json(silent=True) or {}
    print(f"Received: {data}")
    return jsonify({'success': True, 'received': data})

if __name__ == '__main__':
    print("Starting test server on port 5001...")
    app.run(host='127.0.0.1', port=5001, debug=False)
