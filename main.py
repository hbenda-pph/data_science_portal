import os

from flask import Flask, jsonify


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


app = Flask(__name__, static_folder=BASE_DIR)


@app.route('/', methods=['GET'])
def serve_portal():
    """Entrega la página principal del portal de ciencia de datos."""
    return app.send_static_file('index.html')


@app.route('/api/health', methods=['GET'])
def health_check():
    """Endpoint simple para monitoreo del servicio."""
    return jsonify({"status": "ok"})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=True, host='0.0.0.0', port=port)
