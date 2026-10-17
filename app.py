from flask import Flask, render_template, request, Response, stream_with_context, redirect, url_for
from ban_checker import BanChecker, STEAM_API_KEY
import json
import uuid

app = Flask(__name__)
checker = BanChecker(api_key=STEAM_API_KEY)

# Simple in-memory cache for results
# In production, use Redis or a database
RESULTS_CACHE = {}
JOBS_CACHE = {}

@app.route('/', methods=['GET', 'POST'])
def index():
    # If POST (legacy fallback or if JS disabled), we could handle it, 
    # but for this feature we expect JS to handle the stream.
    # We keep it simple: Just render index.
    return render_template('index.html')

@app.route('/api/start_check', methods=['POST'])
def start_check():
    data = request.get_json(silent=True) or request.form or {}
    steam_input = (data.get('steam_input') or '').strip()
    lang = data.get('lang', 'es')
    if not steam_input:
        return {"error": "Empty input"}, 400
    job_id = str(uuid.uuid4())
    JOBS_CACHE[job_id] = {"steam_input": steam_input, "lang": lang}
    return {"job_id": job_id}

@app.route('/stream_check/<path:steam_input>')
def stream_check(steam_input):
    if steam_input in JOBS_CACHE:
        actual_input = JOBS_CACHE[steam_input]["steam_input"]
        lang = JOBS_CACHE[steam_input].get("lang", "es")
    else:
        actual_input = steam_input
        lang = request.args.get("lang", "es")

    def generate():
        # Yield padding to force browser buffer flush
        yield ":" + (" " * 2048) + "\n\n"
        
        gen = checker.get_all_bans_generator(actual_input, lang=lang)
        final_result = None
        
        try:
            for item in gen:
                # Catch 'complete' immediately
                if item["type"] == "complete":
                    print(f"[DEBUG] Generator complete. Result captured (len={len(item['result'])}).")
                    final_result = item["result"]
                    
                    res_id = str(uuid.uuid4())
                    RESULTS_CACHE[res_id] = final_result
                    
                    complete_payload = {
                        'type': 'complete',
                        'url': url_for('show_result', result_id=res_id) + f"?lang={lang}",
                        'result_id': res_id
                    }
                    yield f"data: {json.dumps(complete_payload)}\n\n"
                    
                    redirect_payload = {
                        'type': 'redirect',
                        'url': url_for('show_result', result_id=res_id) + f"?lang={lang}",
                        'result_id': res_id
                    }
                    yield f"data: {json.dumps(redirect_payload)}\n\n"
                    return

                yield f"data: {json.dumps(item)}\n\n"
        except Exception as e:
            print(f"[ERROR] Stream Exception: {e}")
            import traceback
            traceback.print_exc()
            err_msg = f"Internal error: {str(e)}" if lang == "en" else f"Error interno: {str(e)}"
            yield f"data: {json.dumps({'type': 'error', 'msg': err_msg})}\n\n"
            
        # Fallback if generator finishes without 'complete' (Should not happen usually)
        if not final_result:
            no_res_msg = "Scan finished without results." if lang == "en" else "El escaneo terminó sin resultados."
            yield f"data: {json.dumps({'type': 'error', 'msg': no_res_msg})}\n\n"

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
