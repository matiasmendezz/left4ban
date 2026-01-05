from flask import Flask, render_template, request, Response, stream_with_context, redirect, url_for
from ban_checker import BanChecker, STEAM_API_KEY
import json
import uuid

app = Flask(__name__)
checker = BanChecker(api_key=STEAM_API_KEY)

# Simple in-memory cache for results
# In production, use Redis or a database
RESULTS_CACHE = {}

@app.route('/', methods=['GET', 'POST'])
def index():
    # If POST (legacy fallback or if JS disabled), we could handle it, 
    # but for this feature we expect JS to handle the stream.
    # We keep it simple: Just render index.
    return render_template('index.html')

@app.route('/stream_check/<path:steam_input>')
def stream_check(steam_input):
    def generate():
        # Yield padding to force browser buffer flush
        yield ":" + (" " * 2048) + "\n\n"
        
        gen = checker.get_all_bans_generator(steam_input)
        final_result = None
        
        try:
            for item in gen:
                # Catch 'complete' immediately and redirect
                if item["type"] == "complete":
                    print(f"[DEBUG] Generator complete. Result captured (len={len(item['result'])}).")
                    final_result = item["result"]
                    
                    # STORE AND REDIRECT NOW
                    res_id = str(uuid.uuid4())
                    RESULTS_CACHE[res_id] = final_result
                    
                    print(f"[DEBUG] Sending redirect to {res_id}")
                    yield f"data: {json.dumps({'type': 'redirect', 'url': url_for('show_result', result_id=res_id)})}\n\n"
                    
                    # Heavy padding to force flush
                    yield ":" + (" " * 8192) + "\n\n" 
                    
                    import time
                    time.sleep(2)
                    return

                yield f"data: {json.dumps(item)}\n\n"
        except Exception as e:
            print(f"[ERROR] Stream Exception: {e}")
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'msg': f'Error interno: {str(e)}'})}\n\n"
            
        # Fallback if generator finishes without 'complete' (Should not happen usually)
        if not final_result:
             yield f"data: {json.dumps({'type': 'error', 'msg': 'El escaneo terminó sin resultados.'})}\n\n"

    headers = {
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',
        'Connection': 'keep-alive' # Explicitly keep alive
    }
    return Response(stream_with_context(generate()), mimetype='text/event-stream', headers=headers)

@app.route('/result/<result_id>')
def show_result(result_id):
    data = RESULTS_CACHE.get(result_id)
    if not data:
        return render_template('index.html', error="Resultado expirado o inválido.")
    return render_template('results.html', data=data)

if __name__ == '__main__':
    import webbrowser
    from threading import Timer

    def open_browser():
        webbrowser.open_new("http://127.0.0.1:5000")

    Timer(1.5, open_browser).start()
    app.run(debug=False, port=5000)
