"""Anonymous rule-QA boundary. Bind to loopback; expose only via Nginx /api/qa/."""
import base64
import binascii
import io
import json
import os
import threading
import time
from google_sheets_storage import record_qa
from qa_notifications import notify_qa
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zipfile import ZipFile, BadZipFile
from xml.etree import ElementTree as ET
from openpyxl import load_workbook
from qa_engine import run_qa_check
from qa_localization import MESSAGES, localized_explanation
from qa_workbooks import GLOSSARY_SHEET, GLOSSARY_HEADER, SAMPLES, localized_report, report_filename, sample_workbook
from qa_findings import annotate, review, ReviewError

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

MAX_FILE = 10 * 1024 * 1024
MAX_BODY = 29 * 1024 * 1024
MAX_ROWS = 5000
MAX_CHARS = 1_000_000
RULES = {
 'missing': ('Missing translation',),
 'terminology': ('Terminology mismatch:',),
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


def read_rows(payload, embedded_glossary=None):
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
                if embedded_glossary is not None and GLOSSARY_SHEET in book:
                    embedded_glossary.extend(workbook_glossary(book[GLOSSARY_SHEET]))
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


def read_glossary(payload):
    entries = payload.get('glossary', [])
    if not isinstance(entries, list) or len(entries) > 50:
        raise InputError('glossary')
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'source_term', 'approved_targets'}:
            raise InputError('glossary')
        source, targets = entry['source_term'], entry['approved_targets']
        if not isinstance(targets, list) or not 1 <= len(targets) <= 5:
            raise InputError('glossary')
        if any(not isinstance(term, str) or not term.strip() or len(term) > 150 for term in [source, *targets]):
            raise InputError('glossary')
    return entries


def workbook_glossary(sheet):
    rows = sheet.iter_rows(max_col=2,values_only=True)
    if next(rows,()) != GLOSSARY_HEADER:
        raise InputError('glossary')
    terms = {}
    for index,(source,target) in enumerate(rows):
        if index >= 250 or not isinstance(source,str) or not isinstance(target,str):
            raise InputError('glossary')
        terms.setdefault(source,[]).append(target)
    return read_glossary({'glossary':[{'source_term':source,'approved_targets':targets}
                                      for source,targets in terms.items()]})


def execute(payload):
    if not isinstance(payload,dict) or payload.get('action')!='qa': raise InputError('qa_only')
    if set(payload)-{'action','rows','files','checks','decisions','explain_id','language','glossary'}: raise InputError('invalid_request')
    embedded=[]
    rows=read_rows(payload,embedded if 'glossary' not in payload else None)
    glossary=read_glossary(payload) if 'glossary' in payload else embedded
    checks=payload.get('checks',[rule for rule in RULES if rule!='terminology' or glossary])
    if not isinstance(checks,list) or not checks or any(not isinstance(c,str) or c not in RULES for c in checks): raise InputError('checks')
    if 'terminology' in checks and not glossary:
        raise InputError('glossary_required')
    results=[]
    prefixes=tuple(x for c in checks for x in RULES[c])
    for index,row in enumerate(rows,1):
        all_issues=run_qa_check(row['source'],row['target'],glossary)
        issues=[i for i in all_issues if i.startswith(prefixes)]
        results.append({'id':index,**row,'issues':issues,'all_issues':all_issues})
    result=annotate({'version':'ltli-public-qa-1','rows':results,'total':len(results),'checks':checks},payload.get('decisions'))
    if 'explain_id' in payload:
        index=payload['explain_id'];language=payload.get('language','ko')
        if type(index) is not int or not 1<=index<=len(results) or not isinstance(language,str) or language not in MESSAGES:raise InputError('explain_request')
        row=results[index-1]
        result['explanation']=localized_explanation({**row,'issues':row['active_issues']},language)
        result['explained_id']=index
    return result


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass  # No content, filenames, IPs or behavioral analytics.
    def respond(self,status,value, *, language=None):
        body=json.dumps(value,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        if language:
            self.send_header('Content-Language', language)
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers();self.wfile.write(body)
    def workbook_response(self, body, filename, language):
        self.send_response(200)
        self.send_header('Content-Type',XLSX_MIME)
        self.send_header('Content-Language',language)
        self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.respond(200,{'status':'ok'}) if self.path=='/api/qa/health' else self.respond(404,{'error':'not_found'})
    def do_POST(self):
        if self.path=='/api/qa/assist': return self.respond(403,{'error':'qa_only'})
        if self.path not in ('/api/qa/check','/api/qa/report','/api/qa/prepare','/api/qa/review'): return self.respond(404,{'error':'not_found'})
        # No CORS; browsers may submit only same-origin JSON, never a cross-site form.
        if self.headers.get('Sec-Fetch-Site')=='cross-site': return self.respond(403,{'error':'origin'})
        if self.headers.get('Content-Type','').split(';')[0]!='application/json': return self.respond(415,{'error':'content_type'})
        started=time.perf_counter()
        log_check=False
        outcome='failed'
        metrics={}
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=MAX_BODY: return self.respond(413,{'error':'body_limit'})
            self.connection.settimeout(30)
            payload=json.loads(self.rfile.read(length))
            log_check=(self.path=='/api/qa/check' and isinstance(payload,dict) and 'explain_id' not in payload)
            if self.path=='/api/qa/prepare':
                if isinstance(payload,dict) and payload.get('action')=='sample':
                    language=payload.get('language')
                    fmt=payload.get('format','rows')
                    if (set(payload)-{'action','language','format'} or not isinstance(language,str)
                        or language not in SAMPLES or fmt not in ('rows','xlsx')):
                        raise InputError('sample_request')
                    sample=SAMPLES[language]
                    if fmt=='xlsx':
                        return self.workbook_response(sample_workbook(sample),f'ltli_qa_sample_{language}.xlsx',language)
                    return self.respond(200,{'version':'ltli-qa-sample-1',**sample},language=language)
                if not isinstance(payload,dict) or payload.get('action')!='prepare' or set(payload)-{'action','rows','files'}:
                    raise InputError('invalid_request')
                embedded=[]
                rows=read_rows(payload,embedded)
                result={'version':'ltli-qa-input-1','total':len(rows),'rows':rows}
                if embedded:
                    result['glossary']=embedded
            elif self.path=='/api/qa/review':
                if not isinstance(payload,dict) or payload.get('action')!='review' or set(payload)-{'action','rows','checks','decisions','operation','row_id','issue','fingerprint','glossary'}:
                    raise InputError('invalid_request')
                result=execute({k:v for k,v in payload.items() if k in ('rows','checks','decisions','glossary')}|{'action':'qa'})
                # Recompute all rules when validating old decisions during accept/restore.
                glossary=read_glossary(payload)
                for row in result['rows']:row['all_issues']=run_qa_check(row['source'],row['target'],glossary)
                result=review(result,payload)
            elif self.path=='/api/qa/report':
                # An older browser bundle omits the locale. Its UI language cannot be inferred.
                language=payload.get('report_language') if isinstance(payload,dict) else None
                if not isinstance(language,str) or language not in MESSAGES:
                    raise InputError('report_language')
                result=execute({key:value for key,value in payload.items() if key!='report_language'})
                if sum(len(row['issues']) for row in result['rows'])>25000:
                    raise InputError('report_limit')
                return self.workbook_response(localized_report(result,language),report_filename(language),language)
            else: result=execute(payload)
            outcome='success'
            if log_check:
                metrics={'segments':result['total'],'warnings':sum(len(r['issues']) for r in result['rows'])}
            self.respond(200,result)
        except ReviewError as error: self.respond(409 if str(error)=='stale_review' else 400,{'error':str(error)})
        except InputError as error: self.respond(403 if str(error)=='qa_only' else 400,{'error':str(error)})
        except (ValueError,UnicodeError,TimeoutError): self.respond(400,{'error':'invalid_request'})
        except (BrokenPipeError,ConnectionResetError): pass
        except Exception: self.respond(500,{'error':'processing_failed'})
        finally:
            if log_check:
                elapsed_ms=int((time.perf_counter()-started)*1000)
                record_qa(outcome, elapsed_ms, **metrics)
                if outcome=='success':notify_qa(elapsed_ms, **metrics)

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
