"""
Signalix — internal file upload endpoint.
Lets the owner push large data files (e.g. SET EOD zip) directly to the server,
bypassing Google Drive rate-limits. Guarded by a shared token.
Saves to /root/signalix/uploads/
"""
import os
import hashlib
from flask import Flask, request, Response

UPLOAD_DIR = "/root/signalix/uploads"
TOKEN = os.getenv("UPLOAD_TOKEN", "signalix-upload-2026")
MAX_MB = 800
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)

PAGE = """<!doctype html><html><head><meta charset=utf-8>
<title>Signalix Upload</title></head><body style="font-family:sans-serif;max-width:480px;margin:40px auto">
<h2>Signalix File Upload</h2>
<form id=up method=post action="/upload?token=signalix-upload-2026" enctype=multipart/form-data">
<input id=f type=file name=file required><br><br>
<button id=b type=submit>Upload</button>
</form>
<div id=status style="margin-top:16px;white-space:pre-wrap"></div>
<progress id=p value=0 max=100 style="width:100%;display:none"></progress>
<script>
var uploading=false;
document.getElementById('up').addEventListener('submit',function(e){
  e.preventDefault();
  var f=document.getElementById('f').files[0];
  if(!f){return;}
  uploading=true;
  var b=document.getElementById('b'); b.disabled=true; b.textContent='Uploading…';
  var s=document.getElementById('status'); s.textContent='Uploading '+f.name+' ('+(f.size/1048576).toFixed(1)+' MB)… do NOT close this tab';
  var pr=document.getElementById('p'); pr.style.display='block'; pr.value=0;
  var fd=new FormData(); fd.append('file',f);
  var xhr=new XMLHttpRequest();
  xhr.open('POST','/upload?token=signalix-upload-2026',true);
  xhr.upload.onprogress=function(ev){ if(ev.lengthComputable){ pr.value=ev.loaded/ev.total*100; } };
  xhr.onload=function(){
    uploading=false; b.disabled=false; b.textContent='Upload'; pr.style.display='none';
    s.textContent='SERVER: '+xhr.status+'\\n'+xhr.responseText;
  };
  xhr.onerror=function(){ uploading=false; b.disabled=false; b.textContent='Upload'; pr.style.display='none'; s.textContent='NETWORK ERROR — upload failed, try again'; };
  xhr.send(fd);
});
window.onbeforeunload=function(){ if(uploading){ return 'Upload still in progress — closing will cancel it'; } };
</script>
</body></html>"""

@app.route("/")
def home():
    return Response(PAGE, mimetype="text/html")

@app.route("/upload", methods=["POST"])
def upload():
    if request.args.get("token") != TOKEN:
        return Response("unauthorized", status=403)
    f = request.files.get("file")
    if not f:
        return Response("no file", status=400)
    # size guard via content-length
    cl = request.content_length or 0
    if cl > MAX_MB * 1024 * 1024:
        return Response(f"too large (max {MAX_MB}MB)", status=413)
    # allow caller to force a destination name (e.g. ?name=new%20try.zip)
    name = request.args.get("name") or f.filename or "upload.bin"
    name = os.path.basename(name)
    dest = os.path.join(UPLOAD_DIR, name)
    tmp = dest + ".part"
    h = hashlib.sha256()
    with open(tmp, "wb") as out:
        while True:
            chunk = f.stream.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
            out.write(chunk)
    os.rename(tmp, dest)
    sz = os.path.getsize(dest)
    return Response(f"OK saved {dest} ({sz} bytes) sha256={h.hexdigest()}", status=200)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, threaded=True)

import hashlib
@app.route("/upload2", methods=["POST"])
def upload2():
    """Upload that returns sha256 so the sender can verify integrity."""
    if request.args.get("token") != TOKEN:
        return Response("unauthorized", status=403)
    f = request.files.get("file")
    if not f:
        return Response("no file", status=400)
    dest = os.path.join(UPLOAD_DIR, os.path.basename(f.filename))
    h = hashlib.sha256()
    with open(dest, "wb") as out:
        while True:
            chunk = f.read(1024*1024)
            if not chunk: break
            h.update(chunk); out.write(chunk)
    return Response(f"OK sha256={h.hexdigest()} size={os.path.getsize(dest)}", status=200)
