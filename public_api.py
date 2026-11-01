"""Anonymous rule-QA boundary. Bind to loopback; expose only via Nginx /api/qa/."""
import base64
import binascii
import io
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zipfile import ZipFile, BadZipFile
from xml.etree import ElementTree as ET
from openpyxl import load_workbook
from qa_engine import run_qa_check, convert_dataframe_to_excel
import pandas as pd

MAX_FILE = 10 * 1024 * 1024
MAX_BODY = 29 * 1024 * 1024
MAX_ROWS = 5000
MAX_CHARS = 1_000_000
RULES = {
 'missing': ('Missing translation',),
 'identical': ('Source and target are identical',),
 'numbers': ('Number mismatch', 'Unit mismatch'),
 'structure': ('Tag mismatch', 'Placeholder mismatch', 'Bracket mismatch', 'Unbalanced target brackets'),
 'references': ('URL mismatch', 'Email mismatch', 'File name mismatch', 'Shortcut mismatch'),
 'style': ('Punctuation mismatch', 'Whitespace warning'),
}

class InputError(ValueError):
    pass


def zip_guard(data):
    try:
        with ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            if len(members) > 2000 or sum(x.file_size for x in members) > 50 * 1024 * 1024:
                raise InputError('expanded_limit')
            if any(x.flag_bits & 1 for x in members): raise InputError('encrypted')
            for member in members:
                if member.filename.endswith(('.xml', '.rels')):
                    xml = archive.read(member)
                    declarations = xml.replace(b'\x00', b'').upper()
                    if b'<!DOCTYPE' in declarations or b'<!ENTITY' in declarations:
                        raise InputError('invalid_file')
    except (BadZipFile, OSError, RuntimeError):
        raise InputError('invalid_file') from None


def unpack_file(item):
    if not isinstance(item, dict) or set(item) != {'name', 'data'}: raise InputError('invalid_file')
    name, encoded = item['name'], item['data']
    if not isinstance(name, str) or not isinstance(encoded, str) or len(encoded) > (MAX_FILE * 4 // 3 + 8):
        raise InputError('file_limit')
    try: data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error): raise InputError('invalid_file') from None
    if not data or len(data) > MAX_FILE: raise InputError('file_limit')
    kind = name.rsplit('.', 1)[-1].lower()
    if kind not in ('txt', 'docx', 'xlsx'): raise InputError('file_type')
    if kind != 'txt': zip_guard(data)
    return kind, data


def text_lines(kind, data):
    if kind == 'docx':
        try:
            with ZipFile(io.BytesIO(data)) as archive:
                root = ET.fromstring(archive.read('word/document.xml'))
            ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
            body = root.find(ns + 'body')
            # Match the existing QA screen: body paragraphs, not tables/headers/textboxes.
            return [] if body is None else [
                value for p in body.findall(ns + 'p')
                if (value := ''.join((n.text or '') if n.tag == ns+'t' else '\n' if n.tag == ns+'br' else '\t'
                                      for n in p.iter() if n.tag in (ns+'t', ns+'br', ns+'tab')).strip())]
        except (KeyError, ET.ParseError): raise InputError('invalid_file') from None
    for encoding in (('utf-16',) if data.startswith((b'\xff\xfe', b'\xfe\xff')) else ('utf-8-sig', 'cp949')):
        try: return [line.strip() for line in data.decode(encoding).splitlines() if line.strip()]
        except UnicodeError: pass
    raise InputError('encoding')


def read_rows(payload):
    if 'rows' in payload:
        if payload.get('files'): raise InputError('ambiguous_input')
        rows = payload['rows']
    else:
        files = payload.get('files', [])
        if not isinstance(files, list) or not 1 <= len(files) <= 2: raise InputError('files_required')
        decoded = [unpack_file(f) for f in files]
        if len(decoded) == 1:
            kind, data = decoded[0]
            if kind != 'xlsx': raise InputError('pair_required')
            book = None
            try:
                book = load_workbook(io.BytesIO(data), read_only=True, data_only=False, keep_links=False)
                sheet = book.active
                if sheet.max_column > 100: raise InputError('columns')
                iterator = sheet.iter_rows(values_only=True)
                headers = next(iterator, ())
                normalized = [''.join(str(x or '').lower().split()).replace('_','').replace('-','').lstrip('\ufeff') for x in headers]
                if normalized.count('source') != 1 or normalized.count('target') != 1: raise InputError('columns')
                a,b = normalized.index('source'),normalized.index('target')
                rows=[]
                for row in iterator:
                    source,target = row[a],row[b]
                    if source is None and target is None: continue
                    rows.append({'source': str(source) if source is not None else '', 'target': str(target) if target is not None else ''})
                    if len(rows)>MAX_ROWS: raise InputError('row_limit')
            except InputError: raise
            except (ValueError, KeyError, ET.ParseError): raise InputError('invalid_file') from None
            finally:
                if book: book.close()
        else:
            (a,source),(b,target)=decoded
            if a != b or a not in ('txt','docx'): raise InputError('same_format')
            sources,targets=text_lines(a,source),text_lines(b,target)
            if not sources or len(sources)!=len(targets): raise InputError('alignment')
            rows=[{'source':s,'target':t} for s,t in zip(sources,targets)]
    if not isinstance(rows,list) or not 1<=len(rows)<=MAX_ROWS: raise InputError('row_limit')
    size=0
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'source','target'} or any(not isinstance(x,str) for x in row.values()): raise InputError('rows')
        size+=sum(map(len,row.values()))
        if any(len(x)>20000 for x in row.values()) or size>MAX_CHARS: raise InputError('text_limit')
    return rows


def execute(payload):
    if not isinstance(payload,dict) or payload.get('action')!='qa': raise InputError('qa_only')
    if set(payload)-{'action','rows','files','checks'}: raise InputError('invalid_request')
    checks=payload.get('checks',list(RULES))
    if not isinstance(checks,list) or not checks or any(not isinstance(c,str) or c not in RULES for c in checks): raise InputError('checks')
    rows=read_rows(payload); results=[]
    prefixes=tuple(x for c in checks for x in RULES[c])
    for index,row in enumerate(rows,1):
        issues=[i for i in run_qa_check(row['source'],row['target']) if i.startswith(prefixes)]
        results.append({'id':index,**row,'issues':issues})
    return {'version':'ltli-public-qa-1','rows':results,'total':len(results),
            'flagged':sum(bool(r['issues']) for r in results),'checks':checks}


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass  # No content, filenames, IPs or behavioral analytics.
    def respond(self,status,value):
        body=json.dumps(value,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers();self.wfile.write(body)
    def do_GET(self):
        self.respond(200,{'status':'ok'}) if self.path=='/api/qa/health' else self.respond(404,{'error':'not_found'})
    def do_POST(self):
        if self.path not in ('/api/qa/check','/api/qa/report'): return self.respond(404,{'error':'not_found'})
        # No CORS; browsers may submit only same-origin JSON, never a cross-site form.
        if self.headers.get('Sec-Fetch-Site')=='cross-site': return self.respond(403,{'error':'origin'})
        if self.headers.get('Content-Type','').split(';')[0]!='application/json': return self.respond(415,{'error':'content_type'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=MAX_BODY: return self.respond(413,{'error':'body_limit'})
            self.connection.settimeout(30)
            payload=json.loads(self.rfile.read(length))
            result=execute(payload)
            if self.path=='/api/qa/report':
                frame=pd.DataFrame([{'Segment':r['id'],'Source':r['source'],'Target':r['target'],
                                     'QA Issues':'; '.join(r['issues']),'QA Result':'Review' if r['issues'] else 'No warning'}
                                    for r in result['rows']])
                body=convert_dataframe_to_excel(frame)
                self.send_response(200)
                self.send_header('Content-Type','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                self.send_header('Content-Disposition','attachment; filename="LTLI-QA-report.xlsx"')
                self.send_header('Cache-Control','no-store')
                self.send_header('Content-Length',str(len(body)))
                self.end_headers();self.wfile.write(body)
            else: self.respond(200,result)
        except InputError as error: self.respond(403 if str(error)=='qa_only' else 400,{'error':str(error)})
        except (ValueError,UnicodeError,TimeoutError): self.respond(400,{'error':'invalid_request'})
        except (BrokenPipeError,ConnectionResetError): pass
        except Exception: self.respond(500,{'error':'processing_failed'})

class BoundedServer(ThreadingHTTPServer):
    daemon_threads=True
    slots=threading.BoundedSemaphore(2)
    def process_request(self,request,address):
        if not self.slots.acquire(blocking=False):
            request.sendall(b'HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            self.shutdown_request(request);return
        try: super().process_request(request,address)
        except Exception: self.slots.release();raise
    def process_request_thread(self,request,address):
        try: super().process_request_thread(request,address)
        finally: self.slots.release()

if __name__=='__main__':
    BoundedServer(('127.0.0.1',int(os.environ.get('LTLI_QA_API_PORT','8510'))),Handler).serve_forever()
